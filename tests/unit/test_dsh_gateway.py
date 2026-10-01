from __future__ import annotations

from pathlib import Path

from aios.application.dsh_gateway import authorize_dsh_payload, normalize_dsh_payload


def _pre_execute(cwd: Path, tool: str, **tool_input: object) -> dict[str, object]:
    return {"event": "tools/pre-execute", "cwd": str(cwd), "tool": tool, "input": tool_input}


def _intent(cwd: Path, event: str, path: str) -> dict[str, object]:
    return {"event": event, "cwd": str(cwd), "input": {"file_path": path}}


def test_session_context_is_injected_without_blocking(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload({"event": "agent/created", "cwd": str(governed_repo)})
    assert outcome["decision"] == "allow"
    assert outcome["rule_id"] == "SESSION_CONTEXT"
    assert "AGENTS.md" in str(outcome["reason"])


def test_read_only_tools_are_outside_governance_scope(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload(_pre_execute(governed_repo, "read", file_path="input/x.txt"))
    assert outcome["decision"] == "allow"
    assert outcome["rule_id"] == "OUTSIDE_AIOS_SCOPE"


def test_unknown_events_and_tools_have_no_aios_check(governed_repo: Path) -> None:
    assert normalize_dsh_payload({"event": "tools/post-execute", "cwd": str(governed_repo)}) is None
    assert normalize_dsh_payload(_pre_execute(governed_repo, "glob", pattern="*")) is None
    outcome = authorize_dsh_payload(_pre_execute(governed_repo, "glob", pattern="*"))
    assert outcome["decision"] == "allow"


def test_write_intent_denies_protected_input_path(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload(_intent(governed_repo, "fs/write-intent", "input/asset.txt"))
    assert outcome["decision"] == "deny"
    assert outcome["rule_id"] == "PATH_POLICY_VIOLATION"


def test_write_intent_denies_runtime_state_path(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload(
        _intent(governed_repo, "fs/write-intent", ".aios/state/state.db")
    )
    assert outcome["decision"] == "deny"


def test_edit_intent_denies_governance_rule_path(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload(_intent(governed_repo, "fs/edit-intent", "AGENTS.md"))
    assert outcome["decision"] == "deny"


def test_write_intent_allows_documentation_write(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload(_intent(governed_repo, "fs/write-intent", "docs/note.md"))
    assert outcome["decision"] == "allow"


def test_write_intent_denies_formal_source_without_github(governed_repo: Path) -> None:
    """A formal code write needs a reachable GitHub remote (Code Start)."""

    outcome = authorize_dsh_payload(_intent(governed_repo, "fs/write-intent", "src/module.py"))
    assert outcome["decision"] == "deny"
    assert outcome["rule_id"] == "CODE_START_BLOCKED"


def test_shell_command_denies_shared_repository_destruction(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload(
        _pre_execute(governed_repo, "pwsh", command="git push --force origin main")
    )
    assert outcome["decision"] == "deny"
    assert "force" in str(outcome["rule_id"]).casefold() or outcome["targets"] is not None


def test_shell_command_allows_native_engineering_work(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload(_pre_execute(governed_repo, "pwsh", command="pytest tests"))
    assert outcome["decision"] == "allow"


def test_uninitialized_project_is_not_governed(tmp_path: Path) -> None:
    # An uninitialized project is a repository without governance config; the
    # boundary keeps root resolution from escaping to the hosting repository.
    (tmp_path / ".git").mkdir()
    outcome = authorize_dsh_payload(_intent(tmp_path, "fs/write-intent", "src/module.py"))
    assert outcome["decision"] == "allow"


def test_payload_without_input_is_tolerated(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload(
        {"event": "fs/write-intent", "cwd": str(governed_repo), "input": None}
    )
    # No resolvable target means no proven blocker, never a crash.
    assert outcome["decision"] in {"allow", "deny"}
    assert isinstance(outcome["rule_id"], str)


def test_path_may_arrive_at_the_top_level(governed_repo: Path) -> None:
    outcome = authorize_dsh_payload(
        {"event": "fs/write-intent", "cwd": str(governed_repo), "target": "input/asset.txt"}
    )
    assert outcome["decision"] == "deny"
