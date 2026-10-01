"""DATETIME(6) on MariaDB: keep the microseconds that row order and equality rely on

Plain DATETIME drops them, so rows written in the same second tied in every ORDER BY created_at.
SQLite keeps microseconds already: nothing to do there.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _set_fsp(fsp: int) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    inspector = sa.inspect(bind)
    for table in inspector.get_table_names():
        # MariaDB DDL is not transactional: columns a failed earlier run already changed are skipped.
        changes = [
            f"MODIFY `{c['name']}` DATETIME({fsp}) {'NULL' if c['nullable'] else 'NOT NULL'}"
            for c in inspector.get_columns(table)
            if isinstance(c["type"], mysql.DATETIME) and (c["type"].fsp or 0) != fsp
        ]
        if changes:  # one ALTER per table: one table rebuild
            op.execute(f"ALTER TABLE `{table}` {', '.join(changes)}")


def upgrade() -> None:
    _set_fsp(6)


def downgrade() -> None:
    _set_fsp(0)
