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


def test_images_wait_for_ci_and_prereleases_skip_latest():
    """A-190: a tag that fails CI publishes nothing, and an RC never becomes `latest`."""
    text = RELEASE.read_text(encoding="utf-8")
    ci = (RELEASE.parent / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"^  workflow_call:", ci, re.M)
    tests = text.split("\n  tests:", 1)[1].split("\n  images:", 1)[0]
    assert "uses: ./.github/workflows/ci.yml" in tests
    images = text.split("\n  images:", 1)[1].split("\n  setup-exe:", 1)[0]
    assert re.search(r"^    needs: \[?tests\]?$", images, re.M)
    assert "flavor: latest=false" in images
    latest = [line.strip() for line in images.splitlines() if "value=latest" in line]
    assert latest == ["type=raw,value=latest,enable=${{ !contains(github.ref_name, '-') }}"]
    assert "prerelease: ${{ contains(github.ref_name, '-') }}" in text
