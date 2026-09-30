"""The deploy-website skill must not contradict itself about where apps can run (A-183)."""

from pathlib import Path

SKILL = (Path(__file__).resolve().parents[2] / "skills/deploy-website/SKILL.md").read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    return SKILL[SKILL.index(start) : SKILL.index(end)]


def test_external_platform_table_lists_only_external_platforms():
    rows = [line for line in _section("## Step 2b", "After deploying:").splitlines() if line.startswith("| ")]
    platforms = [row.split("|")[1].strip() for row in rows[1:]]  # skip the header row
    assert platforms and not [p for p in platforms if "Deployer" in p or "co-host" in p.lower()]


def test_co_host_apps_are_not_listed_as_not_built():
    status = _section("## Feature status", "## Step 2a")
    for row in status.splitlines():
        if "Not built" in row:
            assert "main Deployer PC only" not in row and "Apps running on host devices |" not in row
    assert "### Co-host PCs" in _section("## Step 2a", "## Step 2b")
