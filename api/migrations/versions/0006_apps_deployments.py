"""apps and deployments (docs/DEPLOYMENTS.md): push-to-deploy pipeline; app hostnames in `domains`

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# See 0002: explicit charset so foreign keys to the utf8mb4 tables of 0001 are accepted by MariaDB.
TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mariadb_engine": "InnoDB",
    "mariadb_charset": "utf8mb4",
}


def upgrade() -> None:
    op.create_table(
        "apps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("repo_url", sa.String(length=500), nullable=False),
        sa.Column("branch", sa.String(length=120), nullable=False),
        sa.Column("root_dir", sa.String(length=200), nullable=False),
        sa.Column("preset", sa.String(length=12), nullable=False),
        sa.Column("install_command", sa.String(length=500), nullable=True),
        sa.Column("build_command", sa.String(length=500), nullable=True),
        sa.Column("start_command", sa.String(length=500), nullable=True),
        sa.Column("output_dir", sa.String(length=200), nullable=True),
        sa.Column("container_port", sa.Integer(), nullable=True),
        sa.Column("env_encrypted", sa.Text(), nullable=False),
        sa.Column("repo_token_encrypted", sa.Text(), nullable=True),
        sa.Column("webhook_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("api_key_id", sa.String(length=36), nullable=True),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("live_deployment_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("port"),
        sa.UniqueConstraint("project_id", "slug", name="uq_app_project_slug"),
        **TABLE_OPTS,
    )
    op.create_index(op.f("ix_apps_project_id"), "apps", ["project_id"], unique=False)
    op.create_table(
        "deployments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("trigger", sa.String(length=10), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=True),
        sa.Column("commit_message", sa.String(length=200), nullable=True),
        sa.Column("branch", sa.String(length=120), nullable=False),
        sa.Column("image_tag", sa.String(length=200), nullable=True),
        sa.Column("container_name", sa.String(length=100), nullable=True),
        sa.Column("log", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("rollback_of", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTS,
    )
    op.create_index(op.f("ix_deployments_app_id"), "deployments", ["app_id"], unique=False)
    op.create_index(op.f("ix_deployments_created_at"), "deployments", ["created_at"], unique=False)
    with op.batch_alter_table("domains") as batch_op:
        batch_op.add_column(sa.Column("app_id", sa.String(length=36), nullable=True))
        batch_op.create_index(op.f("ix_domains_app_id"), ["app_id"], unique=False)
        batch_op.create_foreign_key("fk_domains_app_id_apps", "apps", ["app_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    with op.batch_alter_table("domains") as batch_op:
        batch_op.drop_constraint("fk_domains_app_id_apps", type_="foreignkey")
        batch_op.drop_index(op.f("ix_domains_app_id"))
        batch_op.drop_column("app_id")
    op.drop_index(op.f("ix_deployments_created_at"), table_name="deployments")
    op.drop_index(op.f("ix_deployments_app_id"), table_name="deployments")
    op.drop_table("deployments")
    op.drop_index(op.f("ix_apps_project_id"), table_name="apps")
    op.drop_table("apps")
