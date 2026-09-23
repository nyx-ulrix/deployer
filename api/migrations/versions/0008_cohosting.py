"""co-hosting (docs/COHOSTING.md): project_members.can_cohost, source_replicas, sync_conflicts, sync_versions

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("project_members") as batch_op:
        batch_op.add_column(sa.Column("can_cohost", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "source_replicas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "data_source_id", sa.String(36), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("position_primary", sa.JSON()),
        sa.Column("position_replica", sa.JSON()),
        sa.Column("id_offset", sa.Integer()),
        sa.Column("last_synced_at", sa.DateTime()),
        sa.Column("lag_seconds", sa.Float()),
        sa.Column("error", sa.Text()),
        sa.Column("warnings", sa.JSON()),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("data_source_id", "device_id", name="uq_replica_source_device"),
    )
    op.create_index("ix_source_replicas_data_source_id", "source_replicas", ["data_source_id"])
    op.create_index("ix_source_replicas_device_id", "source_replicas", ["device_id"])

    op.create_table(
        "sync_conflicts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "replica_id", sa.String(36), sa.ForeignKey("source_replicas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("table_name", sa.String(128), nullable=False),
        sa.Column("key_json", sa.JSON(), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("base_json", sa.JSON()),
        sa.Column("primary_json", sa.JSON()),
        sa.Column("replica_json", sa.JSON()),
        sa.Column("op_primary", sa.String(10)),
        sa.Column("op_replica", sa.String(10)),
        sa.Column("primary_changed_at", sa.DateTime()),
        sa.Column("replica_changed_at", sa.DateTime()),
        sa.Column("resolution", sa.String(10)),
        sa.Column("resolved_json", sa.JSON()),
        sa.Column("resolved_by_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sync_conflicts_replica_id", "sync_conflicts", ["replica_id"])
    op.create_index("ix_sync_conflicts_status", "sync_conflicts", ["status"])
    op.create_index("ix_sync_conflicts_replica_key", "sync_conflicts", ["replica_id", "table_name", "key_hash"])

    op.create_table(
        "sync_versions",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column(
            "replica_id", sa.String(36), sa.ForeignKey("source_replicas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("table_name", sa.String(128), nullable=False),
        sa.Column("key_json", sa.JSON(), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("version_hash", sa.String(64), nullable=False),
        sa.Column("json", sa.JSON()),
        sa.Column("origin", sa.String(10), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sync_versions_replica_id", "sync_versions", ["replica_id"])
    op.create_index("ix_sync_versions_synced_at", "sync_versions", ["synced_at"])
    op.create_index("ix_sync_versions_replica_key", "sync_versions", ["replica_id", "table_name", "key_hash"])


def downgrade() -> None:
    op.drop_table("sync_versions")
    op.drop_table("sync_conflicts")
    op.drop_table("source_replicas")
    with op.batch_alter_table("project_members") as batch_op:
        batch_op.drop_column("can_cohost")
