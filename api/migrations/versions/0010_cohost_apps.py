"""co-hosting phase 2 (docs/COHOSTING.md "Websites on both PCs"): apps.cohost,
apps.cohost_share_repo_access, app_replicas, sync_versions.echo

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Same table options as 0001-0009: without them MariaDB gives a new table the server's default
# collation, and foreign keys to the utf8mb4 tables fail with errno 150 ("incorrectly formed").
TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mariadb_engine": "InnoDB",
    "mariadb_charset": "utf8mb4",
}

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _create_app_replicas() -> None:
    op.create_table(
        "app_replicas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("app_id", sa.String(36), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("deployment_id", sa.String(36)),
        sa.Column("image_tag", sa.String(200)),
        sa.Column("container_name", sa.String(100)),
        sa.Column("port", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("last_seen_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("app_id", "device_id", name="uq_app_replica_device"),
        **TABLE_OPTS,
    )


def upgrade() -> None:
    # MariaDB DDL is not transactional: every step checks what a failed earlier run already did.
    missing = [c for c in ("cohost", "cohost_share_repo_access") if c not in _columns("apps")]
    if missing:
        with op.batch_alter_table("apps") as batch_op:
            for name in missing:
                batch_op.add_column(sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))
    if "echo" not in _columns("sync_versions"):
        with op.batch_alter_table("sync_versions") as batch_op:
            batch_op.add_column(sa.Column("echo", sa.String(10), nullable=True))

    if not sa.inspect(op.get_bind()).has_table("app_replicas"):
        _create_app_replicas()
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("app_replicas")}
    for column in ("app_id", "device_id"):
        name = f"ix_app_replicas_{column}"
        if name not in indexes:
            op.create_index(name, "app_replicas", [column])


def downgrade() -> None:
    op.drop_table("app_replicas")
    with op.batch_alter_table("sync_versions") as batch_op:
        batch_op.drop_column("echo")
    with op.batch_alter_table("apps") as batch_op:
        batch_op.drop_column("cohost_share_repo_access")
        batch_op.drop_column("cohost")
