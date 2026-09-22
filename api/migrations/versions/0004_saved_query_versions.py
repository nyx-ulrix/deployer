"""saved query versions: strict version control on saved queries

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-22
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

# Same table options as 0001..0003 (see 0002 for why: FK collation on MariaDB).
TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mariadb_engine": "InnoDB",
    "mariadb_charset": "utf8mb4",
}


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("saved_queries") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_table(
        "saved_query_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("saved_query_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=False),
        sa.Column("author_email", sa.String(length=255), nullable=False),
        sa.Column("message", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["saved_query_id"], ["saved_queries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("saved_query_id", "version", name="uq_saved_query_version"),
        **TABLE_OPTS,
    )
    op.create_index(
        "ix_saved_query_versions_query_version", "saved_query_versions", ["saved_query_id", "version"], unique=False
    )

    # Backfill: one version-1 row per existing saved query, authored by its owner.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT q.id, q.query_text, q.owner_id, u.email, q.updated_at "
            "FROM saved_queries q LEFT JOIN users u ON u.id = q.owner_id"
        )
    ).all()
    if rows:
        conn.execute(
            sa.text(
                "INSERT INTO saved_query_versions "
                "(id, saved_query_id, version, query_text, author_id, author_email, message, created_at) "
                "VALUES (:id, :qid, 1, :text, :author, :email, :message, :created_at)"
            ),
            [
                {
                    "id": str(uuid4()),
                    "qid": qid,
                    "text": text,
                    "author": owner_id,
                    "email": email or "",
                    "message": "Imported from before version history",
                    "created_at": updated_at,
                }
                for qid, text, owner_id, email, updated_at in rows
            ],
        )


def downgrade() -> None:
    op.drop_table("saved_query_versions")
    with op.batch_alter_table("saved_queries") as batch_op:
        batch_op.drop_column("version")
