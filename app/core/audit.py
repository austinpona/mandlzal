"""Tiny helper to write audit-log entries."""
import json
from typing import Any
from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def log_action(
    db: Session,
    *,
    actor: str | None,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Persist an audit entry. Does not commit by default - the caller's
    surrounding transaction commits the write."""
    entry = AuditLog(
        actor=actor or "system",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=json.dumps(details, default=str) if details else None,
    )
    db.add(entry)
    return entry
