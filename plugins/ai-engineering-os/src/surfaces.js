/**
 * The eight governance tools, the human commands, the skill catalogue, and the
 * constitution section — registered on whichever surfaces the host exposes.
 *
 * Every registration is delegated to the `aios` kernel, so nothing here can
 * disagree with the CLI or the MCP server. Each surface is registered inside its
 * own guard: the pre-dispatch enforcement listener must keep working even if an
 * optional surface rejects a shape, because losing enforcement to a broken
 * command would be the worst possible failure mode.
 *
 * Shapes follow the published host contracts
 * (docs/reference/subsystems/{tools,commands,skills,system-prompt}.md):
 *   - tool: { name, description, parameters, output: { schema, render }, execute }
 *     where `parameters` must already be a JSON Schema of `type: "object"`,
 *     because it is forwarded to the model unchanged. The whole tool surface is
 *     opt-in (`exposeTools`), and every definition is validated before
 *     registration so a bad schema can never reach a request.
 *   - command: { name, description, handler(invocation) -> { kind, text } }
 *   - prompt section: { name, order, text }
 *   - skill provider: { name, list(options), get(candidate, options) }
 */

import { spawn } from 'node:child_process'
import { readdir, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
export const SKILLS_DIRECTORY = join(HERE, '..', 'skills')

// Placement for the constitution section. The centrally allocated names live in
// the host's own enum; a plugin-owned section picks an explicit finite order.
const SECTION_ORDER = 500

// Skill rank: lower wins inside one registry layer. These are plugin-bundled
// instructions, so they sit below project-local skills.
const SKILL_RANK = 50
const SKILL_NAME_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

/** Tool name -> `aios` argv builder. Argument names mirror the MCP contract. */
export const TOOL_DEFINITIONS = [
  {
    name: 'project_init',
    description:
      'Initialize a governed project: configuration, minimal documents, runtime database.',
    parameters: {
      project_root: { type: 'string', description: 'Project root to create.', required: true },
      project_id: { type: 'string', description: 'Stable id, e.g. PROJECT-001.', required: true },
      name: { type: 'string', description: 'Human-readable project name.', required: true },
      project_type: {
        type: 'string',
        description: 'backend | frontend | fullstack | desktop | generic',
      },
    },
    argv: (args) => [
      'init',
      String(args.project_root),
      '--project-id',
      String(args.project_id),
      '--name',
      String(args.name),
      ...(args.project_type ? ['--project-type', String(args.project_type)] : []),
      '--json',
    ],
  },
  {
    name: 'governance_check',
    description:
      'Run one stateless gate (start, frontend, or finish) and return allowed plus findings.',
    parameters: {
      project_root: {
        type: 'string',
        description: 'Project root, subdirectory, or worktree.',
        required: true,
      },
      stage: { type: 'string', description: 'start | frontend | finish', required: true },
      change_class: { type: 'string', description: 'Required for formal code changes.' },
      requirement_id: { type: 'string', description: 'Research-required classes only.' },
      base_ref: { type: 'string', description: 'Task-start commit; required for finish.' },
      test_command: { type: 'string', description: 'Declared test command to run at finish.' },
      memory_written: { type: 'boolean', description: 'Durable memory was recorded.' },
      memory_not_needed: { type: 'boolean', description: 'Nothing durable was learned.' },
    },
    argv: (args) => [
      args.stage === 'finish' ? 'finish' : 'check',
      String(args.project_root),
      ...(args.change_class ? ['--change-class', String(args.change_class)] : []),
      ...(args.requirement_id ? ['--requirement-id', String(args.requirement_id)] : []),
      ...(args.test_command ? ['--test-command', String(args.test_command)] : []),
      ...(args.base_ref ? ['--base-ref', String(args.base_ref)] : []),
      ...(args.memory_written ? ['--memory-written'] : []),
      ...(args.memory_not_needed ? ['--memory-not-needed'] : []),
      '--json',
    ],
  },
  {
    name: 'approval_record',
    description:
      'Record a user approval or rejection for a gate; a frontend decision is written into UI_SPEC.md.',
    parameters: {
      project_root: { type: 'string', description: 'Project root.', required: true },
      gate: { type: 'string', description: 'code_start | frontend | finish', required: true },
      subject: { type: 'string', description: 'What the user approved.', required: true },
      decided_by: { type: 'string', description: 'Who decided.', required: true },
      decision: { type: 'string', description: 'approved | rejected' },
      scope: { type: 'string', description: 'Exact scope; scopes never inherit.' },
      reason: { type: 'string', description: 'Optional reason.' },
    },
    argv: (args) => [
      'approval',
      'record',
      String(args.project_root),
      '--gate',
      String(args.gate),
      '--subject',
      String(args.subject),
      '--decided-by',
      String(args.decided_by),
      '--decision',
      String(args.decision ?? 'approved'),
      '--scope',
      String(args.scope ?? 'default'),
      ...(args.reason ? ['--reason', String(args.reason)] : []),
      '--json',
    ],
  },
  {
    name: 'context_refresh',
    description: 'Regenerate the derived PROJECT_CONTEXT.md cache.',
    parameters: {
      project_root: { type: 'string', description: 'Project root.', required: true },
    },
    argv: (args) => ['context', 'refresh', String(args.project_root), '--json'],
  },
  {
    name: 'worktree_manage',
    description: 'Disposable worktree lifecycle: prepare, check, finish, cleanup, or list.',
    parameters: {
      project_root: { type: 'string', description: 'Project root.', required: true },
      action: {
        type: 'string',
        description: 'prepare | check | finish | cleanup | list',
        required: true,
      },
      name: { type: 'string', description: 'Worktree slug.' },
      task_id: { type: 'string', description: 'Optional task id.' },
    },
    argv: (args) => [
      'worktree',
      String(args.action),
      String(args.project_root),
      ...(args.name ? ['--name', String(args.name)] : []),
      ...(args.task_id ? ['--task-id', String(args.task_id)] : []),
      '--json',
    ],
  },
  {
    name: 'memory_search',
    description: 'Refresh the index from the Git-tracked JSONL and search durable memory.',
    parameters: {
      project_root: { type: 'string', description: 'Project root.', required: true },
      query: { type: 'string', description: 'Search query.', required: true },
      limit: { type: 'number', description: 'Maximum hits.' },
    },
    argv: (args) => [
      'memory',
      'search',
      String(args.query),
      String(args.project_root),
      ...(args.limit ? ['--limit', String(args.limit)] : []),
      '--json',
    ],
  },
  {
    name: 'memory_record',
    description: 'Write one durable record, or submit a candidate from a subagent.',
    parameters: {
      project_root: { type: 'string', description: 'Project root.', required: true },
      record_type: {
        type: 'string',
        description: 'decision | bug | lesson | pattern',
        required: true,
      },
      title: { type: 'string', description: 'Record title.', required: true },
      summary: { type: 'string', description: 'What was learned.', required: true },
      source: { type: 'string', description: 'Source path or URL.', required: true },
      candidate: { type: 'boolean', description: 'Submit as a subagent candidate.' },
    },
    argv: (args) => [
      'memory',
      'record',
      '--project-root',
      String(args.project_root),
      '--type',
      String(args.record_type),
      '--title',
      String(args.title),
      '--summary',
      String(args.summary),
      '--source',
      String(args.source),
      ...(args.candidate ? ['--candidate'] : []),
      '--json',
    ],
  },
  {
    name: 'memory_candidate',
    description: 'List, accept, or reject a subagent memory candidate.',
    parameters: {
      project_root: { type: 'string', description: 'Project root.', required: true },
      action: { type: 'string', description: 'list | accept | reject', required: true },
      candidate_id: { type: 'string', description: 'Candidate id for accept/reject.' },
    },
    argv: (args) => [
      'memory',
      'candidate',
      String(args.candidate_id ?? ''),
      ...(args.action === 'accept' ? ['--accept'] : []),
      ...(args.action === 'reject' ? ['--reject'] : []),
      '--project-root',
      String(args.project_root),
      '--json',
    ],
  },
]

export const COMMAND_DEFINITIONS = [
  {
    name: 'aios-check',
    description: 'Preview governance blockers for the current directory.',
    argv: ['check', '.', '--json'],
  },
  {
    name: 'aios-status',
    description: 'Report AI Engineering OS runtime diagnostics.',
    argv: ['doctor', '--json'],
  },
  {
    name: 'aios-memory',
    description: 'List pending memory candidates.',
    argv: ['memory', 'candidates', '.', '--json'],
  },
]

export function runAios(command, argv, timeoutMs) {
  return new Promise((resolve) => {
    let settled = false
    const finish = (value) => {
      if (!settled) {
        settled = true
        resolve(value)
      }
    }
    let child
    try {
      child = spawn(command, argv, { stdio: ['ignore', 'pipe', 'pipe'] })
    } catch (error) {
      finish({ ok: false, error: String(error) })
      return
    }
    const timer = setTimeout(() => {
      child.kill()
      finish({ ok: false, error: `aios ${argv[0]} exceeded its ${timeoutMs}ms budget` })
    }, timeoutMs)
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => {
      stdout += chunk
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk
    })
    child.on('error', (error) => {
      clearTimeout(timer)
      finish({ ok: false, error: String(error) })
    })
    child.on('close', () => {
      clearTimeout(timer)
      try {
        finish({ ok: true, result: JSON.parse(stdout) })
      } catch {
        finish({ ok: false, error: stderr.trim() || 'aios returned unreadable output' })
      }
    })
  })
}

