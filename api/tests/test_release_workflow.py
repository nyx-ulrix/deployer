"""A-149: the release workflow is read-only by default; only the jobs that publish get write scopes."""

import re
from pathlib import Path

RELEASE = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"


def _permissions(text: str, indent: str) -> list[dict[str, str]]:
    """Every `permissions:` block at this indent, as {scope: level}."""
    blocks = []
    for m in re.finditer(rf"^{indent}permissions:\n((?:{indent}  \S.*\n)+)", text, re.M):
        blocks.append(dict(line.strip().split(": ", 1) for line in m.group(1).splitlines()))
    return blocks


def test_release_workflow_permissions_are_per_job():
    text = RELEASE.read_text(encoding="utf-8")
    assert _permissions(text, "") == [{"contents": "read"}]
    jobs = _permissions(text, "    ")
    assert {"contents": "read", "packages": "write"} in jobs  # images
    assert {"contents": "write"} in jobs  # bundle (GitHub release)
    # setup-exe holds the signing PFX: it must not get any write scope.
    setup_exe = text.split("  setup-exe:", 1)[1].split("\n  bundle:", 1)[0]
    assert "permissions:" not in setup_exe
