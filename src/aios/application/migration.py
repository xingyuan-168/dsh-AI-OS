"""Move a Codex-era runtime directory onto the DSH layout (ADR-0018).

The migration is a data move, not a rebuild: the runtime database is copied to a
consistency backup with a SHA-256 sidecar first, then moved as-is. Structural
validation of an older schema stays with the documented ``init --migrate-runtime``
path, so an unrecognized database is preserved rather than silently discarded
(ADR-0017 failure semantics).

Anything in the legacy directory that this module does not recognize is reported
and left in place; the legacy directory is removed only once it is empty.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

LEGACY_ROOT = ".codex-os"
RUNTIME_ROOT = ".aios"

# Legacy entries this module understands, relative to the legacy root.
KNOWN_FILES = (
    "project.yaml",
    "state/state.db",
    "state/memory.lock",
    "state/memory-candidates",
)


class MigrationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class MigrationResult:
    migrated: bool
    moved: tuple[str, ...]
    backup: str | None
    unknown: tuple[str, ...]
    detail: str


def migrate_runtime(project_root: Path) -> MigrationResult:
    """Migrate one project from ``.codex-os/`` to ``.aios/``."""

    root = project_root.resolve()
    legacy = root / LEGACY_ROOT
    if not legacy.is_dir():
        return MigrationResult(False, (), None, (), "no legacy runtime directory")
    if not _looks_like_runtime(legacy):
        raise MigrationError(
            "MIGRATION_UNKNOWN_STRUCTURE",
            "MIGRATION_UNKNOWN_STRUCTURE: "
            + LEGACY_ROOT
            + " does not contain a recognized project config or runtime database",
        )

    target = root / RUNTIME_ROOT
    target.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    backup: str | None = None

    database = legacy / "state" / "state.db"
    if database.is_file():
        backup = _backup(database, target / "state" / "backups")

    for relative in KNOWN_FILES:
        source = legacy / relative
        if not source.exists():
            continue
        destination = target / relative
        if destination.exists() and not source.is_dir():
            # Never overwrite a live runtime entry; report it instead.
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            _merge_directory(source, destination)
        else:
            shutil.move(str(source), str(destination))
        moved.append(RUNTIME_ROOT + "/" + relative)

    unknown = tuple(sorted(_remaining(legacy)))
    detail = "migrated" if moved else "nothing to migrate"
    if unknown:
        detail += "; unrecognized entries preserved in " + LEGACY_ROOT
    else:
        _prune_empty(legacy)

    return MigrationResult(True, tuple(moved), backup, unknown, detail)


def _looks_like_runtime(legacy: Path) -> bool:
    return (legacy / "project.yaml").is_file() or (legacy / "state" / "state.db").is_file()


def _backup(database: Path, backups: Path) -> str:
    """Copy the live database and record its digest before any move."""

    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = database.name + "." + stamp + ".bak"
    destination = backups / name
    shutil.copy2(database, destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    (backups / (name + ".sha256")).write_text(
        digest + "  " + name + "\n", encoding="ascii"
    )
    return (Path(RUNTIME_ROOT) / "state" / "backups" / name).as_posix()


def _merge_directory(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.iterdir()):
        moved = destination / entry.name
        if moved.exists():
            # Keep the existing runtime entry; the caller reports the leftover.
            continue
        shutil.move(str(entry), str(moved))
    _prune_empty(source)


def _remaining(legacy: Path) -> list[str]:
    return [
        path.relative_to(legacy).as_posix()
        for path in legacy.rglob("*")
        if path.is_file()
    ]


def _prune_empty(directory: Path) -> None:
    """Remove the legacy directory tree only when nothing is left in it."""

    for child in sorted(directory.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if child.is_dir() and not any(child.iterdir()):
            child.rmdir()
    if directory.is_dir() and not any(directory.iterdir()):
        directory.rmdir()


__all__ = [
    "KNOWN_FILES",
    "LEGACY_ROOT",
    "RUNTIME_ROOT",
    "MigrationError",
    "MigrationResult",
    "migrate_runtime",
]
