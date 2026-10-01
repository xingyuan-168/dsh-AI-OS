/**
 * The kernel bridge: one subprocess call, one deterministic decision.
 *
 * The plugin never decides anything itself. It forwards a normalized payload to
 * `aios authorize-dsh`, which returns the single governance verdict. Duplicating
 * any rule here would create a second rule set that drifts from the kernel.
 *
 * Failure is closed for mutating work: if the kernel is missing, slow, or
 * answers with something unreadable, a mutating operation is denied with an
 * explicit reason while a read-only operation only reports that the check could
 * not run. That matches the documented host-event semantics in
 * docs/GOVERNANCE_RULES.md.
 */

import { spawn } from 'node:child_process'

const DENY = (ruleId, reason, targets = []) => ({
  decision: 'deny',
  rule_id: ruleId,
  reason,
  targets,
  next_step: 'Resolve the named finding; host policy remains independent.',
})

const ALLOW = (ruleId, reason) => ({
  decision: 'allow',
  rule_id: ruleId,
  reason,
  targets: [],
  next_step: 'DSH keeps its native permissions for this operation.',
})

/**
 * Operations that may not proceed when the kernel cannot answer.
 * `read`/`glob`/`grep` style tools are absent on purpose: blocking a read on an
 * unavailable check would restrict work without protecting anything.
 */
const MUTATING_EVENTS = new Set(['fs/write-intent', 'fs/edit-intent'])
const MUTATING_TOOLS = new Set(['write', 'edit', 'pwsh', 'bash', 'shell'])

export function isMutating(payload) {
  if (MUTATING_EVENTS.has(payload?.event)) return true
  return MUTATING_TOOLS.has(String(payload?.tool ?? '').toLowerCase())
}

function runKernel(command, payload, timeoutMs) {
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
      child = spawn(command, ['authorize-dsh'], { stdio: ['pipe', 'pipe', 'pipe'] })
    } catch (error) {
      finish({ ok: false, ruleId: 'AIOS_RUNTIME_UNAVAILABLE', reason: String(error) })
      return
    }

    const timer = setTimeout(() => {
      child.kill()
      finish({
        ok: false,
        ruleId: 'AIOS_RUNTIME_TIMEOUT',
        reason: `aios authorize-dsh exceeded its ${timeoutMs}ms budget`,
      })
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
      finish({ ok: false, ruleId: 'AIOS_RUNTIME_UNAVAILABLE', reason: String(error) })
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      if (code !== 0) {
        finish({
          ok: false,
          ruleId: 'AIOS_RUNTIME_FAILED',
          reason: stderr.trim() || `aios authorize-dsh exited with code ${code}`,
        })
        return
      }
      try {
        const decision = JSON.parse(stdout)
        if (!decision || typeof decision.decision !== 'string' || !decision.rule_id) {
          throw new Error('decision is missing its decision or rule_id field')
        }
        finish({ ok: true, decision })
      } catch (error) {
        finish({ ok: false, ruleId: 'AIOS_RUNTIME_INVALID_RESPONSE', reason: String(error) })
      }
    })

    child.stdin.on('error', () => {})
    child.stdin.end(JSON.stringify(payload))
  })
}

/**
 * Adjudicate one host payload. Always resolves: never throws into the host.
 *
 * @param {Record<string, unknown>} payload normalized by `./payload.js`
 * @param {Record<string, unknown>} settings plugin configuration
 */
export async function adjudicate(payload, settings) {
  const result = await runKernel(
    String(settings.kernelCommand ?? 'aios'),
    payload,
    Number(settings.timeoutMs ?? 10000),
  )
  if (result.ok) return result.decision
  if (settings.failMode === 'observe' || !isMutating(payload)) {
    return ALLOW(result.ruleId, result.reason)
  }
  return DENY(result.ruleId, result.reason)
}

export const decisions = { ALLOW, DENY }
