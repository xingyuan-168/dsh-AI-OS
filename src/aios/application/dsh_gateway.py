"""Normalize DeepSeek Harness host payloads into the single governance kernel.

The DSH Cordis plugin only forwards host events; it never decides. Each payload
is normalized into the same internal request the host-event adapter already
understands, so there is exactly one offline rule set and one authorized-path
parser (ADR-0018). Adding a second, DSH-specific rule set would make the two
drift apart, which is precisely the failure this module exists to prevent.

Payload contract (produced by the plugin, versioned with it)::

    {
      "event": "tools/pre-execute" | "fs/write-intent" | "fs/edit-intent" | "agent/created",
      "cwd": "<session working directory>",
      "tool": "<DSH tool name, tools/pre-execute only>",
      "input": { ... tool arguments ... }
    }
"""

from __future__ import annotations

from typing import Any

from aios.application.hook_gateway import SESSION_CONTEXT, explain_hook_payload

# DSH tool name -> the operation class the kernel already understands.
# A missing entry means "no AIOS check": reads and other non-mutating tools are
# never blocked by path rules, which keeps native engineering work unrestricted.
TOOL_OPERATIONS: dict[str, str] = {
    "write": "Write",
    "edit": "Edit",
    "pwsh": "Bash",
    "bash": "Bash",
    "shell": "Bash",
}

# Argument names accepted for a write/edit target, most specific first.
WRITE_PATH_KEYS = ("file_path", "path", "target")

WRITE_INTENT_EVENTS = {
    "fs/write-intent": "Write",
    "fs/edit-intent": "Edit",
}

CONTEXT_EVENT = "agent/created"
PRE_EXECUTE_EVENT = "tools/pre-execute"


def normalize_dsh_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the kernel request for one DSH payload, or None when out of scope."""

    event = str(payload.get("event") or "")
    if event in WRITE_INTENT_EVENTS:
        tool = WRITE_INTENT_EVENTS[event]
    elif event == PRE_EXECUTE_EVENT:
        tool = TOOL_OPERATIONS.get(str(payload.get("tool") or "").casefold(), "")
        if not tool:
            return None
    else:
        return None

    data = payload.get("input")
    data = data if isinstance(data, dict) else {}
    tool_input: dict[str, Any] = {}
    if tool in {"Write", "Edit"}:
        for key in WRITE_PATH_KEYS:
            value = data.get(key) or payload.get(key)
            if value:
                tool_input["file_path"] = str(value)
                break
    elif tool == "Bash":
        command = data.get("command") or payload.get("command")
        tool_input["command"] = str(command or "")

    return {
        "cwd": str(payload.get("cwd") or "."),
        "tool_name": tool,
        "tool_input": tool_input,
        "hook_event_name": "PreToolUse",
        # Tier 2: when the plugin runs in strict mode, a project without
        # .aios/project.yaml is judged against the in-memory default policy.
        "aios_strict": bool(payload.get("strict")),
    }


def authorize_dsh_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Adjudicate one DSH payload and return the plugin-facing decision.

    The decision shape is the plugin's whole input: it maps ``deny`` onto the
    host's own pre-dispatch verdict and never treats this output as execution
    authority. Unresolvable failures are reported as denials by the kernel.
    """

    if str(payload.get("event") or "") == CONTEXT_EVENT:
        return {
            "decision": "allow",
            "rule_id": "SESSION_CONTEXT",
            "reason": SESSION_CONTEXT,
            "targets": [],
            "next_step": "Read AGENTS.md and the task-relevant fact documents.",
        }
    normalized = normalize_dsh_payload(payload)
    if normalized is None:
        return {
            "decision": "allow",
            "rule_id": "OUTSIDE_AIOS_SCOPE",
            "reason": "no AIOS check applies to this event or tool",
            "targets": [],
            "next_step": "DSH keeps its native permissions for this operation.",
        }
    outcome = explain_hook_payload(normalized)
    if outcome.get("decision") == "context":
        outcome = {**outcome, "decision": "allow"}
    return outcome


__all__ = [
    "CONTEXT_EVENT",
    "PRE_EXECUTE_EVENT",
    "TOOL_OPERATIONS",
    "WRITE_INTENT_EVENTS",
    "WRITE_PATH_KEYS",
    "authorize_dsh_payload",
    "normalize_dsh_payload",
]
