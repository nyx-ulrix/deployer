"""Cloud connections (instance owner) and the hosting targets apps can use (docs/CLOUD.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from app.deps import DbSession, InstanceOwner, ProjectAccess, require_role
from app.errors import ApiError
from app.models import Project
from app.services import audit, cloud

router = APIRouter(tags=["cloud"])

Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]
Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]


class AwsCredentials(BaseModel):
    access_key_id: str = Field(max_length=40)
    secret_access_key: str = Field(max_length=100)
    region: str = Field(max_length=30)
    role_arn: str | None = Field(default=None, max_length=600)


class FirebaseCredentials(BaseModel):
    service_account_json: str = Field(max_length=20_000)
    project_id: str | None = Field(default=None, max_length=40)
    region: str | None = Field(default=None, max_length=30)


class ConnectionCreate(BaseModel):
    provider: Literal["aws", "firebase"]
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = Field(default=None, max_length=36)  # None: every project may use it
    aws: AwsCredentials | None = None
    firebase: FirebaseCredentials | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()


@router.get("/instance/cloud")
def list_connections(owner: InstanceOwner, db: DbSession) -> dict:
    return {
        "connections": [cloud.connection_out(c, db) for c in cloud.list_connections(db)],
        "targets": cloud.TARGETS,
    }


@router.get("/instance/cloud/requirements")
def requirements(owner: InstanceOwner) -> dict:
    """The least-privilege IAM policy for the AWS user, the Google roles and APIs for the service account."""
    return cloud.requirements()


@router.post("/instance/cloud", status_code=201)
def create_connection(body: ConnectionCreate, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    creds = body.aws if body.provider == "aws" else body.firebase
    if creds is None:
        raise ApiError(422, "validation_error", f"Send the {body.provider} credentials", {"field": body.provider})
    if body.project_id and db.get(Project, body.project_id) is None:
        raise ApiError(422, "validation_error", "Project not found", {"field": "project_id"})
    conn = cloud.create_connection(
        db,
        provider=body.provider,
        name=body.name,
        project_id=body.project_id,
        raw=creds.model_dump(),
        user_id=owner.id,
    )
    # Never the credentials: provider, name and scope only.
    audit.record(
        db,
        "cloud.connection_create",
        request=request,
        user_id=owner.id,
        project_id=body.project_id,
        connection_id=conn.id,
        provider=conn.provider,
    )
    db.commit()
    return cloud.connection_out(conn, db)


@router.post("/instance/cloud/{connection_id}/check")
def check_connection(connection_id: str, owner: InstanceOwner, db: DbSession) -> dict:
    conn = cloud.check_connection(db, cloud.get_connection(db, connection_id))
    db.commit()
    return cloud.connection_out(conn, db)


@router.delete("/instance/cloud/{connection_id}")
def delete_connection(connection_id: str, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    conn = cloud.get_connection(db, connection_id)
    cloud.delete_connection(db, conn)
    audit.record(db, "cloud.connection_delete", request=request, user_id=owner.id, connection_id=connection_id)
    db.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/cloud/connections")
def project_connections(access: Admin, db: DbSession) -> list[dict]:
    """Read-only: the connections this project's apps may use (instance-wide + the project's own)."""
    return [cloud.connection_out(c) for c in cloud.list_connections(db, access.project.id)]


@router.get("/projects/{project_id}/cloud/targets")
def project_targets(access: Viewer, db: DbSession) -> list[dict]:
    return cloud.targets_out(db, access.project.id)
