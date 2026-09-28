"""cloud hosting phase C1 (docs/CLOUD.md): cloud_connections, apps.target / cloud_connection_id /
cloud_state, deployments.target_url, domains.dns_records

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Same table options as 0001-0010: without them MariaDB gives a new table the server's default
# collation, and foreign keys to the utf8mb4 tables fail with errno 150 ("incorrectly formed").
TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mariadb_engine": "InnoDB",
    "mariadb_charset": "utf8mb4",
}

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # MariaDB DDL is not transactional: every step checks what a failed earlier run already did.
    if not sa.inspect(op.get_bind()).has_table("cloud_connections"):
        op.create_table(
            "cloud_connections",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("provider", sa.String(10), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE")),
            sa.Column("config_encrypted", sa.Text(), nullable=False),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("status_message", sa.Text()),
            sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            **TABLE_OPTS,
        )
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("cloud_connections")}
    if "ix_cloud_connections_project_id" not in indexes:
        op.create_index("ix_cloud_connections_project_id", "cloud_connections", ["project_id"])

    apps = _columns("apps")
    if not {"target", "cloud_connection_id", "cloud_state"} <= apps:
        with op.batch_alter_table("apps") as batch_op:
            if "target" not in apps:
                batch_op.add_column(sa.Column("target", sa.String(20), nullable=False, server_default="local"))
            if "cloud_connection_id" not in apps:
                batch_op.add_column(sa.Column("cloud_connection_id", sa.String(36), nullable=True))
                batch_op.create_foreign_key(
                    "fk_apps_cloud_connection_id",
                    "cloud_connections",
                    ["cloud_connection_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            if "cloud_state" not in apps:
                batch_op.add_column(sa.Column("cloud_state", sa.JSON(), nullable=True))
    if "target_url" not in _columns("deployments"):
        with op.batch_alter_table("deployments") as batch_op:
            batch_op.add_column(sa.Column("target_url", sa.String(500), nullable=True))
    if "dns_records" not in _columns("domains"):
        with op.batch_alter_table("domains") as batch_op:
            batch_op.add_column(sa.Column("dns_records", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("domains") as batch_op:
        batch_op.drop_column("dns_records")
    with op.batch_alter_table("deployments") as batch_op:
        batch_op.drop_column("target_url")
    with op.batch_alter_table("apps") as batch_op:
        batch_op.drop_constraint("fk_apps_cloud_connection_id", type_="foreignkey")
        batch_op.drop_column("cloud_state")
        batch_op.drop_column("cloud_connection_id")
        batch_op.drop_column("target")
    op.drop_table("cloud_connections")
