"""Every migration table gets the utf8mb4 options.

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
