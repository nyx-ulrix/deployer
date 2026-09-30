"""A-188: release images report their git tag as the version, not the hardcoded base version."""

import importlib
from pathlib import Path

import app

ROOT = Path(__file__).resolve().parents[2]


def _reload_version(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("DEPLOYER_BUILD_VERSION", raising=False)
    else:
        monkeypatch.setenv("DEPLOYER_BUILD_VERSION", value)
    return importlib.reload(app).__version__


def test_version_comes_from_the_release_tag(monkeypatch):
    try:
        assert _reload_version(monkeypatch, "v1.4.2") == "1.4.2"
        assert _reload_version(monkeypatch, "") == "0.1.0"
        assert _reload_version(monkeypatch, None) == "0.1.0"
    finally:
        monkeypatch.delenv("DEPLOYER_BUILD_VERSION", raising=False)
        importlib.reload(app)


def test_release_build_passes_the_tag_to_the_api_image():
    dockerfile = (ROOT / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert "ENV DEPLOYER_BUILD_VERSION=$DEPLOYER_REF" in dockerfile
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "DEPLOYER_REF=${{ github.ref_name }}" in release
