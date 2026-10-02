"""Read-only host-event adapter; AIOS decisions never grant host execution authority.

Shared by the Codex-compatible ``authorize-hook`` bridge and the DSH payload
normalizer in :mod:`aios.application.dsh_gateway`, so both surfaces adjudicate
through exactly one offline rule set (ADR-0018).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from aios.application.authorization import (
    AuthorizationRequest,
    GovernanceAuthorizationKernel,
)
from aios.application.cleanup_policy import is_reparse, literal_tokens
from aios.application.governance_policy import GovernancePolicyCompiler
from aios.core.gates import GateDecision, formal_write_blockers
from aios.infrastructure.config import load_project_config, resolve_runtime_root

_PATH_HEADER = re.compile(
    r"^\*\*\*\s+(?:Add File|Update File|Delete File|Move to):\s*(.+?)\s*$", re.MULTILINE
)
_REDIRECT_TARGETS = re.compile(r"""(?<![-<>])>{1,2}\s*("[^"]+"|'[^']+'|[^\s|;&<>]+)""")
_CONTEXT = (
    "AI Engineering OS governs this project. Read AGENTS.md and relevant fact documents. "
    "Keep DSH's native workflow and approval boundaries. Record the starting Git ref; "
    "run Code Start before implementation and Finish with that base ref. DSH must confirm "
    "task ownership before cleanup and protect the user's existing changes."
)

# Public alias: the DSH plugin injects this text at session start.
SESSION_CONTEXT = _CONTEXT

# Deterministic defaults used when Tier 2 strict mode judges a project that has
# no .aios/project.yaml. They live in memory only: the plugin never materializes
# a configuration file the user did not ask for.
DEFAULT_CODE_PATHS: tuple[str, ...] = ("src",)
DEFAULT_GITHUB_HOSTS: frozenset[str] = frozenset({"github.com"})


class HookGatewayError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _result(decision: str, code: str, reason: str, targets: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "layer": "aios",
        "decision": decision,
        "rule_id": code,
        "reason": reason,
        "targets": list(targets),
        "next_step": (
            "Resolve the named finding; host policy remains independent."
            if decision == "deny"
            else "DSH must confirm task scope, ownership and native permissions."
        ),
    }


