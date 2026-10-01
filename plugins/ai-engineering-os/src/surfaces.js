/**
 * The eight governance tools, the human commands, the skill catalogue, and the
 * constitution section — registered on whichever surfaces the host exposes.
 *
 * Every registration is guarded: a profile that lacks a surface keeps the
 * others instead of failing to load. All work is delegated to the `aios`
 * kernel, so nothing here can disagree with the CLI or the MCP server.
 *
 * Assumed host contracts (confirm against the installed host types):
 *   - `ctx.tools.register` takes a definition with a name, description,
 *     input schema, and handler.
 *   - `ctx.commands.register`, `ctx.skills.registerProvider`, and
 *     `ctx.systemPrompt.section` take the forms documented by the host.
 * A shape mismatch surfaces as a registration error, never as a silent allow.
 */

import { spawn } from 'node:child_process'
import { readdir, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
export const SKILLS_DIRECTORY = join(HERE, '..', 'skills')

/** Tool name -> `aios` argv prefix. Argument names mirror the MCP contract. */
export const TOOL_DEFINITIONS = [
  {
    name: 'project_init',
    description:
      'Initialize a governed project: configuration, minimal documents, runtime database.',
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
    required: ['project_root', 'project_id', 'name'],
  },
  {
    name: 'governance_check',
    description:
      'Run one stateless gate (start, frontend, or finish) and return allowed plus findings.',
    argv: (args) => [
      args.stage === 'finish' ? 'finish' : 'check',
      String(args.project_root),
      ...(args.change_class ? ['--change-class', String(args.change_class)] : []),
      ...(args.requirement_id ? ['--requirement-id', String(args.requirement_id)] : []),
      ...(args.test_command ? ['--test-command', String(args.test_command)] : []),
      ...(args.base_ref ? ['--base-ref', String(args.base_ref)] : []),
      ...(args.memory_not_needed ? ['--memory-not-needed'] : []),
      '--json',
    ],
    required: ['project_root', 'stage'],
  },
  {
    name: 'approval_record',
    description:
      'Record a user approval or rejection for a gate; a frontend decision is written into UI_SPEC.md.',
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
    required: ['project_root', 'gate', 'subject', 'decided_by'],
  },
  {
    name: 'context_refresh',
    description: 'Regenerate the derived PROJECT_CONTEXT.md cache.',
    argv: (args) => ['context', 'refresh', String(args.project_root), '--json'],
    required: ['project_root'],
  },
  {
    name: 'worktree_manage',
    description: 'Disposable worktree lifecycle: prepare, check, finish, cleanup, or list.',
    argv: (args) => [
      'worktree',
      String(args.action),
      String(args.project_root),
      ...(args.name ? ['--name', String(args.name)] : []),
      ...(args.task_id ? ['--task-id', String(args.task_id)] : []),
      '--json',
    ],
    required: ['project_root', 'action'],
  },
  {
    name: 'memory_search',
    description: 'Refresh the index from the Git-tracked JSONL and search durable memory.',
    argv: (args) => [
      'memory',
      'search',
      String(args.query),
      String(args.project_root),
      ...(args.limit ? ['--limit', String(args.limit)] : []),
      '--json',
    ],
    required: ['project_root', 'query'],
  },
  {
    name: 'memory_record',
    description: 'Write one durable record, or submit a candidate from a subagent.',
    argv: (args) => [
      'memory',
      'record',
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
    required: ['project_root', 'record_type', 'title', 'summary', 'source'],
  },
  {
    name: 'memory_candidate',
    description: 'List, accept, or reject a subagent memory candidate.',
    argv: (args) => [
      'memory',
      'candidate',
      String(args.candidate_id ?? ''),
      ...(args.action === 'accept' ? ['--accept'] : []),
      ...(args.action === 'reject' ? ['--reject'] : []),
      '--json',
    ],
    required: ['action'],
  },
]

export const COMMAND_DEFINITIONS = [
  { name: 'aios-check', argv: ['check', '.', '--json'], description: 'Preview governance blockers.' },
  { name: 'aios-status', argv: ['doctor', '--json'], description: 'Report runtime diagnostics.' },
  {
    name: 'aios-memory',
    argv: ['memory', 'candidates', '.', '--json'],
    description: 'List pending memory candidates.',
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

async function readSkills() {
  let entries = []
  try {
    entries = await readdir(SKILLS_DIRECTORY, { withFileTypes: true })
  } catch {
    return []
  }
  const skills = []
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    try {
      const body = await readFile(join(SKILLS_DIRECTORY, entry.name, 'SKILL.md'), 'utf8')
      skills.push({ name: entry.name, body })
    } catch {
      // A skill without a readable manifest is skipped, never invented.
    }
  }
  return skills
}

export function registerSurfaces(ctx, settings, contextText) {
  if (ctx.tools?.register) {
    for (const definition of TOOL_DEFINITIONS) {
      ctx.tools.register({
        name: definition.name,
        description: definition.description,
        handler: async (args = {}) => {
          const missing = (definition.required ?? []).filter((key) => !args[key])
          if (missing.length > 0) {
            return { ok: false, error: `missing required arguments: ${missing.join(', ')}` }
          }
          const outcome = await runAios(
            String(settings.kernelCommand ?? 'aios'),
            definition.argv(args),
            Number(settings.timeoutMs ?? 10000),
          )
          return outcome.ok ? outcome.result : { ok: false, error: outcome.error }
        },
      })
    }
  }

  if (ctx.commands?.register) {
    for (const command of COMMAND_DEFINITIONS) {
      ctx.commands.register({
        name: command.name,
        description: command.description,
        handler: () =>
          runAios(
            String(settings.kernelCommand ?? 'aios'),
            command.argv,
            Number(settings.timeoutMs ?? 10000),
          ),
      })
    }
  }

  if (ctx.skills?.registerProvider) {
    const provider = {
      list: async () =>
        (await readSkills()).map((skill) => ({ name: skill.name, description: skill.name })),
      get: async (skillName) => {
        const skill = (await readSkills()).find((item) => item.name === skillName)
        return skill ? { name: skill.name, content: skill.body } : undefined
      },
    }
    ctx.effect(() => ctx.skills.registerProvider(() => provider))
  }

  if (ctx.systemPrompt?.section) {
    ctx.effect(() =>
      ctx.systemPrompt.section({
        name: 'ai-engineering-os',
        text: contextText,
      }),
    )
  }
}
