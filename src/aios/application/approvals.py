"""Approval recording shared by the CLI, MCP, and DSH tool surfaces.

One implementation keeps the three surfaces from drifting: a frontend approval
is only ever proven by the Git-tracked metadata block in docs/design/UI_SPEC.md,
and the SQLite row stays a rebuildable index.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from aios.core.gates import write_frontend_approval
from aios.infrastructure.config import resolve_runtime_root
from aios.infrastructure.database import Database, MigrationError

VALID_GATES = ("code_start", "frontend", "finish")
VALID_DECISIONS = ("approved", "rejected")


class ApprovalError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def record_approval(
    project_root: Path,
    *,
    gate: str,
    subject: str,
    decision: str,
    decided_by: str,
    scope: str = "default",
    reason: str | None = None,
) -> dict[str, object]:
    """Record one user approval or rejection for a governance gate."""

    resolved = resolve_runtime_root(project_root)
    root = resolved.checkout_root
    if gate not in VALID_GATES:
        raise ApprovalError("CONFIG_INVALID", "gate must be one of: " + ", ".join(VALID_GATES))
    if decision not in VALID_DECISIONS:
        raise ApprovalError(
            "CONFIG_INVALID", "decision must be one of: " + ", ".join(VALID_DECISIONS)
        )
    if not decided_by.strip():
        raise ApprovalError("CONFIG_INVALID", "decided_by is required")
    if not scope.strip():
        raise ApprovalError("CONFIG_INVALID", "scope is required")

    if gate == "frontend":
        write_frontend_approval(
            root / "docs" / "design" / "UI_SPEC.md",
            scope=scope,
            approved_by=decided_by,
            approved_on=datetime.now(UTC).date().isoformat(),
            decision=decision,
        )

    warnings: list[str] = []
    approval_id: str | None = None
    try:
        database = Database(resolved.project_root / ".aios/state/state.db")
        database.migrate()
        approval_id = _insert_approval(
            database,
            gate=gate,
            subject=subject,
            decision=decision,
            decided_by=decided_by,
            reason=reason,
        )
    except (MigrationError, sqlite3.Error, OSError) as exc:
        if gate != "frontend":
            raise
        warnings.append("Approval document saved; derived index unavailable: " + str(exc))

    return {
        "id": approval_id,
        "gate": gate,
        "subject": subject,
        "decision": decision,
        "scope": scope,
        "warnings": warnings,
    }


def _insert_approval(
    database: Database,
    *,
    gate: str,
    subject: str,
    decision: str,
    decided_by: str,
    reason: str | None,
) -> str:
    approval_id = "APPROVAL-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    with database.connection() as connection:
        connection.execute(
            "INSERT INTO approvals(id, subject, gate, decision, decided_by, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                approval_id,
                subject.strip(),
                gate,
                decision,
                decided_by.strip(),
                reason,
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()
    return approval_id


__all__ = ["VALID_DECISIONS", "VALID_GATES", "ApprovalError", "record_approval"]
