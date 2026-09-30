"""The README holds the only roadmap; ARCHITECTURE links to it instead of keeping a copy that drifts (A-185)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_single_roadmap_with_one_current_phase():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = readme[readme.index("## Roadmap") : readme.index("## Security")]
    assert roadmap.count("*(current)*") == 1
    architecture = (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "../README.md#roadmap" in architecture
    assert "**Done" not in architecture and "current**" not in architecture
