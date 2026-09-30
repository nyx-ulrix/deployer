"""Migration checks: every migration table gets the utf8mb4 options, and head matches the models.

The test database is SQLite, which ignores collations and foreign-key forms, so a `create_table`
without them only fails on a real MariaDB (errno 150 "Foreign key constraint is incorrectly
formed") - exactly how 0008 broke an installed instance.
"""

import re
from pathlib import Path

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


def test_migrations_match_the_models(migration_db):
    """`create_all` builds the test schema, so a model change without a migration would pass every
    other test and break upgraded installs. Upgrade a scratch database to head and diff it."""
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from app.db import Base

    cfg, db_file = migration_db
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], f"models and migrations differ - add a migration: {diff}"
