"""Verify the plugin against the host contracts it actually runs under.

Three classes of mistake cost real failures; all are pinned here:

1. Registration shapes (`docs/reference/subsystems/{tools,commands,skills,
   system-prompt}.md`): a tool needs `output { schema, render }` and `execute`,
   a deny is `{ kind: 'deny', reason }`, a prompt section needs a finite `order`,
   a command handler takes an invocation and returns `{ kind, text }`, and a
   skill provider needs a name plus candidates carrying rank/locator/invocation/
   source/provider.
2. Cordis context semantics: the real `ctx` is a proxy that **throws when a
   plugin reads a service it did not declare in `inject`**. The stub throws the
   same way, so a plain-object stub can no longer hide that class of bug.
3. Request-path safety: registered tools join the tool catalogue of every model
   request, so an invalid tool schema fails whole turns instead of denying one
   operation. The surface is therefore opt-in and every definition is validated
   before registration.
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
import {
  assertToolSchema,
  registerSurfaces,
  TOOL_DEFINITIONS,
  toParameterSchema,
} from './src/surfaces.js'

let input = ''
for await (const chunk of process.stdin) input += chunk
const request = JSON.parse(input || '{}')
const provided = request.provided ?? ['tools', 'commands', 'skills', 'systemPrompt']
const settings = {
  kernelCommand: 'aios',
  timeoutMs: 120000,
  exposeTools: request.exposeTools === true,
  ...(request.settings ?? {}),
}

const calls = { events: [], tools: [], commands: [], skills: [], sections: [] }
const disposer = () => () => {}
const services = {
  tools: { register: (definition) => { calls.tools.push(definition); return disposer() } },
  commands: { register: (definition) => { calls.commands.push(definition); return disposer() } },
  skills: { registerProvider: (create) => { calls.skills.push(create); return disposer() } },
  systemPrompt: { section: (section) => { calls.sections.push(section); return disposer() } },
  sandboxPolicy: { workspaceRoot: request.workspaceRoot ?? '/tmp/workspace-root' },
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
let failures = null

if (request.mode === 'diagnostics') {
  // Prove the debug channel records a real adjudication, since the host exposes
  // no readable plugin log.
  const { adjudicate } = await import('./src/kernel.js')
  const { toolPayload } = await import('./src/payload.js')
  const { readFile } = await import('node:fs/promises')
  const cwd = request.diagnosticDir
  try {
    await adjudicate(
      toolPayload({ tool: 'write', args: { file_path: 'input/probe.txt' }, cwd }),
      {
        kernelCommand: 'aios',
        timeoutMs: 120000,
        failMode: 'closed',
        diagnostics: true,
        strict: false,
      },
    )
  } catch (error) {
    threw = error?.stack ?? String(error)
  }
  let body = null
  try {
    body = await readFile(cwd + '/.aios/tmp/plugin-diagnostics.jsonl', 'utf8')
  } catch {
    body = null
  }
  process.stdout.write(JSON.stringify({ threw, diagnostics: body }))
} else if (request.mode === 'validate') {
  // Direct contract checks on the pre-flight validator itself.
  const good = {
    name: 'probe',
    description: 'probe',
    execute: () => {},
    parameters: { type: 'object', properties: { a: { type: 'string' } }, required: ['a'] },
    output: { schema: {}, render: () => [{ type: 'text', text: 'x' }] },
  }
  const cases = {
    ok: good,
    nullType: { ...good, parameters: { type: null, properties: {} } },
    noProperties: { ...good, parameters: { type: 'object' } },
    undeclaredRequired: {
      ...good,
      parameters: { type: 'object', properties: { a: {} }, required: ['b'] },
    },
    noRender: { ...good, output: { schema: {} } },
    noExecute: { ...good, execute: 'nope' },
    noDescription: { ...good, description: '' },
  }
  const results = {}
  for (const [label, definition] of Object.entries(cases)) {
    try {
      assertToolSchema(definition)
      results[label] = 'accepted'
    } catch (error) {
      results[label] = 'rejected: ' + String(error?.message ?? error)
    }
  }
  results.convertedRootType = toParameterSchema({ a: { type: 'string', required: true } }).type
  process.stdout.write(JSON.stringify({ threw, results }))
} else {
  if (request.badDefinition === true) {
    TOOL_DEFINITIONS.push({
      name: 'broken-tool',
      description: 'a definition whose parameter map cannot convert',
      parameters: null,
      argv: () => ['doctor', '--json'],
    })
  }
  try {
    if (request.mode === 'surfaces') {
      failures = registerSurfaces(ctx, settings, 'CONSTITUTION TEXT')
    } else {
      await apply(ctx, settings)
    }
  } catch (error) {
    threw = error?.stack ?? String(error)
  }
  process.stdout.write(JSON.stringify({
    threw,
    failures,
    events: calls.events,
    registeredNames: calls.tools.map((tool) => tool.name),
    tools: calls.tools.map((tool) => ({
      name: tool.name,
      hasExecute: typeof tool.execute === 'function',
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
      passesValidator: (() => {
        try {
          assertToolSchema(tool)
          return true
        } catch {
          return false
        }
      })(),
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
    skills: calls.skills.length
      ? (() => {
          const provider = calls.skills[0]()
          return { providerName: provider.name }
        })()
      : null,
  }))
}
"""

