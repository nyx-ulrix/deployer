from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.deps import CurrentUser, DbSession, ProjectAccess, require_role
from app.errors import ApiError, forbidden, not_found, validation_error
from app.models import Project, ProjectInvite, ProjectMember, User, role_rank, utcnow
from app.serializers import iso
from app.services import audit, cohosting, invites
from app.services.passwords import Email

router = APIRouter(tags=["members"])

AssignableRole = Literal["admin", "developer", "viewer"]
Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]


def member_out(member: ProjectMember, user: User) -> dict:
    return {
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "role": member.role,
        "can_cohost": bool(member.can_cohost),  # docs/COHOSTING.md
        "created_at": iso(member.created_at),
    }


def _get_member(db, project_id: str, user_id: str) -> ProjectMember:
    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
    )
    if member is None:
        raise not_found("Member")
    return member


# --- members -------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/members")
def list_members(access: Viewer, db: DbSession) -> list[dict]:
    rows = db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == access.project.id)
        .order_by(ProjectMember.created_at)
    ).all()
    rows = sorted(rows, key=lambda r: -role_rank(r[0].role))  # stable: by role, then join date
    return [member_out(m, u) for m, u in rows]


class MemberUpdate(BaseModel):
    role: AssignableRole | None = None
    can_cohost: bool | None = None  # docs/COHOSTING.md "Roles"


@router.patch("/projects/{project_id}/members/{user_id}")
def update_member(user_id: str, body: MemberUpdate, request: Request, access: Admin, db: DbSession) -> dict:
    if body.role is None and body.can_cohost is None:
        raise validation_error("Nothing to change: send role and/or can_cohost")
    member = _get_member(db, access.project.id, user_id)
    is_self = user_id == access.user.id
    if body.role is not None and member.role == "owner":
        raise forbidden("The project owner's role can't be changed")
    if member.role == "owner" and access.role != "owner":
        raise forbidden("Only the project owner can change the owner's settings")
    if access.role != "owner" and member.role == "admin" and not is_self:
        raise forbidden("Only the project owner can change another admin's role")
    old_role, old_cohost = member.role, bool(member.can_cohost)
    if body.role is not None:
        member.role = body.role
    if body.can_cohost is not None:
        if body.can_cohost and role_rank(member.role) < role_rank("developer"):
            raise validation_error("Co-hosting needs the developer role or higher")
        member.can_cohost = body.can_cohost
    if role_rank(member.role) < role_rank("developer"):
        member.can_cohost = False
    if old_role != member.role:
        audit.record(
            db,
            "member.role_change",
            request=request,
            user_id=access.user.id,
            project_id=access.project.id,
            target_user_id=user_id,
            old_role=old_role,
            new_role=member.role,
        )
    if old_cohost != bool(member.can_cohost):
        audit.record(
            db,
            "member.cohost_change",
            request=request,
            user_id=access.user.id,
            project_id=access.project.id,
            target_user_id=user_id,
            can_cohost=bool(member.can_cohost),
        )
        if not member.can_cohost:
            cohosting.pause_member_replicas(
                db, access.project.id, user_id, "Co-hosting was switched off for this member"
            )
    db.commit()
    return member_out(member, db.get(User, user_id))


@router.delete("/projects/{project_id}/members/{user_id}")
def remove_member(user_id: str, request: Request, access: Viewer, db: DbSession) -> dict:
    member = _get_member(db, access.project.id, user_id)
    is_self = user_id == access.user.id
    if member.role == "owner":
        raise forbidden("The project owner can't be removed")
    if not is_self:
        if not access.at_least("admin"):
            raise forbidden("Requires the admin role or higher on this project")
        if access.role != "owner" and member.role == "admin":
            raise forbidden("Only the project owner can remove an admin")
    db.delete(member)
    cohosting.pause_member_replicas(db, access.project.id, user_id, "The device owner left the project")
    audit.record(
        db,
        "member.remove",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        target_user_id=user_id,
        role=member.role,
    )
    db.commit()
    return {"ok": True}


# --- invites (project side) ----------------------------------------------------------------------


@router.get("/projects/{project_id}/invites")
def list_invites(access: Admin, db: DbSession) -> list[dict]:
    now = utcnow()
    rows = db.scalars(
        select(ProjectInvite)
        .where(
            ProjectInvite.project_id == access.project.id,
            ProjectInvite.accepted_at.is_(None),
            ProjectInvite.revoked_at.is_(None),
            ProjectInvite.expires_at > now,
        )
        .order_by(ProjectInvite.created_at.desc())
    ).all()
    return [invites.invite_out(i) for i in rows]


class InviteCreate(BaseModel):
    email: Email | None = None
    role: AssignableRole
    expires_in_days: int = Field(default=invites.DEFAULT_EXPIRY_DAYS, ge=1, le=30)

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


@router.post("/projects/{project_id}/invites")
def create_invite(body: InviteCreate, request: Request, access: Admin, db: DbSession) -> dict:
    invite, token = invites.create_invite(
        db,
        project=access.project,
        inviter=access.user,
        role=body.role,
        email=body.email,
        expires_in_days=body.expires_in_days,
    )
    audit.record(
        db,
        "invite.create",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        invite_id=invite.id,
        role=invite.role,
        email=invite.email,
    )
    db.commit()
    return {"invite": invites.invite_out(invite), "invite_url": invites.invite_url(db, token)}


@router.delete("/projects/{project_id}/invites/{invite_id}")
def revoke_invite(invite_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    invite = db.get(ProjectInvite, invite_id)
    if invite is None or invite.project_id != access.project.id:
        raise not_found("Invite")
    if invite.revoked_at is None and invite.accepted_at is None:
        invite.revoked_at = utcnow()
        audit.record(
            db,
            "invite.revoke",
            request=request,
            user_id=access.user.id,
            project_id=access.project.id,
            invite_id=invite.id,
        )
    db.commit()
    return {"ok": True}


# --- invites (public / invitee side) -------------------------------------------------------------


@router.get("/invites/{token}")
def get_invite(token: str, db: DbSession) -> dict:
    invite = invites.find_pending_invite(db, token)
    if invite is None:
        raise not_found("Invite")
    project = db.get(Project, invite.project_id)
    inviter = db.get(User, invite.invited_by_id)
    if project is None:
        raise not_found("Invite")
    return {
        "project_name": project.name,
        "role": invite.role,
        "invited_by_name": (inviter.display_name or inviter.email) if inviter else None,
        "email": invite.email,
        "expires_at": iso(invite.expires_at),
    }


@router.post("/invites/{token}/accept")
def accept_invite(token: str, request: Request, user: CurrentUser, db: DbSession) -> dict:
    invite = invites.find_invite(db, token)
    if invite is not None and invite.accepted_by_id == user.id:
        # Already accepted by this user (e.g. during sign-up): idempotent.
        return {"project_id": invite.project_id}
    if invite is None or not invites.is_pending(invite):
        raise not_found("Invite")
    try:
        project_id = invites.accept_invite(db, invite, user)
    except ApiError:
        db.rollback()
        raise
    audit.record(db, "invite.accept", request=request, user_id=user.id, project_id=project_id, invite_id=invite.id)
    db.commit()
    return {"project_id": project_id}
