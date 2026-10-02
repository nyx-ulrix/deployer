"""Migration checks: every migration table gets the utf8mb4 options, and head matches the models
(on SQLite, and on MariaDB too in CI's "Unit suite on MariaDB" job).

The test database is SQLite, which ignores collations and foreign-key forms, so a `create_table`
without them only fails on a real MariaDB (errno 150 "Foreign key constraint is incorrectly
formed") - exactly how 0008 broke an installed instance.
"""

import os
import re
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parent.parent / "migrations" / "versions"


def test_every_create_table_passes_table_opts():
    missing = []
    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for call in re.finditer(r"op\.create_table\((.*?)\n    \)", text, flags=re.S):
            if "**TABLE_OPTS" not in call.group(1):
                name = re.search(r'"(\w+)"', call.group(1))
                missing.append(f"{path.name}: {name.group(1) if name else '?'}")
    assert not missing, "create_table without **TABLE_OPTS: " + ", ".join(missing)


@pytest.fixture(params=["sqlite", "mysql"])
def head_db_url(request, migration_db):
    """A scratch database upgraded to head: SQLite always, and a throwaway database on the MariaDB test
    server when DEPLOYER_TEST_DATABASE_URL points at one (the MariaDB-only DATETIME(6) migration and the
    model variant are only compared there)."""
    from alembic import command
    from sqlalchemy import create_engine, make_url, text

    cfg, db_file = migration_db
    if request.param == "sqlite":
        url = f"sqlite:///{db_file.as_posix()}"
        command.upgrade(cfg, "head")
        yield url
        return
    base = os.environ.get("DEPLOYER_TEST_DATABASE_URL", "")
    if not base.startswith("mysql"):
        pytest.skip("DEPLOYER_TEST_DATABASE_URL is not a MariaDB database")
    server = create_engine(base, isolation_level="AUTOCOMMIT")
    name = "deployer_migration_check"
    with server.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
        conn.execute(text(f"CREATE DATABASE {name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    url = make_url(base).set(database=name).render_as_string(hide_password=False)
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    try:
        command.upgrade(cfg, "head")
        yield url
    finally:
        with server.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
        server.dispose()


def test_migrations_match_the_models(head_db_url):
    """`create_all` builds the test schema, so a model change without a migration would pass every
    other test and break upgraded installs. Upgrade a scratch database to head and diff it."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from app.db import Base

    engine = create_engine(head_db_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], f"models and migrations differ - add a migration: {diff}"