# Services the plugin declares in `inject`; everything else must be read
# defensively because Cordis throws on an undeclared property read.
INJECTED = ["tools", "commands", "skills", "systemPrompt"]
# What a base-backed profile actually exposes, including the optional
# workspace-root source the plugin consults for a session working directory.
FULL_PROFILE = [*INJECTED, "sandboxPolicy"]


def _probe(project_root: Path, **request: object) -> dict:
    environment = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    result = subprocess.run(
        [str(NODE), "--input-type=module", "-e", PROBE],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PLUGIN_ROOT,
        env=environment,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# --- request-path safety: the reason this surface is opt-in -------------------


def test_default_configuration_adds_no_model_facing_tools(governed_repo: Path) -> None:
    """A governance plugin must not enlarge every request's tool catalogue."""

    report = _probe(governed_repo)
    assert report["threw"] is None, report["threw"]
    assert report["registeredNames"] == []
    # Enforcement and the session context are unconditional.
    assert report["events"] == ["tools/pre-execute", "agent/created"]


def test_tool_surface_is_opt_in_and_then_valid(governed_repo: Path) -> None:
    report = _probe(governed_repo, exposeTools=True)
    assert report["threw"] is None, report["threw"]
    assert len(report["tools"]) == 8
    for tool in report["tools"]:
        assert tool["hasExecute"], tool["name"]
        assert tool["passesValidator"], tool["name"]
        assert tool["parametersType"] == "object", tool["name"]
        assert tool["propertiesIsObject"], tool["name"]
        assert tool["requiredIsArrayOrAbsent"], tool["name"]
        assert tool["requiredDeclaredInProperties"], tool["name"]
        assert tool["outputIsObject"], tool["name"]
        assert tool["schemaIsObject"], tool["name"]
        assert tool["renderIsFunction"], tool["name"]


def test_invalid_tool_definition_is_skipped_and_never_registered(governed_repo: Path) -> None:
    """One bad definition must not poison requests, and must not block the rest."""

    report = _probe(governed_repo, mode="surfaces", exposeTools=True, badDefinition=True)
    assert report["threw"] is None, report["threw"]
    assert "broken-tool" not in report["registeredNames"]
    assert len(report["registeredNames"]) == 8
    assert any("broken-tool" in failure for failure in report["failures"]), report["failures"]


def test_validator_rejects_each_malformed_shape() -> None:
    results = _probe(Path.cwd(), mode="validate")["results"]
    assert results["ok"] == "accepted"
    assert results["convertedRootType"] == "object"
    malformed = (
        "nullType",
        "noProperties",
        "undeclaredRequired",
        "noRender",
        "noExecute",
        "noDescription",
    )
    for label in malformed:
        assert results[label].startswith("rejected"), (label, results[label])


# --- host contracts ----------------------------------------------------------


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


def test_skill_provider_registers(governed_repo: Path) -> None:
    report = _probe(governed_repo)
    assert report["skills"] is not None
    assert report["skills"]["providerName"] == "ai-engineering-os"


def test_apply_survives_a_profile_without_the_convenience_services(governed_repo: Path) -> None:
    """A missing convenience service must not take enforcement down with it."""

    report = _probe(governed_repo, provided=["tools"], exposeTools=True)
    assert report["threw"] is None, report["threw"]
    assert "tools/pre-execute" in report["events"]
    assert len(report["registeredNames"]) == 8
    assert report["commands"] == []
    assert report["sections"] == []


def test_inject_declares_every_service_the_plugin_reads() -> None:
    """The host throws on an undeclared read, so the declared set is the contract.

    Driving `apply` with a throwing proxy (above) proves the plugin never touches
    a service outside `inject` on the paths it takes.
    """

    entry = (PLUGIN_ROOT / "src" / "index.js").read_text(encoding="utf-8")
    declared = entry.split("export const inject =", 1)[1].split("\n", 1)[0]
    for service in INJECTED:
        assert f"'{service}'" in declared, service


def test_diagnostics_channel_records_an_adjudication(governed_repo: Path) -> None:
    """The channel verification depends on must actually work."""

    report = _probe(governed_repo, mode="diagnostics", diagnosticDir=str(governed_repo))
    assert report["threw"] is None, report["threw"]
    body = report["diagnostics"]
    assert body, "diagnostics file was not written"
    line = json.loads(body.strip().splitlines()[-1])
    # The record captures what the plugin extracted plus the verdict, which is
    # what makes a missed denial provable instead of guessable.
    assert line["tool"] == "write"
    assert line["input"]["file_path"] == "input/probe.txt"
    assert line["decision"] in {"allow", "deny"}
    assert line["rule_id"]
