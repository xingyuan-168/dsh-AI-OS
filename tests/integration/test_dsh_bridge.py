"""The DSH bridge contract: `aios authorize-dsh` over a real stdio pipe.

The Cordis plugin depends on exactly this: one JSON payload in, one decision
out, exit 0 whenever a decision exists. A non-zero exit means the payload could
not be adjudicated, which the plugin must treat as fail-closed for mutating
operations.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run(payload: object, cwd: Path, *, raw: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "aios", "authorize-dsh"],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        timeout=120,
    )


@pytest.mark.parametrize(
    "event,decision",
    [
        ({"event": "agent/created"}, "allow"),
        ({"event": "fs/write-intent", "input": {"file_path": "input/asset.txt"}}, "deny"),
        ({"event": "fs/edit-intent", "input": {"file_path": "AGENTS.md"}}, "deny"),
        ({"event": "fs/write-intent", "input": {"file_path": "docs/note.md"}}, "allow"),
        (
            {"event": "tools/pre-execute", "tool": "pwsh", "input": {"command": "pytest tests"}},
            "allow",
        ),
        (
            {
                "event": "tools/pre-execute",
                "tool": "pwsh",
                "input": {"command": "git push --force origin main"},
            },
            "deny",
        ),
        (
            {"event": "tools/pre-execute", "tool": "read", "input": {"file_path": "input/x"}},
            "allow",
        ),
    ],
)
def test_bridge_returns_a_decision_for_every_governed_event(
    governed_repo: Path, event: dict[str, object], decision: str
) -> None:
    result = _run({**event, "cwd": str(governed_repo)}, governed_repo)
    assert result.returncode == 0, result.stderr
    outcome = json.loads(result.stdout)
    assert outcome["decision"] == decision
    assert outcome["rule_id"]


def test_bridge_denies_formal_source_write_without_github(governed_repo: Path) -> None:
    payload = {
        "event": "fs/write-intent",
        "cwd": str(governed_repo),
        "input": {"file_path": "src/module.py"},
    }
    outcome = json.loads(_run(payload, governed_repo).stdout)
    assert outcome["decision"] == "deny"
    assert outcome["rule_id"] == "CODE_START_BLOCKED"


def test_unreadable_payload_exits_nonzero(governed_repo: Path) -> None:
    result = _run(None, governed_repo, raw="not json")
    assert result.returncode != 0


def test_bridge_is_diagnostic_and_creates_nothing(governed_repo: Path) -> None:
    payload = {
        "event": "fs/write-intent",
        "cwd": str(governed_repo),
        "input": {"file_path": "docs/only-checked.md"},
    }
    assert json.loads(_run(payload, governed_repo).stdout)["decision"] == "allow"
    assert not (governed_repo / "docs/only-checked.md").exists()
