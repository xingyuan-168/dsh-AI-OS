"""Verify the plugin's surface registrations against the published contracts.

The Cordis registration shapes were the one part an offline environment could
not check, and getting them wrong cost a load failure. This probe drives
`registerSurfaces` with a stub context and asserts every registered shape against
docs/reference/subsystems/{tools,commands,skills,system-prompt}.md, so the
contract is pinned rather than rediscovered in the host log.
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
import { registerSurfaces } from './src/surfaces.js'

const calls = { tools: [], commands: [], skills: [], sections: [] }
const disposer = () => () => {}
const ctx = {
  tools: { register: (definition) => { calls.tools.push(definition); return disposer() } },
  commands: { register: (definition) => { calls.commands.push(definition); return disposer() } },
  skills: { registerProvider: (create) => { calls.skills.push(create); return disposer() } },
  systemPrompt: { section: (section) => { calls.sections.push(section); return disposer() } },
  effect: (callback) => {
    const cleanup = callback()
    return typeof cleanup === 'function' ? cleanup : disposer()
  },
}

const failures = registerSurfaces(
  ctx,
  { kernelCommand: 'aios', timeoutMs: 120000 },
  'CONSTITUTION TEXT',
)

// Exercise one tool end to end through the stub so the wiring is proven, not
// just the shape: execute() must return the kernel envelope and render() must
// turn it into a text content block.
const status = calls.tools.find((tool) => tool.name === 'context_refresh')
let executed = null
let rendered = null
if (status) {
  try {
    executed = await status.execute({ project_root: process.cwd() })
    rendered = status.output.render({}, executed)
  } catch (error) {
    executed = { threw: String(error) }
  }
}

let skills = null
if (calls.skills.length > 0) {
  const provider = calls.skills[0]()
  const candidates = await provider.list({})
  const first = candidates[0]
  const body = first ? await provider.get(first, {}) : null
  skills = {
    providerName: provider.name,
    listIsArray: Array.isArray(candidates),
    count: candidates.length,
    firstKeys: first ? Object.keys(first).sort() : [],
    hasContent: typeof body?.content === 'string' && body.content.length > 0,
  }
}

process.stdout.write(JSON.stringify({
  failures,
  tools: calls.tools.map((tool) => ({
    name: tool.name,
    hasExecute: typeof tool.execute === 'function',
    hasParameters: typeof tool.parameters === 'object' && tool.parameters !== null,
    outputIsObject: typeof tool.output === 'object' && tool.output !== null,
    schemaIsObject: typeof tool.output?.schema === 'object' && tool.output.schema !== null,
    renderIsFunction: typeof tool.output?.render === 'function',
  })),
  commands: calls.commands.map((command) => ({
    name: command.name,
    handlerIsFunction: typeof command.handler === 'function',
  })),
  sections: calls.sections.map((section) => ({
    name: section.name,
    orderIsFinite: Number.isFinite(section.order),
    textIsString: typeof section.text === 'string',
  })),
  executed,
  rendered,
  skills,
}))
"""


def _probe(project_root: Path) -> dict:
    environment = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    result = subprocess.run(
        [str(NODE), "--input-type=module", "-e", PROBE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PLUGIN_ROOT,
        env=environment,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_surfaces_register_without_failures(governed_repo: Path) -> None:
    report = _probe(governed_repo)
    assert report["failures"] == []


def test_every_tool_declares_the_required_output_contract(governed_repo: Path) -> None:
    report = _probe(governed_repo)
    assert len(report["tools"]) == 8
    for tool in report["tools"]:
        assert tool["hasExecute"], tool["name"]
        assert tool["hasParameters"], tool["name"]
        # output { schema, render } is mandatory; omitting it fails registration.
        assert tool["outputIsObject"], tool["name"]
        assert tool["schemaIsObject"], tool["name"]
        assert tool["renderIsFunction"], tool["name"]


def test_a_tool_executes_through_the_kernel_and_renders_text(governed_repo: Path) -> None:
    report = _probe(governed_repo)
    executed = report["executed"]
    assert executed is not None and "threw" not in executed, executed
    assert executed["ok"] is True, executed
    rendered = report["rendered"]
    assert isinstance(rendered, list) and rendered, rendered
    assert rendered[0]["type"] == "text"
    assert isinstance(rendered[0]["text"], str) and rendered[0]["text"]


def test_commands_register_with_an_invocation_handler(governed_repo: Path) -> None:
    report = _probe(governed_repo)
    assert [command["name"] for command in report["commands"]] == [
        "aios-check",
        "aios-status",
        "aios-memory",
    ]
    for command in report["commands"]:
        assert command["handlerIsFunction"], command["name"]


def test_prompt_section_declares_a_finite_order(governed_repo: Path) -> None:
    report = _probe(governed_repo)
    assert len(report["sections"]) == 1
    section = report["sections"][0]
    assert section["name"] == "ai-engineering-os"
    # A non-finite order throws at registration time.
    assert section["orderIsFinite"] is True
    assert section["textIsString"] is True


def test_skill_provider_exposes_candidates_and_bodies(governed_repo: Path) -> None:
    report = _probe(governed_repo)
    skills = report["skills"]
    assert skills is not None
    assert skills["providerName"] == "ai-engineering-os"
    assert skills["listIsArray"] is True
    assert skills["count"] == 8
    for key in ("invocation", "locator", "name", "provider", "rank", "source"):
        assert key in skills["firstKeys"], key
    assert skills["hasContent"] is True
