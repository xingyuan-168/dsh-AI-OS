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

const PATH_KEYS = ['path', 'filePath', 'file_path', 'target', 'processPath', 'hostPath']
const COMMAND_KEYS = ['command', 'cmd', 'script', 'input']
const NAME_KEYS = ['name', 'tool', 'toolName', 'tool_name']

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
  return firstString(value, NAME_KEYS)
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

export function toolPayload({ tool, args, cwd }) {
  return {
    event: 'tools/pre-execute',
    cwd: resolveCwd(cwd),
    tool: String(tool ?? extractName(args) ?? '').toLowerCase(),
    input: args && typeof args === 'object' ? args : {},
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
