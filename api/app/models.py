"""Platform metadata schema. Source of truth for docs/ARCHITECTURE.md "Data model".

Every change here needs an Alembic migration in api/migrations/versions/.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ROLES = ("viewer", "developer", "admin", "owner")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    # Stored naive-UTC: MariaDB DATETIME has no time zone.
    return datetime.now(UTC).replace(tzinfo=None)


def role_rank(role: str) -> int:
    return ROLES.index(role)


class InstanceSetting(Base):
    __tablename__ = "instance_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    # Plain JSON-encoded value, or an app.crypto encrypted string when is_secret.
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_instance_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    identities: Mapped[list["UserIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="UserIdentity.created_at"
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_identity_provider_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # google | github
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(255))
    provider_username: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="identities")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    replaced_by_id: Mapped[str | None] = mapped_column(String(36))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    members: Mapped[list["ProjectMember"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    data_sources: Mapped[list["DataSource"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_member_project_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # see ROLES
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class ProjectInvite(Base):
    __tablename__ = "project_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))  # when set, only this email may accept
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_data_source_project_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(63), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # sql | nosql
    engine: Mapped[str] = mapped_column(String(20), nullable=False)  # mariadb | mysql | postgresql | mongodb
    mode: Mapped[str] = mapped_column(String(10), nullable=False)  # managed | external
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # app.crypto.encrypt_json of the connection config:
    #   sql:   {host, port, username, password, database, tls}
    #   nosql: {uri, database}  (managed Mongo also stores username/password)
    config_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="unknown", nullable=False)  # ok | error | unknown
    status_message: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Host device for managed sources; NULL = the main server. See docs/DEVICES.md.
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    # Soft delete ("Recently deleted", docs/BACKUPS.md). While deleted, `name` is replaced by a unique
    # placeholder so the name can be reused, and the original is kept in `deleted_name`.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    deleted_name: Mapped[str | None] = mapped_column(String(63))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="data_sources")


class SchemaLink(Base):
    __tablename__ = "schema_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    from_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    from_entity: Mapped[str] = mapped_column(String(128), nullable=False)
    from_field: Mapped[str] = mapped_column(String(255), nullable=False)
    to_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    to_entity: Mapped[str] = mapped_column(String(128), nullable=False)
    to_field: Mapped[str] = mapped_column(String(255), nullable=False)
    cardinality: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # anon | service
    prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # app.crypto.encrypt_secret of the full secret, for "reveal"; NULL for keys created before 0005.
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


# --- Host devices (docs/DEVICES.md) ---------------------------------------------------------------


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="active", nullable=False)  # active | disabled
    roles: Mapped[list] = mapped_column(JSON, nullable=False)  # ["database_host", "backup_storage"]
    # my_projects | selected
    sharing_mode: Mapped[str] = mapped_column(String(12), default="my_projects", nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255))
    os: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[str | None] = mapped_column(String(32))
    capabilities: Mapped[dict | None] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DeviceEnrollment(Base):
    __tablename__ = "device_enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_code: Mapped[str] = mapped_column(String(9), unique=True, nullable=False)  # ABCD-EFGH
    poll_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255))
    os: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[str | None] = mapped_column(String(32))
    capabilities: Mapped[dict | None] = mapped_column(JSON)
    # pending | approved | denied | expired | consumed
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    # Raw device token encrypted with MASTER_KEY; kept only between approval and the device's poll.
    device_token_encrypted: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DeviceProjectGrant(Base):
    __tablename__ = "device_project_grants"
    __table_args__ = (UniqueConstraint("device_id", "project_id", name="uq_device_project"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# --- Jobs, backups & recovery (docs/BACKUPS.md) ---------------------------------------------------


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)  # backup.snapshot, restore, ...
    status: Mapped[str] = mapped_column(String(10), default="queued", index=True, nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    data_source_id: Mapped[str | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"), index=True)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class BackupPolicy(Base):
    __tablename__ = "backup_policies"

    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    schedule: Mapped[str] = mapped_column(String(10), default="hourly", nullable=False)  # hourly | every_6h | daily
    keep_hourly: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    keep_daily: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    keep_weekly: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    keep_monthly: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    pitr_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pitr_window_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    copy_to_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    copy_to_device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    safety_snapshots: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # NULL for platform (metadata DB) backups. No FK: backups outlive purged sources until pruned.
    data_source_id: Mapped[str | None] = mapped_column(String(36), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)
    scope: Mapped[str] = mapped_column(String(10), default="source", nullable=False)  # source | platform
    engine: Mapped[str | None] = mapped_column(String(20))
    # scheduled | manual | pre_restore | pre_drop | pre_delete | pre_move | final
    trigger: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="running", nullable=False)  # running|succeeded|failed
    label: Mapped[str | None] = mapped_column(String(120))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    # {gtid, binlog_file, binlog_pos} for MariaDB | {oplog_ts_start, oplog_ts_end} for MongoDB
    consistent_point: Mapped[dict | None] = mapped_column(JSON)
    schema_snapshot: Mapped[dict | None] = mapped_column(JSON)  # SourceSchema at snapshot time
    row_counts: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    verify_status: Mapped[str | None] = mapped_column(String(10))  # ok | failed
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by_id: Mapped[str | None] = mapped_column(String(36))
    job_id: Mapped[str | None] = mapped_column(String(36))


class BackupLogSegment(Base):
    __tablename__ = "backup_log_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    data_source_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # binlog | oplog
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    start_point: Mapped[dict | None] = mapped_column(JSON)
    end_point: Mapped[dict | None] = mapped_column(JSON)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class BackupCopy(Base):
    __tablename__ = "backup_copies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    artifact_type: Mapped[str] = mapped_column(String(10), nullable=False)  # backup | segment
    artifact_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    location: Mapped[str] = mapped_column(String(10), nullable=False)  # local | device | primary
    device_id: Mapped[str | None] = mapped_column(String(36), index=True)  # where the bytes live; NULL = main server
    ref: Mapped[str] = mapped_column(String(500), nullable=False)  # path inside that location's backup store
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)  # pending | ok | missing
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# --- Remote access & domains (docs/REMOTE_ACCESS.md) ----------------------------------------------


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    hostname: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="cloudflare", nullable=False)
    zone_id: Mapped[str | None] = mapped_column(String(64))
    zone_name: Mapped[str | None] = mapped_column(String(253))
    dns_record_id: Mapped[str | None] = mapped_column(String(64))
    # dashboard | project | app (docs/DEPLOYMENTS.md: app hostnames route to the app's container)
    target_type: Mapped[str] = mapped_column(String(12), default="dashboard", nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    app_id: Mapped[str | None] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)  # pending | active | error
    status_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# --- Query editor: run log & saved queries (docs/QUERY_EDITOR.md) ---------------------------------


class QueryRun(Base):
    """One console/editor run. The only place query text is stored (audit logs keep counts only)."""

    __tablename__ = "query_runs"
    __table_args__ = (Index("ix_query_runs_project_created", "project_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    # No FK: the log outlives the data source. `source_name` / `user_email` are snapshots for the same reason.
    data_source_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(63), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # sql | nosql
    engine: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # ok | error | timeout | refused
    statements: Mapped[int] = mapped_column(Integer, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False)  # rows returned, or documents for MongoDB
    affected_rows: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)  # already redacted by query_console
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    layout: Mapped[str] = mapped_column(String(10), nullable=False)  # terminal | editor | api
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class SavedQuery(Base):
    __tablename__ = "saved_queries"
    __table_args__ = (Index("ix_saved_queries_project_updated", "project_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    data_source_id: Mapped[str | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    folder: Mapped[str | None] = mapped_column(String(120))
    # Opaque to the API: the dashboard stores its notebook document ({"cells": [{id, text}]}) here.
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # sql | nosql | any
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    # Current version number; every text change appends a SavedQueryVersion and bumps this.
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)


class SavedQueryVersion(Base):
    """Append-only history of a saved query's text (docs/QUERY_EDITOR.md "Phase 2 — versions")."""

    __tablename__ = "saved_query_versions"
    __table_args__ = (
        UniqueConstraint("saved_query_id", "version", name="uq_saved_query_version"),
        Index("ix_saved_query_versions_query_version", "saved_query_id", "version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    saved_query_id: Mapped[str] = mapped_column(ForeignKey("saved_queries.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Snapshots, no FK: history outlives the author's account.
    author_id: Mapped[str] = mapped_column(String(36), nullable=False)
    author_email: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# --- Apps & deployments (docs/DEPLOYMENTS.md) ----------------------------------------------------


class App(Base):
    __tablename__ = "apps"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_app_project_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)  # DNS-safe, unique per project
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)  # https only
    branch: Mapped[str] = mapped_column(String(120), default="main", nullable=False)
    root_dir: Mapped[str] = mapped_column(String(200), default=".", nullable=False)
    preset: Mapped[str] = mapped_column(String(12), nullable=False)  # static | node | python | dockerfile
    install_command: Mapped[str | None] = mapped_column(String(500))
    build_command: Mapped[str | None] = mapped_column(String(500))
    start_command: Mapped[str | None] = mapped_column(String(500))
    output_dir: Mapped[str | None] = mapped_column(String(200))
    container_port: Mapped[int | None] = mapped_column(Integer)
    env_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # encrypt_json({KEY: value})
    repo_token_encrypted: Mapped[str | None] = mapped_column(Text)  # GitHub token for private repos; never logged
    webhook_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"))
    port: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)  # Caddy listener, 8100-8199, for life
    live_deployment_id: Mapped[str | None] = mapped_column(String(36))  # no FK: circular with deployments
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True, nullable=False)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    # queued | building | deploying | live | failed | cancelled | superseded
    status: Mapped[str] = mapped_column(String(12), default="queued", nullable=False)
    trigger: Mapped[str] = mapped_column(String(10), nullable=False)  # manual | webhook | rollback
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    commit_message: Mapped[str | None] = mapped_column(String(200))
    branch: Mapped[str] = mapped_column(String(120), nullable=False)
    image_tag: Mapped[str | None] = mapped_column(String(200))
    container_name: Mapped[str | None] = mapped_column(String(100))
    log: Mapped[str] = mapped_column(Text, default="", nullable=False)  # capped 1 MB, tail kept
    error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    rollback_of: Mapped[str | None] = mapped_column(String(36))
