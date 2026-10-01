"""Alembic migrations on a real MariaDB 11: the unit suite upgrades SQLite only (its MariaDB schema
comes from `create_all`).

Skipped unless the server is configured (see test_managed_databases.py for the docker command)::

    DEPLOYER_IT_MARIADB_URL=mysql://root:<password>@127.0.0.1:13306 pytest tests/integration/test_migrations_mariadb.py
"""

import os
import secrets
from urllib.parse import urlsplit

import pymysql
import pytest
from alembic import command

MARIADB_URL = os.environ.get("DEPLOYER_IT_MARIADB_URL")

pytestmark = pytest.mark.skipif(not MARIADB_URL, reason="set DEPLOYER_IT_MARIADB_URL")


def test_upgrade_to_head_stores_microseconds(migration_db):
    cfg, _ = migration_db
    m = urlsplit(MARIADB_URL)
    name = f"it_migrations_{secrets.token_hex(4)}"
    root = pymysql.connect(host=m.hostname, port=m.port or 3306, user=m.username, password=m.password, autocommit=True)
    try:
        with root.cursor() as cur:
            cur.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        # ConfigParser interpolates '%', which a URL-encoded password may contain.
        cfg.set_main_option("sqlalchemy.url", f"mysql+pymysql://{m.netloc}/{name}?charset=utf8mb4".replace("%", "%%"))
        command.upgrade(cfg, "head")
        with root.cursor() as cur:
            cur.execute(
                "SELECT table_name, column_name, datetime_precision FROM information_schema.columns"
                " WHERE table_schema = %s AND data_type = 'datetime'",
                (name,),
            )
            columns = cur.fetchall()
        assert columns and [c for c in columns if c[2] != 6] == []  # 0012
    finally:
        with root.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{name}`")
        root.close()
