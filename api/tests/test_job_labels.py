"""A-087: every job type the API creates has a label in the dashboard's Activity drawer."""

import re
from pathlib import Path

import app.main  # noqa: F401  (registers every job handler)
from app.services import device_moves, jobs

JOBS_TS = Path(__file__).resolve().parents[2] / "dashboard" / "src" / "features" / "jobs" / "jobs.ts"


def test_dashboard_labels_every_job_type():
    labelled = set(re.findall(r'^\s*"([a-z_]+\.[a-z_]+)":', JOBS_TS.read_text(encoding="utf-8"), re.M))
    created = {t for t in jobs._registry if not t.startswith("test.")}  # other tests register test.* handlers
    created.add(device_moves.MOVE_JOB)  # device.move rows are created directly, not enqueued
    assert created <= labelled, f"no Activity label for {sorted(created - labelled)}"
