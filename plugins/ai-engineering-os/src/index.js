/**
 * AI Engineering OS — the DeepSeek Harness governance layer as a Cordis plugin.
 *
 * The plugin forwards; the kernel decides. Every verdict below comes from
 * `aios authorize-dsh`, so the CLI, the MCP server, and this plugin can never
 * disagree about what is allowed.
 *
 * Where enforcement actually happens:
 *   - `tools/pre-execute` is the one pre-dispatch point that can deny, cancel,
 *     or ask. It covers *every* tool, including the write and shell tools, so it
 *     is the enforcement point for all three gates.
 *   - `fs/write-intent` and `fs/edit-intent` are single-slot *intent* decisions
 *     (they choose the expected version of a write) and cannot deny anything.
 *     They are deliberately not registered: a listener there would look like
 *     write-time protection without being able to provide it.
 *   - `agent/created` announces a session, so the constitution section can be
 *     assembled from the kernel rather than duplicated here.
 *
 * Assumed host contract (confirm against the installed host types): a
 * pre-dispatch listener receives the execution and `next`, and returns the
 * host's decision type. `next()` is returned whenever AIOS does not deny, so a
 * mistranslated verdict can only fail to block — it can never auto-approve.
 */

import { adjudicate } from './kernel.js'
import { extractName, resolveCwd, sessionPayload, toolPayload } from './payload.js'
import { registerSurfaces } from './surfaces.js'

export const name = 'ai-engineering-os'
export const inject = ['tools']

export const DEFAULTS = {
  strict: true,
  uninitializedProjects: 'strict',
  kernelCommand: 'aios',
  timeoutMs: 10000,
  failMode: 'closed',
}

const FALLBACK_CONTEXT =
  'AI Engineering OS governs this project. Read AGENTS.md and the relevant fact documents.'

/**
 * Map an AIOS verdict onto the host's pre-dispatch verdict.
 *
 * This is the single place to correct if the host's decision type differs: the
 * AIOS rule id is always carried in the reason so a block is attributable.
 */
function preToolVerdict(decision) {
  return { type: 'deny', reason: `${decision.rule_id}: ${decision.reason}` }
}

async function sessionContext(settings) {
  const decision = await adjudicate(sessionPayload({ cwd: process.cwd() }), settings)
  return typeof decision.reason === 'string' && decision.reason ? decision.reason : FALLBACK_CONTEXT
}

export async function apply(ctx, config = {}) {
  const settings = { ...DEFAULTS, ...config }

  ctx.on('tools/pre-execute', async (exec, next) => {
    const decision = await adjudicate(
      {
        ...toolPayload({
          tool: extractName(exec) ?? exec?.name,
          args: exec?.arguments ?? exec?.args ?? exec?.input ?? exec?.tool_input,
          cwd: resolveCwd(exec?.cwd, exec?.workdir),
        }),
        // Tier 2: strict mode makes an uninitialized project follow the same
        // gates. The kernel materializes the default policy in memory only.
        strict: Boolean(settings.strict),
      },
      settings,
    )
    if (decision.decision === 'deny') return preToolVerdict(decision)
    return next()
  })

  ctx.on('agent/created', async () => {
    // Announcement only: the kernel's session facts are surfaced through the
    // prompt section below. This never blocks a session from starting.
    await sessionContext(settings)
  })

  registerSurfaces(ctx, settings, await sessionContext(settings))
}
