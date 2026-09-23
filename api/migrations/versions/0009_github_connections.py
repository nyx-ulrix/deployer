"""github_connections + apps.github_connection_user_id / github_hook_id
(docs/DEPLOYMENTS.md "Connect a Git repository")

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Same table options as 0001-0006: without them MariaDB gives a new table the server's default
# collation, and foreign keys to the utf8mb4 tables fail with errno 150 ("incorrectly formed").
TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mariadb_engine": "InnoDB",
    "mariadb_charset": "utf8mb4",
}

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "github_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
        ),
        sa.Column("github_login", sa.String(100), nullable=False),
        sa.Column("github_user_id", sa.String(40), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        **TABLE_OPTS,
    )
    with op.batch_alter_table("apps") as batch_op:
        batch_op.add_column(sa.Column("github_connection_user_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("github_hook_id", sa.String(40), nullable=True))
        batch_op.create_foreign_key(
            "fk_apps_github_connection_user_id_users",
            "users",
            ["github_connection_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("apps") as batch_op:
        batch_op.drop_constraint("fk_apps_github_connection_user_id_users", type_="foreignkey")
        batch_op.drop_column("github_hook_id")
        batch_op.drop_column("github_connection_user_id")
    op.drop_table("github_connections")
