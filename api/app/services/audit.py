from fastapi import Request
from sqlalchemy.orm import Session

from app.deps import client_ip
from app.models import AuditLog


def record(
    db: Session,
    action: str,
    *,
    request: Request | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    **details,
) -> None:
    """Adds an audit log row to the session. Caller commits."""
    db.add(
        AuditLog(
            action=action,
            user_id=user_id,
            project_id=project_id,
            ip=client_ip(request) if request else None,
            user_agent=(request.headers.get("User-Agent") or "")[:255] if request else None,
            details=details or None,
        )
    )
