"""devices backups domains

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Same table options as 0001: a table without them gets the server's default collation
# (utf8mb4_unicode_ci), and MariaDB refuses foreign keys between VARCHAR columns whose collations
# differ from the utf8mb4 tables created by 0001 (errno 150 "Foreign key constraint is incorrectly formed").
TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mariadb_engine": "InnoDB",
    "mariadb_charset": "utf8mb4",
}


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_copies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("artifact_type", sa.String(length=10), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("location", sa.String(length=10), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=True),
        sa.Column("ref", sa.String(length=500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTS,
    )
    op.create_index(op.f("ix_backup_copies_artifact_id"), "backup_copies", ["artifact_id"], unique=False)
    op.create_index(op.f("ix_backup_copies_device_id"), "backup_copies", ["device_id"], unique=False)
    op.create_table(
        "backup_log_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("start_point", sa.JSON(), nullable=True),
        sa.Column("end_point", sa.JSON(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTS,
    )
    op.create_index(
        op.f("ix_backup_log_segments_data_source_id"), "backup_log_segments", ["data_source_id"], unique=False
    )
    op.create_index(op.f("ix_backup_log_segments_end_at"), "backup_log_segments", ["end_at"], unique=False)
    op.create_index(op.f("ix_backup_log_segments_start_at"), "backup_log_segments", ["start_at"], unique=False)
    op.create_table(
        "backups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("data_source_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("engine", sa.String(length=20), nullable=True),
        sa.Column("trigger", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("consistent_point", sa.JSON(), nullable=True),
        sa.Column("schema_snapshot", sa.JSON(), nullable=True),
        sa.Column("row_counts", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verify_status", sa.String(length=10), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTS,
    )
    op.create_index(op.f("ix_backups_data_source_id"), "backups", ["data_source_id"], unique=False)
    op.create_index(op.f("ix_backups_project_id"), "backups", ["project_id"], unique=False)
    op.create_index(op.f("ix_backups_started_at"), "backups", ["started_at"], unique=False)
    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("sharing_mode", sa.String(length=12), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("os", sa.String(length=120), nullable=True),
        sa.Column("version", sa.String(length=32), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        **TABLE_OPTS,
    )
    op.create_index(op.f("ix_devices_owner_id"), "devices", ["owner_id"], unique=False)
    op.create_table(
        "device_enrollments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_code", sa.String(length=9), nullable=False),
        sa.Column("poll_secret_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("os", sa.String(length=120), nullable=True),
        sa.Column("version", sa.String(length=32), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("approved_by_id", sa.String(length=36), nullable=True),
        sa.Column("device_id", sa.String(length=36), nullable=True),
        sa.Column("device_token_encrypted", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_code"),
        **TABLE_OPTS,
    )
    op.create_table(
        "device_project_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "project_id", name="uq_device_project"),
        **TABLE_OPTS,
    )
    op.create_index(op.f("ix_device_project_grants_device_id"), "device_project_grants", ["device_id"], unique=False)
    op.create_index(op.f("ix_device_project_grants_project_id"), "device_project_grants", ["project_id"], unique=False)
    op.create_table(
        "domains",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("zone_id", sa.String(length=64), nullable=True),
        sa.Column("zone_name", sa.String(length=253), nullable=True),
        sa.Column("dns_record_id", sa.String(length=64), nullable=True),
        sa.Column("target_type", sa.String(length=12), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hostname"),
        **TABLE_OPTS,
    )
    op.create_index(op.f("ix_domains_project_id"), "domains", ["project_id"], unique=False)
    op.create_table(
        "backup_policies",
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("schedule", sa.String(length=10), nullable=False),
        sa.Column("keep_hourly", sa.Integer(), nullable=False),
        sa.Column("keep_daily", sa.Integer(), nullable=False),
        sa.Column("keep_weekly", sa.Integer(), nullable=False),
        sa.Column("keep_monthly", sa.Integer(), nullable=False),
        sa.Column("pitr_enabled", sa.Boolean(), nullable=False),
        sa.Column("pitr_window_days", sa.Integer(), nullable=False),
        sa.Column("copy_to_primary", sa.Boolean(), nullable=False),
        sa.Column("copy_to_device_id", sa.String(length=36), nullable=True),
        sa.Column("safety_snapshots", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["copy_to_device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("data_source_id"),
        **TABLE_OPTS,
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("data_source_id", sa.String(length=36), nullable=True),
        sa.Column("device_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTS,
    )
    op.create_index(op.f("ix_jobs_created_at"), "jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_jobs_data_source_id"), "jobs", ["data_source_id"], unique=False)
    op.create_index(op.f("ix_jobs_device_id"), "jobs", ["device_id"], unique=False)
    op.create_index(op.f("ix_jobs_project_id"), "jobs", ["project_id"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_type"), "jobs", ["type"], unique=False)
    # Batch mode: plain ALTERs on MariaDB, copy-and-move on SQLite (which can't add constraints in place).
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.add_column(sa.Column("device_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("deleted_name", sa.String(length=63), nullable=True))
        batch_op.create_index(op.f("ix_data_sources_deleted_at"), ["deleted_at"], unique=False)
        batch_op.create_index(op.f("ix_data_sources_device_id"), ["device_id"], unique=False)
        batch_op.create_foreign_key("fk_data_sources_device_id", "devices", ["device_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    # Drop the FK before its index, and whole tables rather than their indexes (MariaDB refuses to drop
    # an index that a foreign key still needs).
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.drop_constraint("fk_data_sources_device_id", type_="foreignkey")
        batch_op.drop_index(op.f("ix_data_sources_device_id"))
        batch_op.drop_index(op.f("ix_data_sources_deleted_at"))
        batch_op.drop_column("deleted_name")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("device_id")
    for table in (
        "jobs",
        "backup_policies",
        "domains",
        "device_project_grants",
        "device_enrollments",
        "backups",
        "backup_log_segments",
        "backup_copies",
        "devices",
    ):
        op.drop_table(table)