/** Read the kebab-case name and description out of one SKILL.md frontmatter. */
function parseSkill(name, body) {
  const match = /^---\s*\n([\s\S]*?)\n---/.exec(body)
  const description = match ? /^description:\s*(.+)$/m.exec(match[1])?.[1]?.trim() : undefined
  return { name, description: description ?? name, body }
}

async function readSkills() {
  let entries = []
  try {
    entries = await readdir(SKILLS_DIRECTORY, { withFileTypes: true })
  } catch {
    return []
  }
  const skills = []
  for (const entry of entries) {
    if (!entry.isDirectory() || !SKILL_NAME_PATTERN.test(entry.name)) continue
    try {
      const body = await readFile(join(SKILLS_DIRECTORY, entry.name, 'SKILL.md'), 'utf8')
      skills.push(parseSkill(entry.name, body))
    } catch {
      // A skill without a readable manifest is skipped, never invented.
    }
  }
  return skills.sort((left, right) => left.name.localeCompare(right.name))
}

/**
 * Read one optional host service without tripping Cordis.
 *
 * Cordis' context is a proxy: reading `ctx.commands` when `commands` was not
 * declared in `inject` throws, so a plain truthiness guard is itself the
 * failure. `ctx.get` is the documented low-level service-store read; the
 * property read remains a fallback for a context that answers only that way.
 * Returns undefined when the service is genuinely absent.
 */
