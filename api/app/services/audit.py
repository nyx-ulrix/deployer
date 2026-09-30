from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.deps import client_ip
from app.models import AuditLog, RefreshToken, utcnow

AUDIT_RETENTION_DAYS = 90
REFRESH_TOKEN_GRACE = timedelta(days=1)
# Read back by the app: keys_to_rotate (who saw which API key) and the backups page's last export.
KEEP_FOREVER = ("api_key.reveal", "api_key.config", "instance.export")


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


def prune(db: Session, now: datetime | None = None) -> int:
    """A-102: deletes refresh tokens a day past expiry and audit rows older than AUDIT_RETENTION_DAYS
    (except KEEP_FOREVER). Caller commits."""
    now = now or utcnow()
    deleted = db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now - REFRESH_TOKEN_GRACE)).rowcount
    deleted += db.execute(
        delete(AuditLog).where(
            AuditLog.created_at < now - timedelta(days=AUDIT_RETENTION_DAYS), AuditLog.action.not_in(KEEP_FOREVER)
        )
    ).rowcount
    return deleted
