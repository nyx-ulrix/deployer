"""github_connections + apps.github_connection_user_id / github_hook_id
(docs/DEPLOYMENTS.md "Connect a Git repository")

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

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