export function optionalService(ctx, key) {
  try {
    const service = ctx.get?.(key)
    if (service) return service
  } catch {
    // Not resolvable through the store; try the declared-property path.
  }
  try {
    return ctx[key]
  } catch {
    return undefined
  }
}

/**
 * Build the model-facing JSON Schema for one tool's arguments.
 *
 * `parameters` is forwarded to the model verbatim, so it must be a JSON Schema
 * whose root declares `type: "object"`. Passing the author-facing per-key map
 * straight through produced `type: null`, and the provider rejected the whole
 * request ("Invalid schema for function ... got 'type: null'"). The per-key maps
 * below stay readable; this converts them.
 */
export function toParameterSchema(parameters = {}) {
  const properties = {}
  const required = []
  for (const [name, spec] of Object.entries(parameters)) {
    const { required: isRequired, ...rest } = spec
    properties[name] = rest
    if (isRequired === true) required.push(name)
  }
  return {
    type: 'object',
    properties,
    ...(required.length > 0 ? { required } : {}),
  }
}

/**
 * Validate one tool definition before it can reach the host.
 *
 * Registration alone is not enough evidence of safety: `parameters` becomes part
 * of every model request, and an invalid schema makes the provider reject the
 * whole turn rather than deny one operation. Everything the model or the runtime
 * depends on is therefore checked here, and a failure drops that tool instead of
 * poisoning requests.
 */
export function assertToolSchema(definition) {
  const fail = (message) => {
    throw new Error(`invalid tool definition for "${definition?.name ?? '?'}": ${message}`)
  }

  if (typeof definition?.name !== 'string' || !definition.name) fail('name must be a non-empty string')
  if (typeof definition?.description !== 'string' || !definition.description) {
    fail('description must be a non-empty string')
  }
  if (typeof definition?.execute !== 'function') fail('execute must be a function')

  const parameters = definition.parameters
  if (!parameters || typeof parameters !== 'object' || Array.isArray(parameters)) {
    fail('parameters must be an object')
  }
  if (parameters.type !== 'object') {
    fail(`parameters.type must be "object", got ${JSON.stringify(parameters.type ?? null)}`)
  }
  const properties = parameters.properties
  if (!properties || typeof properties !== 'object' || Array.isArray(properties)) {
    fail('parameters.properties must be an object')
  }
  if (parameters.required !== undefined) {
    if (!Array.isArray(parameters.required)) fail('parameters.required must be an array')
    for (const key of parameters.required) {
      if (!(key in properties)) fail(`parameters.required lists undeclared key "${key}"`)
    }
  }

  const output = definition.output
  if (!output || typeof output !== 'object') fail('output must be an object')
  if (!output.schema || typeof output.schema !== 'object') fail('output.schema must be an object')
  if (typeof output.render !== 'function') fail('output.render must be a function')
  return definition
}

