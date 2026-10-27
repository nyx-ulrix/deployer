"""apps.env_encrypted as MEDIUMTEXT on MariaDB

An app's variables may total 64 KB (routers/apps.py); encrypted and base64'd that is about 87 KB,
which overflowed TEXT (65,535 bytes) with "Data too long for column 'env_encrypted'". SQLite has no
length limit, so only MariaDB changes.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name in ("mysql", "mariadb"):
        op.alter_column("apps", "env_encrypted", existing_type=sa.Text(), type_=mysql.MEDIUMTEXT(), nullable=False)


def downgrade() -> None:
    if op.get_bind().dialect.name in ("mysql", "mariadb"):
        op.alter_column("apps", "env_encrypted", existing_type=mysql.MEDIUMTEXT(), type_=sa.Text(), nullable=False)
