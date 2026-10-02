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
 * The optional 8-tool surface is gated by `exposeTools` (default false): a tool
 * schema is request payload rather than a governance verdict, so an invalid one
 * fails the whole turn instead of denying one operation.
 *
 * Assumed host contract (confirm against the installed host types): a
 * pre-dispatch listener receives the execution and `next`, and returns the
 * host's decision type. `next()` is returned whenever AIOS does not deny, so a
 * mistranslated verdict can only fail to block — it can never auto-approve.
 *
 * Surface registrations follow the published contracts in
 * `docs/reference/subsystems/{tools,commands,skills,system-prompt}.md`; see
 * `./surfaces.js` for the per-surface shapes and their isolation.
 */

import { adjudicate } from './kernel.js'
import { extractName, resolveCwd, sessionPayload, toolPayload } from './payload.js'
import { optionalService, registerSurfaces } from './surfaces.js'

export const name = 'ai-engineering-os'
// Cordis' context throws when a plugin reads a service it did not declare, so
// every surface the plugin touches is declared here. All four ship in
// `@deepseek-ai/dsh-base`, which every base-backed profile composes; a profile
// that omitted one would leave this fiber pending rather than half-registered,
// which is the honest signal. `./surfaces.js` still reads each optional service
// defensively, so a future edit cannot reintroduce the throwing read.
export const inject = ['tools', 'commands', 'skills', 'systemPrompt']

export const DEFAULTS = {
  strict: true,
  uninitializedProjects: 'strict',
  kernelCommand: 'aios',
  timeoutMs: 10000,
  failMode: 'closed',
  // Registered tools join the tool catalogue of EVERY model request, so a
  // malformed schema there does not deny an operation — it makes the provider
  // reject the whole turn. Governance may deny work; it must never make the
  // model unusable. The tool surface is therefore opt-in, and enforcement
  // (`tools/pre-execute`) plus the session context never depend on it.
  exposeTools: false,
  // Debug-only: append each adjudication to the project's gitignored runtime
  // state so enforcement can be observed from outside the host. Never affects a
  // verdict; see ./kernel.js.
  diagnostics: false,
}

const FALLBACK_CONTEXT =
  'AI Engineering OS governs this project. Read AGENTS.md and the relevant fact documents.'

/**
 * Map an AIOS verdict onto the host's pre-dispatch verdict.
 *
 * `PreToolDecision` is `{ kind: 'deny' | 'allow' | 'cancel' | 'ask', ... }`; a
 * deny carries its model-facing `reason` plus optional structured identity, so a
 * block stays attributable to one AIOS rule.
 */
function preToolVerdict(decision) {
  return {
    kind: 'deny',
    reason: `${decision.rule_id}: ${decision.reason}`,
    info: { name: 'AIOSGovernanceError', code: String(decision.rule_id) },
  }
}

async function sessionContext(settings, workspaceRoot) {
  const decision = await adjudicate(
    sessionPayload({ cwd: resolveCwd(workspaceRoot, process.cwd()) }),
    settings,
  )
  return typeof decision.reason === 'string' && decision.reason ? decision.reason : FALLBACK_CONTEXT
}

export async function apply(ctx, config = {}) {
  const settings = { ...DEFAULTS, ...config }
  // The session's workspace root, when the host exposes it. Tool executions may
  // not carry a cwd, and a relative target resolved against the wrong base would
  // decide against the wrong project — or against nothing at all.
  const workspaceRoot = optionalService(ctx, 'sandboxPolicy')?.workspaceRoot

  ctx.on('tools/pre-execute', async (exec, next) => {
    const decision = await adjudicate(
      {
        ...toolPayload({
          tool: extractName(exec) ?? exec?.name,
          args: exec?.arguments ?? exec?.args ?? exec?.input ?? exec?.tool_input,
          cwd: resolveCwd(
            // The session workspace is authoritative for resolving a relative
            // target; a tool-local or process cwd is only a fallback, because a
            // wrong base decides against the wrong project.
            workspaceRoot,
            exec?.agent?.session?.cwd,
            exec?.session?.cwd,
            exec?.agent?.cwd,
            exec?.cwd,
            exec?.workdir,
          ),
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
    await sessionContext(settings, workspaceRoot)
  })

  registerSurfaces(ctx, settings, await sessionContext(settings, workspaceRoot))
}
