/**
 * Normalize DeepSeek Harness host objects into the kernel's payload contract.
 *
 * Assumed host contracts (read from the live service/event catalogue; confirm
 * against the installed host types before relying on enforcement):
 *
 *   - `tools/pre-execute` delivers a ToolExecution carrying the tool name and
 *     its arguments. This is the only pre-dispatch point that can deny, so it is
 *     the plugin's enforcement path.
 *   - `fs/write-intent` / `fs/edit-intent` deliver a target that resolves to a
 *     filesystem path. The plugin does not register those listeners (they cannot
 *     deny); the kernel still accepts the payloads for diagnostics.
 *
 * Extraction is deliberately tolerant across field spellings: a miss would mean
 * an ungoverned write, so the extractors accept every plausible name rather than
 * one. A payload that yields no path is still adjudicated, because the kernel,
 * not this file, decides what a missing target means.
 */

import { dirname, isAbsolute } from 'node:path'

const PATH_KEYS = ['path', 'filePath', 'file_path', 'target', 'processPath', 'hostPath']
const COMMAND_KEYS = ['command', 'cmd', 'script', 'input']
const NAME_KEYS = ['name', 'toolName', 'tool_name', 'tool']

const firstString = (value, keys) => {
  if (!value || typeof value !== 'object') return undefined
  for (const key of keys) {
    const candidate = value[key]
    if (typeof candidate === 'string' && candidate.length > 0) return candidate
  }
  return undefined
}

export function extractPath(value) {
  if (typeof value === 'string' && value.length > 0) return value
  return firstString(value, PATH_KEYS)
}

export function extractName(value) {
  if (typeof value === 'string' && value.length > 0) return value
  if (!value || typeof value !== 'object') return undefined
  for (const key of NAME_KEYS) {
    const candidate = value[key]
    if (typeof candidate === 'string' && candidate.length > 0) return candidate
    // The execution may nest the tool descriptor rather than name it directly;
    // an unresolved name would silently downgrade the call to "no AIOS check".
    if (candidate && typeof candidate === 'object') {
      const nested = candidate.name
      if (typeof nested === 'string' && nested.length > 0) return nested
    }
  }
  return undefined
}

export function extractCommand(value) {
  return firstString(value, COMMAND_KEYS)
}

export function resolveCwd(...candidates) {
  for (const candidate of candidates) {
    const value = extractPath(candidate)
    if (value) return value
  }
  return process.cwd()
}

/**
 * Best-effort session workspace for one tool execution.
 *
 * The plugin's own context is global, and `sandboxPolicy` may only be provided
 * on the executing agent's (session) context — reading it there at apply time
 * yielded nothing, which left relative targets adjudicated against the host
 * process directory. Consult the executing agent's context first, then the
 * global fallback captured at apply time. Never throws: an unavailable
 * workspace degrades to the fallback instead of breaking the verdict.
 */
export function executionWorkspace(exec, fallback) {
  const context = exec?.agent?.ctx
  if (context) {
    try {
      const root = context.get?.('sandboxPolicy')?.workspaceRoot
      if (typeof root === 'string' && root.length > 0) return root
    } catch {
      // Not readable through the store; try the declared-property path.
    }
    try {
      const root = context.sandboxPolicy?.workspaceRoot
      if (typeof root === 'string' && root.length > 0) return root
    } catch {
      // Unavailable on this context.
    }
  }
  return fallback
}

export function toolPayload({ tool, args, cwd }) {
  const data = args && typeof args === 'object' ? args : {}
  const target = extractPath(data)
  // An absolute target makes the session cwd irrelevant: the kernel resolves a
  // governing project from the target itself. Preferring that base means a
  // missing or wrong session cwd can never move a protected path out of scope,
  // which is exactly how a write to `.aios/state/` slipped through once.
  const base = target && isAbsolute(target) ? dirname(target) : resolveCwd(cwd)
  return {
    event: 'tools/pre-execute',
    cwd: base,
    tool: String(tool ?? extractName(data) ?? '').toLowerCase(),
    input: data,
  }
}

export function writeIntentPayload({ event, target, cwd }) {
  return {
    event,
    cwd: resolveCwd(cwd),
    input: { file_path: String(extractPath(target) ?? '') },
  }
}

export function sessionPayload({ cwd }) {
  return { event: 'agent/created', cwd: resolveCwd(cwd) }
}
