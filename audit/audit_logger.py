import json
from typing import Any

from sqlalchemy.orm import Session

from database.models import AuditLog


def record_audit(
    session: Session,
    *,
    actor_id: str,
    operation: str,
    entity_type: str,
    entity_id: int | str,
    old_value: Any,
    new_value: Any,
    status: str,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            operation=operation,
            entity_type=entity_type,
            entity_id=str(entity_id),
            old_value=json.dumps(old_value, default=str) if old_value is not None else None,
            new_value=json.dumps(new_value, default=str) if new_value is not None else None,
            status=status,
        )
    )