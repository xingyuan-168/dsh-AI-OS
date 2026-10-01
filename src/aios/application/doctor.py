"""Windows runtime diagnostics (governance-core surface)."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from aios.infrastructure.config import resolve_runtime_root

# The npm package name a DSH profile declares for this governance layer.
PLUGIN_PACKAGE_NAME = "ai-engineering-os"


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    required: bool
    ok: bool | None
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks if check.required)

    @property
    def path_encoding_corrupt(self) -> bool:
        return any(check.name == "path-encoding" and not check.ok for check in self.checks)


class DoctorService:
    _PATH_COLUMNS: ClassVar[dict[str, tuple[str, ...]]] = {
        "tasks": ("title",),
        "worktrees": ("path",),
        "memory_index": ("title", "summary", "source"),
    }

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = resolve_runtime_root(project_root or Path.cwd()).project_root

    def run(self) -> DoctorReport:
        return DoctorReport(
            checks=(
                self._python_check(),
                self._command_check("git", required=True, version_args=("--version",)),
                self._sqlite_check(),
                self._path_encoding_check(),
                self._plugin_manifest_check(),
                self._dsh_profile_check(),
                DoctorCheck(
                    "plugin-loaded",
                    False,
                    None,
                    "unknown: only a new DSH session proves the plugin loaded",
                ),
            )
        )

    def _plugin_manifest_check(self) -> DoctorCheck:
        """Report whether the local DSH plugin package is present.

        File presence proves neither profile installation nor loading: AIOS
        decisions and the host's registration are separate layers.
        """
        manifest = self.project_root / "plugins" / "ai-engineering-os" / "package.json"
        if not manifest.is_file():
            return DoctorCheck(
                "plugin-manifest",
                False,
                None,
                "DSH plugin manifest not found; the plugin is installed per profile",
            )
        try:
            declared = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return DoctorCheck(
                "plugin-manifest", False, False, f"plugin manifest unreadable: {exc}"
            )
        name = str(declared.get("name") or "")
        if not name:
            return DoctorCheck("plugin-manifest", False, False, "plugin manifest declares no name")
        return DoctorCheck("plugin-manifest", False, True, f"plugin package {name} present")

    @staticmethod
    def _dsh_profile_check() -> DoctorCheck:
        """Report whether any DSH profile declares the governance plugin.

        A declaration proves neither enablement nor loading, so this check is
        never reported as a proven pass; it only surfaces a missing install.
        """
        home = os.environ.get("DSH_HOME")
        profiles = (Path(home) if home else Path.home() / ".dsh") / "profiles"
        if not profiles.is_dir():
            return DoctorCheck(
                "dsh-profile", False, None, f"no DSH profile directory at {profiles}"
            )
        declaring: list[str] = []
        for profile in sorted(path for path in profiles.iterdir() if path.is_dir()):
            for name in ("cordis.patch.yml", "cordis.yml", "package.json"):
                candidate = profile / name
                if not candidate.is_file():
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                if PLUGIN_PACKAGE_NAME in text:
                    declaring.append(profile.name)
                    break
        if declaring:
            return DoctorCheck(
                "dsh-profile",
                False,
                None,
                "profile declares " + PLUGIN_PACKAGE_NAME + ": " + ", ".join(declaring),
            )
        return DoctorCheck(
            "dsh-profile",
            False,
            None,
            "no DSH profile declares " + PLUGIN_PACKAGE_NAME + "; enforcement is not installed",
        )

    def _path_encoding_check(self) -> DoctorCheck:
        database_path = self.project_root / ".aios" / "state" / "state.db"
        if not database_path.is_file():
            return DoctorCheck("path-encoding", True, True, "project state database is not present")
        corrupt: list[dict[str, object]] = []
        try:
            with sqlite3.connect(database_path) as connection:
                connection.row_factory = sqlite3.Row
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                for table, requested_columns in self._PATH_COLUMNS.items():
                    if table not in tables:
                        continue
                    available = {
                        str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
                    }
                    for column in requested_columns:
                        if column not in available:
                            continue
                        rows = connection.execute(
                            f'SELECT rowid, "{column}" FROM "{table}" '
                            f'WHERE instr("{column}", char(65533)) > 0'
                        ).fetchall()
                        corrupt.extend(
                            {
                                "table": table,
                                "record": int(row["rowid"]),
                                "field": column,
                            }
                            for row in rows
                        )
        except sqlite3.Error as exc:
            return DoctorCheck("path-encoding", True, False, f"state database unreadable: {exc}")
        detail = json.dumps(
            {
                "code": "PATH_ENCODING_CORRUPT" if corrupt else None,
                "records": corrupt,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return DoctorCheck("path-encoding", True, not corrupt, detail)

    @staticmethod
    def _python_check() -> DoctorCheck:
        version = sys.version_info
        ok = version.major == 3 and version.minor == 12
        return DoctorCheck(
            name="python",
            required=True,
            ok=ok,
            detail=f"{version.major}.{version.minor}.{version.micro}",
        )

    @staticmethod
    def _sqlite_check() -> DoctorCheck:
        try:
            with sqlite3.connect(":memory:") as connection:
                connection.execute("SELECT sqlite_version()")
            return DoctorCheck("sqlite", True, True, sqlite3.sqlite_version)
        except sqlite3.Error as exc:
            return DoctorCheck("sqlite", True, False, str(exc))

    def _command_check(
        self,
        name: str,
        *,
        required: bool,
        version_args: tuple[str, ...],
    ) -> DoctorCheck:
        return self._executable_check(
            name,
            shutil.which(name),
            required=required,
            version_args=version_args,
        )

    @staticmethod
    def _executable_check(
        name: str,
        executable: str | None,
        *,
        required: bool,
        version_args: tuple[str, ...],
    ) -> DoctorCheck:
        if executable is None:
            return DoctorCheck(name, required, False, "executable not found")
        result = _run_command((executable, *version_args), timeout=10)
        detail = result.stdout.strip() or result.stderr.strip() or executable
        return DoctorCheck(name, required, result.returncode == 0, detail)


def _run_command(command: tuple[str, ...], *, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))
