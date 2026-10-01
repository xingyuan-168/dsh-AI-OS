"""Thin, real finish checks (ADR-0016).

The finish gate used to trust caller-supplied attestations (--tests-passed,
--docs-synced). It now runs only checks that can be verified in place: the
declared test command (when given), ruff when the project configures it,
"git diff --check", repository hygiene, the pending memory-candidate count,
and a second-layer Code Start re-verification over the complete task diff
from an explicit baseline, including committed code. Professional judgments such
as "the docs are consistent with the change" remain Codex's duty and are
deliberately not re-implemented here.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from codex_ai_os.adapters.git import GitRunner
from codex_ai_os.core.gates import GateFinding, disposable_findings, hygiene_findings
from codex_ai_os.infrastructure.memory import CANDIDATE_DIRECTORY

TEST_TIMEOUT_SECONDS = 900
RUFF_TIMEOUT_SECONDS = 300


def run_thin_checks(
    root: Path,
    *,
    test_command: str | None,
    change_class: str | None = None,
    requirement_id: str | None = None,
    base_ref: str | None = None,
    runner: GitRunner | None = None,
) -> list[GateFinding]:
    """Run only the finish checks that can be verified in place."""

    root = root.resolve()
    git = runner or GitRunner(root)
    findings: list[GateFinding] = []
    try:
        base = _resolve_base(git, base_ref)
        formal = _formal_dirty_paths(root, git, base)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        return [GateFinding(str(exc).split(":", 1)[0], str(exc))]
    findings.extend(_test_command_findings(root, test_command))
    findings.extend(_ruff_findings(root))
    findings.extend(_diff_check_findings(git, base))
    findings.extend(hygiene_findings(root, git))
    findings.extend(disposable_findings(git))
    findings.extend(_memory_candidate_findings(root))
    findings.extend(
        _code_start_recheck_findings(
            root, git, change_class=change_class, requirement_id=requirement_id, formal=formal
        )
    )
    return findings


def _resolve_base(git: GitRunner, base_ref: str | None) -> str:
    if not base_ref:
        raise ValueError("FINISH_BASE_REQUIRED: supply the task's starting commit or EMPTY_TREE")
    if base_ref == "EMPTY_TREE":
        empty = git.run("hash-object", "-t", "tree", "--stdin")
        if empty.returncode != 0:
            raise ValueError("FINISH_BASE_INVALID: cannot resolve empty tree")
        return empty.stdout.strip()
    resolved = git.run("rev-parse", "--verify", "--end-of-options", base_ref + "^{commit}")
    if resolved.returncode != 0:
        raise ValueError("FINISH_BASE_INVALID: base must resolve to a commit")
    sha = resolved.stdout.strip()
    if git.run("merge-base", "--is-ancestor", sha, "HEAD").returncode != 0:
        raise ValueError("FINISH_BASE_INVALID: base is not an ancestor of HEAD")
    return sha


def _formal_dirty_paths(root: Path, git: GitRunner, base_ref: str) -> list[str]:
    from codex_ai_os.infrastructure.config import load_project_config, resolve_runtime_root

    code_paths = load_project_config(resolve_runtime_root(root).project_root).code_paths
    paths: set[str] = set()
    has_head = git.run("rev-parse", "--verify", "HEAD").returncode == 0
    for args in (
        (
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            base_ref,
            *(("HEAD",) if has_head else ("--cached",)),
        ),
        ("diff", "--name-only", "-z", "--no-renames", "--cached"),
        ("diff", "--name-only", "-z", "--no-renames"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        result = git.run(*args)
        if result.returncode != 0:
            raise ValueError("FINISH_DIFF_FAILED: cannot inspect the complete task change")
        paths.update(path for path in result.stdout.split("\0") if path)
    return sorted(
        path
        for path in paths
        if any(
            path.casefold() == prefix.casefold()
            or path.casefold().startswith(prefix.casefold() + "/")
            for prefix in code_paths
        )
    )


def _code_start_recheck_findings(
    root: Path,
    git: GitRunner,
    *,
    change_class: str | None,
    requirement_id: str | None,
    formal: list[str],
) -> list[GateFinding]:
    """Second Code Start layer: formal code changed, so prove the basis.

    Covers the indirect-write hole (``python generate.py`` and friends): the
    Hook screens the write attempt, this re-check screens the result. Already
    merged parallel-task work is covered by the first layer at write time
    plus the worktree cleanup merge proof; no extra state is kept.
    """

    if not formal:
        return []
    if change_class is None or not change_class.strip():
        return [
            GateFinding(
                "CODE_START_UNVERIFIED",
                "formal code paths changed ("
                + ", ".join(formal[:3])
                + ") but no Code Start basis was verified; pass --change-class "
                "(and --requirement-id when the class requires research)",
                path=formal[0],
            )
        ]
    # Deferred import: gates re-exports the evaluator defined in this package.
    from codex_ai_os.core.gates import evaluate_code_start

    try:
        from codex_ai_os.infrastructure.config import load_project_config, resolve_runtime_root

        config = load_project_config(resolve_runtime_root(root).project_root)
        decision = evaluate_code_start(
            root,
            change_class=change_class,
            requirement_id=requirement_id,
            runner=git,
            github_hosts=config.github_hosts,
        )
    except Exception as exc:  # invalid change class: fail closed
        return [
            GateFinding(
                "CODE_START_UNVERIFIED",
                "Code Start re-verification failed: " + str(exc),
                path=formal[0],
            )
        ]
    return list(decision.findings)


def _test_command_findings(root: Path, test_command: str | None) -> list[GateFinding]:
    if test_command is None or not test_command.strip():
        return [GateFinding("TEST_COMMAND_SKIPPED", "no test command declared", blocking=False)]
    try:
        completed = subprocess.run(
            test_command,
            shell=True,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return [
            GateFinding(
                "TEST_COMMAND_TIMEOUT",
                "test command did not finish within " + str(TEST_TIMEOUT_SECONDS) + " seconds",
            )
        ]
    if completed.returncode == 0:
        return []
    detail = "test command failed with exit code " + str(completed.returncode)
    output = (completed.stdout or "").strip() or (completed.stderr or "").strip()
    if output:
        tail = output.splitlines()[-3:]
        detail += ": " + " | ".join(tail)
    return [GateFinding("TEST_COMMAND_FAILED", detail)]


def _ruff_findings(root: Path) -> list[GateFinding]:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return []
    try:
        configured = "[tool.ruff]" in pyproject.read_text(encoding="utf-8")
    except OSError:
        return []
    if not configured:
        return []
    interpreter = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.is_file():
        interpreter = Path(sys.executable)
    if interpreter == Path(sys.executable) and importlib.util.find_spec("ruff") is None:
        return [
            GateFinding(
                "RUFF_UNAVAILABLE",
                "pyproject.toml configures ruff but this interpreter cannot import it",
                blocking=True,
            )
        ]
    try:
        completed = subprocess.run(
            [str(interpreter), "-m", "ruff", "check", "."],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=RUFF_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return [GateFinding("RUFF_TIMEOUT", "ruff check exceeded its time budget")]
    except OSError as exc:
        return [GateFinding("RUFF_FAILED", "ruff check failed to run: " + str(exc))]
    if completed.returncode == 0:
        return []
    output = (completed.stdout or "").strip() or (completed.stderr or "").strip()
    detail = next(
        (line for line in output.splitlines() if line.strip()),
        "ruff reported problems",
    )
    return [GateFinding("RUFF_FAILED", detail)]


def _diff_check_findings(git: GitRunner, base_ref: str) -> list[GateFinding]:
    has_head = git.run("rev-parse", "--verify", "HEAD").returncode == 0
    results = [
        git.run("diff", "--check", *args)
        for args in ((base_ref, "HEAD" if has_head else "--cached"), ("--cached",), ())
    ]
    completed = next(
        (result for result in results if result.returncode != 0 or result.stdout.strip()),
        results[0],
    )
    if completed.returncode != 0:
        return [GateFinding("GIT_DIFF_CHECK_FAILED", "git diff --check failed to run")]
    issues = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not issues:
        return []
    first_path = issues[0].split(":", 1)[0] if ":" in issues[0] else None
    return [
        GateFinding(
            "GIT_DIFF_CHECK",
            str(len(issues))
            + " whitespace or conflict-marker problem(s) flagged by git diff --check",
            path=first_path,
        )
    ]


def _memory_candidate_findings(root: Path) -> list[GateFinding]:
    directory = root / CANDIDATE_DIRECTORY
    if not directory.is_dir():
        return []
    pending = sorted(entry.name for entry in directory.iterdir() if entry.is_file())
    if not pending:
        return []
    return [
        GateFinding(
            "MEMORY_CANDIDATES_PENDING",
            str(len(pending)) + " memory candidate(s) await accept/reject (non-blocking reminder)",
            path=", ".join(pending[:3]),
            blocking=False,
        )
    ]


__all__ = [
    "RUFF_TIMEOUT_SECONDS",
    "TEST_TIMEOUT_SECONDS",
    "run_thin_checks",
]
