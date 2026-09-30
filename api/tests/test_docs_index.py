"""The README holds the one full docs index; ARCHITECTURE and CONTRIBUTING link to it (A-187)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_readme_indexes_every_doc():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    index = readme[readme.index("## Documentation") : readme.index("## Requirements")]
    missing = [p.name for p in (ROOT / "docs").glob("*.md") if f"(docs/{p.name})" not in index]
    assert not missing
    assert "../README.md#documentation" in (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "README.md#documentation" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
