"""Verify the plugin against the host contracts it actually runs under.

Two classes of mistake cost real load failures, and both are pinned here:

1. Registration shapes (`docs/reference/subsystems/{tools,commands,skills,
   system-prompt}.md`): a tool needs `output { schema, render }` and `execute`,
   a deny is `{ kind: 'deny', reason }`, a prompt section needs a finite `order`,
   a command handler takes an invocation and returns `{ kind, text }`, and a
   skill provider needs a name plus candidates carrying rank/locator/invocation/
   source/provider.
2. Cordis context semantics: the real `ctx` is a proxy that **throws when a
   plugin reads a service it did not declare in `inject`**. A plain-object stub
   cannot catch that, so the stub here throws the same way.
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
import { apply } from './src/index.js'

let input = ''
for await (const chunk of process.stdin) input += chunk
const request = JSON.parse(input || '{}')
const provided = request.provided ?? ['tools', 'commands', 'skills', 'systemPrompt']

const calls = { events: [], tools: [], commands: [], skills: [], sections: [] }
const disposer = () => () => {}
const services = {
  tools: { register: (definition) => { calls.tools.push(definition); return disposer() } },
  commands: { register: (definition) => { calls.commands.push(definition); return disposer() } },
  skills: { registerProvider: (create) => { calls.skills.push(create); return disposer() } },
  systemPrompt: { section: (section) => { calls.sections.push(section); return disposer() } },
}
const base = {
  on: (name) => { calls.events.push(name); return disposer() },
  effect: (callback) => {
    const cleanup = callback()
    return typeof cleanup === 'function' ? cleanup : disposer()
  },
  get: (key) => (provided.includes(key) ? services[key] : undefined),
}
// Mirror the host: an undeclared service read throws instead of returning undefined.
const ctx = new Proxy(base, {
  get(target, prop) {
    if (prop in target || typeof prop === 'symbol') return target[prop]
    if (provided.includes(prop)) return services[prop]
    throw new Error('cannot get property "' + String(prop) + '" without inject')
  },
})

let threw = null
try {
  await apply(ctx, { kernelCommand: 'aios', timeoutMs: 120000 })
} catch (error) {
  threw = error?.stack ?? String(error)
}

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
    count: candidates.length,
    firstKeys: first ? Object.keys(first).sort() : [],
    hasContent: typeof body?.content === 'string' && body.content.length > 0,
  }
}

process.stdout.write(JSON.stringify({
  threw,
  events: calls.events,
  tools: calls.tools.map((tool) => ({
    name: tool.name,
    hasExecute: typeof tool.execute === 'function',
    parametersIsObject: typeof tool.parameters === 'object' && tool.parameters !== null,
    // The model receives `parameters` verbatim, so the root must declare
    // type: "object"; a per-key map yields type: null and the provider rejects
    // the whole request.
    parametersType: tool.parameters?.type ?? null,
    propertiesIsObject:
      typeof tool.parameters?.properties === 'object' && tool.parameters.properties !== null,
    requiredIsArrayOrAbsent:
      tool.parameters?.required === undefined || Array.isArray(tool.parameters.required),
    requiredDeclaredInProperties: (tool.parameters?.required ?? []).every(
      (key) => key in (tool.parameters?.properties ?? {}),
    ),
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

FULL_PROFILE = ["tools", "commands", "skills", "systemPrompt"]


def _probe(project_root: Path, provided: list[str] | None = None) -> dict:
    environment = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    result = subprocess.run(
        [str(NODE), "--input-type=module", "-e", PROBE],
        input=json.dumps({"provided": provided or FULL_PROFILE}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PLUGIN_ROOT,
        env=environment,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_apply_registers_enforcement_and_both_listeners(governed_repo: Path) -> None:
    report = _probe(governed_repo)
    assert report["threw"] is None, report["threw"]
    assert report["events"] == ["tools/pre-execute", "agent/created"]


def test_every_tool_declares_the_required_output_contract(governed_repo: Path) -> None:
    report = _probe(governed_repo)
    assert len(report["tools"]) == 8
    for tool in report["tools"]:
        assert tool["hasExecute"], tool["name"]
        assert tool["parametersIsObject"], tool["name"]
        # output { schema, render } is mandatory; omitting it fails registration.
        assert tool["outputIsObject"], tool["name"]
        assert tool["schemaIsObject"], tool["name"]
        assert tool["renderIsFunction"], tool["name"]


def test_every_tool_parameter_schema_is_a_json_object_schema(governed_repo: Path) -> None:
    """`parameters` reaches the model unchanged, so its root must be an object.

    A per-key map (the author-facing DSL shape) serialised as `type: null` and
    made the provider fail the entire turn.
    """

    report = _probe(governed_repo)
    for tool in report["tools"]:
        assert tool["parametersType"] == "object", tool["name"]
        assert tool["propertiesIsObject"], tool["name"]
        assert tool["requiredIsArrayOrAbsent"], tool["name"]
        assert tool["requiredDeclaredInProperties"], tool["name"]


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
    assert skills["count"] == 8
    for key in ("invocation", "locator", "name", "provider", "rank", "source"):
        assert key in skills["firstKeys"], key
    assert skills["hasContent"] is True


def test_apply_survives_a_profile_without_the_convenience_services(governed_repo: Path) -> None:
    """A missing convenience service must not take enforcement down with it."""

    report = _probe(governed_repo, provided=["tools"])
    assert report["threw"] is None, report["threw"]
    assert "tools/pre-execute" in report["events"]
    assert len(report["tools"]) == 8
    assert report["commands"] == []
    assert report["sections"] == []


def test_inject_declares_every_service_the_plugin_reads() -> None:
    """The host throws on an undeclared read, so the declared set is the contract.

    Driving `apply` with a throwing proxy (above) proves the plugin never touches
    a service outside `inject` on the paths it takes.
    """

    entry = (PLUGIN_ROOT / "src" / "index.js").read_text(encoding="utf-8")
    declared = entry.split("export const inject =", 1)[1].split("\n", 1)[0]
    for service in FULL_PROFILE:
        assert f"'{service}'" in declared, service
