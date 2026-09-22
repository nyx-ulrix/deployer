"""query editor: run log and saved queries

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Same table options as 0001/0002 (see 0002 for why: FK collation on MariaDB).
TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mariadb_engine": "InnoDB",
    "mariadb_charset": "utf8mb4",
}


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("source_name", sa.String(length=63), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("engine", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("statements", sa.Integer(), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("affected_rows", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("read_only", sa.Boolean(), nullable=False),
        sa.Column("layout", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTS,
    )
    op.create_index(op.f("ix_query_runs_created_at"), "query_runs", ["created_at"], unique=False)
    op.create_index(op.f("ix_query_runs_data_source_id"), "query_runs", ["data_source_id"], unique=False)
    op.create_index(op.f("ix_query_runs_user_id"), "query_runs", ["user_id"], unique=False)
    op.create_index("ix_query_runs_project_created", "query_runs", ["project_id", "created_at"], unique=False)
    op.create_table(
        "saved_queries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("data_source_id", sa.String(length=36), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("folder", sa.String(length=120), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTS,
    )
    op.create_index("ix_saved_queries_project_updated", "saved_queries", ["project_id", "updated_at"], unique=False)


def downgrade() -> None:
    # Whole tables rather than their indexes first (MariaDB refuses to drop an index a FK still needs).
    op.drop_table("saved_queries")
    op.drop_table("query_runs")