def explain_hook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Explain the same checks as the hook without executing the proposed operation."""
    try:
        return _evaluate(payload)
    except Exception as exc:
        return _result("deny", getattr(exc, "code", "POLICY_CHECK_FAILED"), str(exc))


def _evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    tool = str(payload.get("tool_name", ""))
    data = payload.get("tool_input")
    data = data if isinstance(data, dict) else {}
    cwd = Path(str(data.get("workdir") or payload.get("cwd") or ".")).resolve()
    resolved = resolve_runtime_root(cwd)
    initialized = (resolved.project_root / ".aios/project.yaml").is_file()
    # Tier 2 strict mode is opt-in per call and never persisted to the project.
    strict = bool(payload.get("aios_strict")) and not initialized
    if payload.get("hook_event_name") == "SessionStart":
        return _result("context" if initialized else "allow", "SESSION_CONTEXT", _CONTEXT)
    if tool not in {"Bash", "apply_patch", "Write", "Edit"}:
        return _result("allow", "OUTSIDE_HOOK_SCOPE", "no AIOS check for this tool")
    command = str(data.get("command", ""))
    if tool == "Bash":
        kernel = GovernanceAuthorizationKernel(
            GovernancePolicyCompiler(resolved.project_root).compile()
        )
        outcome = kernel.authorize(
            AuthorizationRequest(
                operation="execute",
                tool=tool,
                command=command,
                cwd=cwd,
                checkout=resolved.checkout_root,
                disposable=resolved.worktree is not None,
            )
        )
        if not outcome.allowed:
            return _result("deny", outcome.rule_id, outcome.reason, outcome.denied_paths)
        if outcome.rule_id == "CLEANUP_TARGET_CHECKED":
            return _result("allow", outcome.rule_id, outcome.reason, outcome.denied_paths)
    paths = _write_targets(tool, command, data)
    boundaries: dict[Path, GateDecision] = {}
    network_deadline = time.monotonic() + 5
    if tool in {"apply_patch", "Write", "Edit"} and not paths and (initialized or strict):
        return _result(
            "deny", "PATCH_TARGET_UNRESOLVED", "patch contains no supported file headers"
        )
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute() and not (
            initialized or (resolved.checkout_root / ".git").exists()
        ):
            # A relative target is only meaningful against a real project base.
            # Without one, protected-path patterns would be matched against an
            # unrelated root, so fail closed and ask for an absolute path.
            return _result(
                "deny",
                "RELATIVE_TARGET_UNRESOLVED",
                "relative write target has no verifiable project base; use an absolute path",
                (raw,),
            )
        lexical = path if path.is_absolute() else cwd / path
        if any(is_reparse(parent) for parent in (lexical, *lexical.parents)):
            return _result(
                "deny",
                "WRITE_TARGET_REPARSE",
                "write traverses a link or junction",
                (lexical.as_posix(),),
            )
        target = lexical.resolve()
        owner = resolve_runtime_root(target.parent)
        governed = (owner.project_root / ".aios/project.yaml").is_file()
        if governed:
            config = load_project_config(owner.project_root)
            code_paths: tuple[str, ...] | list[str] = config.code_paths
            github_hosts: frozenset[str] | tuple[str, ...] = config.github_hosts
        elif strict:
            # Tier 2: an uninitialized project is judged against a deterministic
            # default held only in memory. Nothing is written to disk, so the
            # decision stays reproducible and the project stays unmodified.
            code_paths = DEFAULT_CODE_PATHS
            github_hosts = DEFAULT_GITHUB_HOSTS
        else:
            # Tier 0: baseline protection applies in every workspace, governed or
            # not, but the project-scoped gates below need .aios/project.yaml.
            code_paths = ()
            github_hosts = DEFAULT_GITHUB_HOSTS
        if resolved.worktree and not target.is_relative_to(resolved.checkout_root):
            return _result(
                "deny",
                "WORKTREE_WRITE_OUTSIDE",
                "worktree may not write another checkout",
                (target.as_posix(),),
            )
        relative = target.relative_to(owner.checkout_root).as_posix()
        if owner.worktree and (relative == "docs/memory" or relative.startswith("docs/memory/")):
            return _result(
                "deny",
                "MEMORY_SINGLE_WRITER",
                "submit a memory candidate instead",
                (target.as_posix(),),
            )
        kernel = GovernanceAuthorizationKernel(
            GovernancePolicyCompiler(owner.project_root).compile()
        )
        outcome = kernel.authorize(
            AuthorizationRequest(operation="write", tool=tool, paths=(relative,))
        )
        if not outcome.allowed:
            return _result("deny", outcome.rule_id, outcome.reason, (target.as_posix(),))
        if _formal_write_targets((relative,), code_paths):
            if owner.checkout_root not in boundaries:
                remaining = network_deadline - time.monotonic()
                if remaining <= 0:
                    raise HookGatewayError(
                        "NETWORK_BUDGET_EXHAUSTED", "remote check budget exhausted"
                    )
                boundaries[owner.checkout_root] = _formal_boundary(
                    owner.checkout_root, github_hosts, timeout=remaining
                )
            boundary = boundaries[owner.checkout_root]
            if not boundary.allowed:
                return _result(
                    "deny",
                    "CODE_START_BLOCKED",
                    ", ".join(boundary.blocked_by),
                    (target.as_posix(),),
                )
    return _result("allow", "AIOS_CHECKS_PASSED", "no objective AIOS blocker", paths)


def authorize_hook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    outcome = explain_hook_payload(payload)
    if outcome["decision"] == "context":
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": outcome["reason"],
            }
        }
    if outcome["decision"] != "deny":
        return {}  # Defer to native permissions; never auto-approve/rewrite a tool call.
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": outcome["rule_id"]
            + ": "
            + outcome["reason"]
            + ("; targets=" + ", ".join(outcome["targets"]) if outcome["targets"] else ""),
        }
    }


def parse_apply_patch_paths(patch_text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(path.strip().replace("\\", "/") for path in _PATH_HEADER.findall(patch_text))
    )


def _formal_boundary(
    root: Path, github_hosts: frozenset[str] | tuple[str, ...], *, timeout: float = 5
) -> GateDecision:
    return formal_write_blockers(root, github_hosts=github_hosts, network_timeout=timeout)


def _write_targets(tool: str, command: str, data: dict[str, Any]) -> tuple[str, ...]:
    if tool == "apply_patch":
        return parse_apply_patch_paths(command)
    if tool in {"Write", "Edit"}:
        path = str(data.get("path") or data.get("file_path") or "")
        return (path,) if path else ()
    if re.search(
        r"\b(?:set-content|add-content|out-file|copy-item|move-item|new-item)\b", command, re.I
    ):
        raise HookGatewayError(
            "WRITE_TARGET_UNRESOLVED",
            "shell write targets cannot be proven by this bounded parser; "
            "provide structured file targets for independent checking",
        )
    redirects = tuple(
        match.strip("\"'")
        for match in _REDIRECT_TARGETS.findall(command)
        if match.strip("\"'").casefold() not in {"&1", "&2", "/dev/null", "nul", "$null"}
    )
    for target in redirects:
        try:
            literal_tokens(target)
        except ValueError as exc:
            raise HookGatewayError("WRITE_TARGET_UNRESOLVED", str(exc)) from exc
    return redirects


def _formal_write_targets(
    targets: tuple[str, ...], code_paths: tuple[str, ...] | list[str]
) -> tuple[str, ...]:
    return tuple(
        target
        for target in targets
        if any(
            target.casefold() == base.casefold()
            or target.casefold().startswith(base.casefold() + "/")
            for base in code_paths
        )
    )
