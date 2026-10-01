"""Kernel-level host-event policy: one rule set behind every host surface.

The DSH bridge contract itself (`aios authorize-dsh` over stdio) lives in
test_dsh_bridge.py; this module pins the policy those surfaces share.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aios.application.hook_gateway import authorize_hook_payload
from aios.core.worktree import WorktreeManager
from aios.infrastructure.database import Database


def payload(
    root: Path, tool: str = "apply_patch", command: str = "*** Add File: docs/x.md\n+x"
) -> dict[str, Any]:
    return {
        "cwd": str(root),
        "tool_name": tool,
        "tool_input": {"command": command},
        "hook_event_name": "PreToolUse",
    }


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin main",
        "git push origin :refs/heads/feature",
        "git update-ref -d refs/heads/main",
        "git reset --hard",
        "git clean -fd",
        "git branch -D feature",
    ],
)
def test_shared_main_git_guards(governed_repo: Path, command: str) -> None:
    result = authorize_hook_payload(payload(governed_repo, "Bash", command))
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "git branch -d feature",
        "pip install requests",
        "npm install",
        "cargo build",
        "pytest tests",
        "ruff check src",
    ],
)
def test_native_engineering_commands_remain_native(governed_repo: Path, command: str) -> None:
    assert authorize_hook_payload(payload(governed_repo, "Bash", command)) == {}


def test_registered_worktree_and_single_writer(governed_repo: Path) -> None:
    database = Database(governed_repo / ".aios/state/state.db")
    database.migrate()
    manager = WorktreeManager(governed_repo, database=database)
    manager.prepare(name="hook-check")
    worktree = governed_repo / ".worktrees/hook-check"
    assert authorize_hook_payload(payload(worktree, "Bash", "git reset --hard")) == {}
    for command in ("git push --force origin main", f'git -C "{governed_repo}" reset --hard'):
        assert (
            authorize_hook_payload(payload(worktree, "Bash", command))["hookSpecificOutput"][
                "permissionDecision"
            ]
            == "deny"
        )
    for tool, command in (
        ("apply_patch", "*** Update File: docs/memory/memory.jsonl\n+x"),
        ("Bash", "echo x > docs/memory/memory.jsonl"),
    ):
        assert (
            authorize_hook_payload(payload(worktree, tool, command))["hookSpecificOutput"][
                "permissionDecision"
            ]
            == "deny"
        )
    manager.cleanup(name="hook-check")
