"""A-194: CI enforces the ruff config in pyproject.toml (lint and format) before the API tests."""

from pathlib import Path

CI = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def test_api_job_runs_ruff_lint_and_format_check():
    api_job = CI.read_text(encoding="utf-8").split("\n  api:", 1)[1].split("\n  images:", 1)[0]
    assert "ruff check ." in api_job
    assert "ruff format --check ." in api_job
    assert api_job.index("ruff check") < api_job.index("run: pytest")
