"""Thin stdlib-only bridge: failures must not silently permit sensitive operations."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from typing import Any


def run_hook(payload: dict[str, Any]) -> dict[str, Any]:
    executable = shutil.which("aios")
    code, detail = "AIOS_RUNTIME_UNAVAILABLE", "aios is not installed or not on PATH"
    if executable:
        try:
            result = subprocess.run(
                [executable, "authorize-hook"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                code, detail = "AIOS_RUNTIME_FAILED", "authorization runtime exited unsuccessfully"
            else:
                output = json.loads(result.stdout or "null")
                if not isinstance(output, dict):
                    raise ValueError("expected an object")
                if output:
                    specific = output.get("hookSpecificOutput")
                    if set(output) != {"hookSpecificOutput"} or not isinstance(specific, dict):
                        raise ValueError("invalid hook response")
                    deny = (
                        set(specific)
                        == {"hookEventName", "permissionDecision", "permissionDecisionReason"}
                        and specific.get("hookEventName") == "PreToolUse"
                        and specific.get("permissionDecision") == "deny"
                        and isinstance(specific.get("permissionDecisionReason"), str)
                        and bool(specific["permissionDecisionReason"].strip())
                    )
                    context = (
                        set(specific) == {"hookEventName", "additionalContext"}
                        and specific.get("hookEventName") == "SessionStart"
                        and payload.get("hook_event_name") == "SessionStart"
                        and isinstance(specific.get("additionalContext"), str)
                    )
                    if not (deny or context):
                        raise ValueError("unsupported hook response")
                return output
        except subprocess.TimeoutExpired:
            code, detail = "AIOS_RUNTIME_TIMEOUT", "authorization exceeded its 10 second budget"
        except (ValueError, OSError):
            code, detail = (
                "AIOS_RUNTIME_INVALID_RESPONSE",
                "authorization returned no valid decision",
            )
    data = payload.get("tool_input")
    data = data if isinstance(data, dict) else {}
    command = str(data.get("command", ""))
    sensitive = payload.get("tool_name") in {"apply_patch", "Write", "Edit"} or bool(
        re.search(
            r"\b(?:remove-item|rm|rmdir|rd|del|erase|set-content|add-content|out-file|"
            r"copy-item|move-item|new-item|tee|touch)\b|"
            r"\bgit\b.*\b(?:push|reset|clean|checkout|branch|update-ref)\b|[>]",
            command,
            re.I,
        )
    )
    event = str(payload.get("hook_event_name") or "PreToolUse")
    if sensitive:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": code + ": " + detail,
            }
        }
    return {
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": code + ": " + detail}
    }


def main() -> int:
    # Codex's JSON transport is UTF-8 even when Windows defaults to GBK.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("expected hook object")
    except (ValueError, OSError):
        print("AIOS_HOOK_INPUT_INVALID: unreadable hook payload", file=sys.stderr)
        return 2
    print(json.dumps(run_hook(payload), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
