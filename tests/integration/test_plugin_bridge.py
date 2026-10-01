"""Exercise the DSH plugin's own bridge logic through Node.

The Cordis registration surfaces can only be confirmed inside a running host,
but the plugin's decision path is ordinary JavaScript and is verified here:
payload normalization, the kernel subprocess call, and fail-closed behaviour when
the kernel cannot answer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "plugins" / "ai-engineering-os"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node.js is required to probe the plugin")

PROBE = """
import { adjudicate } from './src/kernel.js'
import { sessionPayload, toolPayload } from './src/payload.js'

let input = ''
for await (const chunk of process.stdin) input += chunk
const request = JSON.parse(input || '{}')
const settings = {
  kernelCommand: 'aios',
  timeoutMs: 30000,
  failMode: 'closed',
  ...(request.settings ?? {}),
}
const payload =
  request.tool === undefined && request.event === 'agent/created'
    ? sessionPayload({ cwd: request.cwd })
    : toolPayload({ tool: request.tool, args: request.args ?? {}, cwd: request.cwd })
const decision = await adjudicate(payload, settings)
process.stdout.write(JSON.stringify(decision))
"""


def _adjudicate(project_root: Path, request: dict[str, object]) -> dict[str, object]:
    environment = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    result = subprocess.run(
        [str(NODE), "--input-type=module", "-e", PROBE],
        input=json.dumps({**request, "cwd": str(project_root)}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PLUGIN_ROOT,
        env=environment,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_non_mutating_tool_defers_to_the_host(governed_repo: Path) -> None:
    decision = _adjudicate(governed_repo, {"tool": "read", "args": {"file_path": "input/x"}})
    assert decision["decision"] == "allow"
    assert decision["rule_id"] == "OUTSIDE_AIOS_SCOPE"


def test_force_push_is_denied_by_the_kernel(governed_repo: Path) -> None:
    decision = _adjudicate(
        governed_repo, {"tool": "pwsh", "args": {"command": "git push --force origin main"}}
    )
    assert decision["decision"] == "deny"
    assert decision["rule_id"]


def test_protected_write_is_denied_by_the_kernel(governed_repo: Path) -> None:
    decision = _adjudicate(
        governed_repo, {"tool": "write", "args": {"file_path": "input/asset.txt"}}
    )
    assert decision["decision"] == "deny"


def test_documentation_write_is_allowed(governed_repo: Path) -> None:
    decision = _adjudicate(
        governed_repo, {"tool": "write", "args": {"file_path": "docs/note.md"}}
    )
    assert decision["decision"] == "allow"


def test_missing_kernel_fails_closed_for_mutating_work(governed_repo: Path) -> None:
    decision = _adjudicate(
        governed_repo,
        {
            "tool": "write",
            "args": {"file_path": "docs/note.md"},
            "settings": {"kernelCommand": "aios-does-not-exist"},
        },
    )
    assert decision["decision"] == "deny"
    assert decision["rule_id"] == "AIOS_RUNTIME_UNAVAILABLE"


def test_missing_kernel_only_reports_for_reads(governed_repo: Path) -> None:
    decision = _adjudicate(
        governed_repo,
        {
            "tool": "read",
            "args": {"file_path": "docs/note.md"},
            "settings": {"kernelCommand": "aios-does-not-exist"},
        },
    )
    assert decision["decision"] == "allow"
    assert decision["rule_id"] == "AIOS_RUNTIME_UNAVAILABLE"


def test_session_context_comes_from_the_kernel(governed_repo: Path) -> None:
    decision = _adjudicate(governed_repo, {"event": "agent/created"})
    assert decision["decision"] == "allow"
    assert decision["rule_id"] == "SESSION_CONTEXT"
    assert "AGENTS.md" in str(decision["reason"])
