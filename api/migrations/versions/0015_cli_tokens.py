"""command-line tokens (docs/CLI.md): cli_tokens and cli_logins

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# Same table options as 0001-0014: without them MariaDB gives a new table the server's default
# collation, and foreign keys to the utf8mb4 tables fail with errno 150 ("incorrectly formed").
TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mariadb_engine": "InnoDB",
    "mariadb_charset": "utf8mb4",
}

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _datetime() -> sa.types.TypeEngine:
    # DATETIME(6) on MariaDB, as 0012 made every other column.
    return sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql", "mariadb")


def upgrade() -> None:
    # MariaDB DDL is not transactional: every step checks what a failed earlier run already did.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("cli_tokens"):
        op.create_table(
            "cli_tokens",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("prefix", sa.String(16), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("last_used_at", _datetime(), nullable=True),
            sa.Column("revoked_at", _datetime(), nullable=True),
            sa.Column("created_at", _datetime(), nullable=False),
            sa.UniqueConstraint("token_hash"),
            **TABLE_OPTS,
        )
    if "ix_cli_tokens_user_id" not in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("cli_tokens")}:
        op.create_index("ix_cli_tokens_user_id", "cli_tokens", ["user_id"])

    if not inspector.has_table("cli_logins"):
        op.create_table(
            "cli_logins",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_code", sa.String(9), nullable=False),
            sa.Column("poll_secret_hash", sa.String(64), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("hostname", sa.String(255), nullable=True),
            sa.Column("os", sa.String(120), nullable=True),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("approved_by_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("token_encrypted", sa.Text(), nullable=True),
            sa.Column("expires_at", _datetime(), nullable=False),
            sa.Column("created_at", _datetime(), nullable=False),
            sa.UniqueConstraint("user_code"),
            **TABLE_OPTS,
        )


def downgrade() -> None:
    op.drop_table("cli_logins")
    op.drop_index("ix_cli_tokens_user_id", table_name="cli_tokens")
    op.drop_table("cli_tokens")
