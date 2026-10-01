"""cloud databases phase C2 (docs/CLOUD.md): data_sources.cloud_connection_id / cloud_state

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FK = "fk_data_sources_cloud_connection_id"


def upgrade() -> None:
    # MariaDB DDL is not transactional: every step checks what a failed earlier run already did.
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("data_sources")}
    has_fk = any(fk.get("name") == FK for fk in inspector.get_foreign_keys("data_sources"))
    if {"cloud_connection_id", "cloud_state"} <= columns and has_fk:
        return
    with op.batch_alter_table("data_sources") as batch_op:
        if "cloud_connection_id" not in columns:
            batch_op.add_column(sa.Column("cloud_connection_id", sa.String(36), nullable=True))
        if not has_fk:
            batch_op.create_foreign_key(FK, "cloud_connections", ["cloud_connection_id"], ["id"], ondelete="SET NULL")
        if "cloud_state" not in columns:
            batch_op.add_column(sa.Column("cloud_state", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.drop_constraint(FK, type_="foreignkey")
        batch_op.drop_column("cloud_state")
        batch_op.drop_column("cloud_connection_id")
