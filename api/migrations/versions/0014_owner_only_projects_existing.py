"""keep project creation open on instances that already have other users (audit L-02)

A-023 added `owner_only_projects`, on unless stored. On an update that silently stopped existing
members from creating projects. Instances that already have a non-owner user get it stored as off;
new installs (no users yet) and owners who already chose a value are left alone.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-02
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    stored = bind.scalar(sa.text("SELECT 1 FROM instance_settings WHERE `key` = 'owner_only_projects'"))
    members = bind.scalar(sa.text("SELECT 1 FROM users WHERE is_instance_owner = 0 LIMIT 1"))
    if stored or not members:
        return
    bind.execute(
        sa.text(
            "INSERT INTO instance_settings (`key`, value, is_secret, updated_at) "
            "VALUES ('owner_only_projects', 'false', 0, :now)"
        ),
        {"now": datetime.now(UTC).replace(tzinfo=None)},
    )


def downgrade() -> None:
    pass  # the stored value is a normal setting the owner can change
