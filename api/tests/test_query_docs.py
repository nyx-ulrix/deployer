"""The query docs describe the shipped Terminal/Notebook modes, not superseded plans or to-do lists (A-186)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_query_docs_describe_modes_without_plans():
    editor = _read("docs/QUERY_EDITOR.md")
    assert "### Terminal" in editor and "### Notebook" in editor
    for stale in ("Revised direction", "Build order", "Editor layout (Supabase-style)"):
        assert stale not in editor
    assert "## Docs & repo" not in _read("docs/QUERY_CONSOLE.md")
    assert "(later)" not in _read("docs/ARCHITECTURE.md")
    assert "skill gains" not in _read("docs/DEPLOYMENTS.md")


def test_dashboard_points_at_existing_sections():
    for path in (ROOT / "dashboard/src/features/query").glob("*.ts*"):
        assert "Revised direction" not in path.read_text(encoding="utf-8"), path.name
