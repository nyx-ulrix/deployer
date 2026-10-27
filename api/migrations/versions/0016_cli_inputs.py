"""input requests (docs/CLI.md "Input requests"): cli_inputs

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# Same table options as 0001-0015: without them MariaDB gives a new table the server's default
# collation, and foreign keys to the utf8mb4 tables fail with errno 150 ("incorrectly formed").
TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mariadb_engine": "InnoDB",
    "mariadb_charset": "utf8mb4",
}

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _datetime() -> sa.types.TypeEngine:
    # DATETIME(6) on MariaDB, as 0012 made every other column.
    return sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql", "mariadb")


def upgrade() -> None:
    # MariaDB DDL is not transactional: every step checks what a failed earlier run already did.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("cli_inputs"):
        op.create_table(
            "cli_inputs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("cli_token_id", sa.String(36), sa.ForeignKey("cli_tokens.id", ondelete="SET NULL")),
            sa.Column("token_name", sa.String(80), nullable=True),
            sa.Column("token_prefix", sa.String(16), nullable=True),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("fields", sa.JSON(), nullable=False),
            sa.Column("app_ids", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False),
            # MEDIUMTEXT on MariaDB: the 48 KB of values, encrypted and base64'd, don't fit TEXT (64 KB).
            sa.Column(
                "values_encrypted", sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql", "mariadb"), nullable=True
            ),
            sa.Column("expires_at", _datetime(), nullable=False),
            sa.Column("submitted_at", _datetime(), nullable=True),
            sa.Column("created_at", _datetime(), nullable=False),
            **TABLE_OPTS,
        )
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("cli_inputs")}
    if "ix_cli_inputs_user_id" not in indexes:
        op.create_index("ix_cli_inputs_user_id", "cli_inputs", ["user_id"])
    if "ix_cli_inputs_cli_token_id" not in indexes:
        op.create_index("ix_cli_inputs_cli_token_id", "cli_inputs", ["cli_token_id"])


def downgrade() -> None:
    op.drop_index("ix_cli_inputs_cli_token_id", table_name="cli_inputs")
    op.drop_index("ix_cli_inputs_user_id", table_name="cli_inputs")
    op.drop_table("cli_inputs")
