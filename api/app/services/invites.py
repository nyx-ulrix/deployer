"""Project invites: hashed single-use tokens with optional email lock."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto import random_token, sha256_hex
from app.errors import ApiError
from app.models import Project, ProjectInvite, ProjectMember, User, utcnow
from app.serializers import iso
from app.services.instance_settings import public_url
from app.services.passwords import normalize_email

DEFAULT_EXPIRY_DAYS = 7


def invite_out(invite: ProjectInvite) -> dict:
    return {
        "id": invite.id,
        "email": invite.email,
        "role": invite.role,
        "invited_by": invite.invited_by_id,
        "expires_at": iso(invite.expires_at),
        "created_at": iso(invite.created_at),
    }


def invite_url(db: Session, token: str) -> str:
    return f"{public_url(db)}/invite/{token}"


def create_invite(
    db: Session,
    *,
    project: Project,
    inviter: User,
    role: str,
    email: str | None = None,
    expires_in_days: int = DEFAULT_EXPIRY_DAYS,
) -> tuple[ProjectInvite, str]:
    """Adds an invite (caller commits). Returns (invite, raw token)."""
    if role == "owner":
        raise ApiError(422, "validation_error", "Invites can't grant the owner role")
    if not 1 <= expires_in_days <= 30:
        raise ApiError(422, "validation_error", "expires_in_days must be between 1 and 30")
    token = random_token(32)
    invite = ProjectInvite(
        project_id=project.id,
        email=normalize_email(email) if email else None,
        role=role,
        token_hash=sha256_hex(token),
        invited_by_id=inviter.id,
        expires_at=utcnow() + timedelta(days=expires_in_days),
        created_at=utcnow(),
    )
    db.add(invite)
    db.flush()
    return invite, token


def find_invite(db: Session, token: str | None) -> ProjectInvite | None:
    """Any invite with this token, regardless of state."""
    if not token or len(token) > 200:
        return None
    return db.scalar(select(ProjectInvite).where(ProjectInvite.token_hash == sha256_hex(token)))


def is_pending(invite: ProjectInvite) -> bool:
    return invite.accepted_at is None and invite.revoked_at is None and invite.expires_at > utcnow()


def find_pending_invite(db: Session, token: str | None) -> ProjectInvite | None:
    invite = find_invite(db, token)
    return invite if invite is not None and is_pending(invite) else None


def email_matches(invite: ProjectInvite, email: str) -> bool:
    return invite.email is None or normalize_email(invite.email) == normalize_email(email)


def accept_invite(db: Session, invite: ProjectInvite, user: User) -> str:
    """Marks the invite used and adds the membership (caller commits). Returns the project id.

    An existing member keeps their current role.
    """
    if not email_matches(invite, user.email):
        raise ApiError(403, "invite_email_mismatch", "This invite was sent to a different email address")
    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == invite.project_id, ProjectMember.user_id == user.id)
    )
    if member is None:
        db.add(ProjectMember(project_id=invite.project_id, user_id=user.id, role=invite.role))
    invite.accepted_at = utcnow()
    invite.accepted_by_id = user.id
    db.flush()
    return invite.project_id
