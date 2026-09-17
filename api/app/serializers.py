"""Response shapes shared across routers (see docs/API.md "Shared shapes")."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DataSource, Project, User, UserIdentity


def iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None


def identity_out(identity: UserIdentity) -> dict:
    return {
        "id": identity.id,
        "provider": identity.provider,
        "provider_email": identity.provider_email,
        "provider_username": identity.provider_username,
        "created_at": iso(identity.created_at),
    }


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "is_instance_owner": user.is_instance_owner,
        "has_password": user.password_hash is not None,
        "created_at": iso(user.created_at),
        "identities": [identity_out(i) for i in user.identities],
    }


def project_out(db: Session, project: Project, role: str) -> dict:
    counts = dict(
        db.execute(
            select(DataSource.kind, func.count())
            .where(DataSource.project_id == project.id, DataSource.deleted_at.is_(None))
            .group_by(DataSource.kind)
        ).all()
    )
    return {
        "id": project.id,
        "slug": project.slug,
        "name": project.name,
        "description": project.description,
        "owner_id": project.owner_id,
        "my_role": role,
        "created_at": iso(project.created_at),
        "updated_at": iso(project.updated_at),
        "data_source_counts": {"sql": counts.get("sql", 0), "nosql": counts.get("nosql", 0)},
    }