function registerTools(ctx, settings, failures) {
  if (settings.exposeTools !== true) {
    // Default: contribute nothing to the model-facing tool catalogue.
    return
  }
  const tools = optionalService(ctx, 'tools')
  if (!tools?.register) {
    failures.push('tools: service unavailable')
    return
  }
  for (const definition of TOOL_DEFINITIONS) {
    let validated
    try {
      // Conversion is inside the guard too: a definition whose parameter map
      // cannot be read must be skipped, not allowed to abort the loop.
      const parameters = toParameterSchema(definition.parameters)
      validated = assertToolSchema({
        name: definition.name,
        description: definition.description,
        parameters,
        output: {
          // The kernel's envelope is arbitrary JSON, so the canonical output is
          // declared unconstrained and rendered as text.
          schema: {},
          render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
        },
        execute: async (args = {}) => {
          const outcome = await runAios(
            String(settings.kernelCommand ?? 'aios'),
            definition.argv(args ?? {}),
            Number(settings.timeoutMs ?? 10000),
          )
          if (!outcome.ok) throw new Error(String(outcome.error))
          return outcome.result
        },
      })
    } catch (error) {
      // Skipped, never registered: an invalid schema would fail every request.
      // The tool is named so the log identifies which definition to fix.
      failures.push(`tool ${definition.name}: ${error?.message ?? String(error)}`)
      continue
    }
    try {
      tools.register(validated)
    } catch (error) {
      failures.push(`tool ${definition.name}: ${error?.message ?? String(error)}`)
    }
  }
}

function registerCommands(ctx, settings, failures) {
  const commands = optionalService(ctx, 'commands')
  if (!commands?.register) {
    return
  }
  for (const command of COMMAND_DEFINITIONS) {
    try {
      commands.register({
        name: command.name,
        description: command.description,
        handler: async () => {
          const outcome = await runAios(
            String(settings.kernelCommand ?? 'aios'),
            command.argv,
            Number(settings.timeoutMs ?? 10000),
          )
          if (!outcome.ok) return { kind: 'error', text: String(outcome.error) }
          return { kind: 'success', text: JSON.stringify(outcome.result, null, 2) }
        },
      })
    } catch (error) {
      failures.push(`command ${command.name}: ${error?.message ?? String(error)}`)
    }
  }
}

function registerSkills(ctx, failures) {
  const skills = optionalService(ctx, 'skills')
  if (!skills?.registerProvider) {
    return
  }
  try {
    ctx.effect(() =>
      skills.registerProvider(() => ({
        name: 'ai-engineering-os',
        list: async () =>
          (await readSkills()).map((skill) => ({
            name: skill.name,
            description: skill.description,
            rank: SKILL_RANK,
            locator: skill.name,
            invocation: { modelInvocable: true, userInvocable: false },
            source: 'bundled',
            provider: 'ai-engineering-os',
          })),
        get: async (candidate) => {
          const skill = (await readSkills()).find((item) => item.name === candidate?.name)
          if (!skill) return undefined
          return {
            name: skill.name,
            description: skill.description,
            invocation: { modelInvocable: true, userInvocable: false },
            source: 'bundled',
            provider: 'ai-engineering-os',
            content: skill.body,
          }
        },
      })),
    )
  } catch (error) {
    failures.push(`skills: ${error?.message ?? String(error)}`)
  }
}

function registerPromptSection(ctx, contextText, failures) {
  const systemPrompt = optionalService(ctx, 'systemPrompt')
  if (!systemPrompt?.section) {
    return
  }
  try {
    ctx.effect(() =>
      systemPrompt.section({
        name: 'ai-engineering-os',
        order: SECTION_ORDER,
        text: String(contextText),
      }),
    )
  } catch (error) {
    failures.push(`system prompt section: ${error?.message ?? String(error)}`)
  }
}

export function registerSurfaces(ctx, settings, contextText) {
  const failures = []
  registerTools(ctx, settings, failures)
  registerCommands(ctx, settings, failures)
  registerSkills(ctx, failures)
  registerPromptSection(ctx, contextText, failures)
  if (failures.length > 0) {
    // Loud on purpose: a rejected surface shape must be visible in the host log
    // even though enforcement itself is unaffected.
    console.error('[ai-engineering-os] surface registration failed: ' + failures.join('; '))
  }
  return failures
}
