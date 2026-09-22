"""Query log (docs/QUERY_EDITOR.md): every console run is logged; list/get/delete permissions; pruning."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.errors import ApiError
from app.models import AuditLog, QueryRun, utcnow
from app.services import connections, query_log, source_ops
from tests.test_query_console import add_source, project_setup, sqlite_engine  # noqa: F401 (fixtures)


@pytest.fixture
def console(client, db, project_setup, sqlite_engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(connections, "get_sql_engine", lambda ds: sqlite_engine)
    ds = add_source(db, project_setup["project"])
    return {**project_setup, "ds": ds, "url": f"{project_setup['base']}/{ds.id}/query"}


def runs(db) -> list[QueryRun]:
    db.expire_all()
    return list(db.scalars(select(QueryRun).order_by(QueryRun.created_at, QueryRun.id)))


def test_runs_are_logged_with_outcome(client, db, console, monkeypatch):
    url, log_url = console["url"], f"/v1/projects/{console['project'].id}/query-log"
    ok = client.post(
        url,
        json={"query": "INSERT INTO items (name) VALUES ('x'); SELECT id FROM items", "layout": "editor"},
        headers=console["dev"],
    )
    assert ok.status_code == 200 and isinstance(ok.json()["run_id"], str)
    failed = client.post(url, json={"query": "SELECT 1; SELEC oops", "layout": "terminal"}, headers=console["dev"])
    assert failed.status_code == 200
    refused = client.post(url, json={"query": "DELETE FROM items"}, headers=console["viewer"])
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "read_only_role"

    def boom(code, status):
        def fake(*a, **k):
            raise ApiError(status, code, f"failed with {code}")

        return fake

    monkeypatch.setattr(source_ops, "run_query", boom("query_timeout", 504))
    assert client.post(url, json={"query": "SELECT sleep(9)"}, headers=console["dev"]).status_code == 504
    monkeypatch.setattr(source_ops, "run_query", boom("database_unavailable", 503))
    assert client.post(url, json={"query": "SELECT 2"}, headers=console["dev"]).status_code == 503

    rows = runs(db)
    assert [r.status for r in rows] == ["ok", "error", "refused", "timeout", "error"]
    assert [r.layout for r in rows] == ["editor", "terminal", "api", "api", "api"]
    assert [r.read_only for r in rows] == [False, False, True, False, False]
    first, second, third, fourth, fifth = rows
    assert first.id == ok.json()["run_id"] and first.statements == 2 and first.rows == 8 and first.affected_rows == 1
    assert first.query_text.startswith("INSERT INTO items") and first.error_message is None
    assert second.statements == 2 and second.rows == 1 and second.affected_rows is None
    assert "syntax" in second.error_message.lower()
    assert third.query_text == "DELETE FROM items" and third.statements == 0 and "read-only" in third.error_message
    assert (
        fourth.error_message == "failed with query_timeout"
        and fifth.error_message == "failed with database_unavailable"
    )
    assert all(r.user_email and r.source_name == console["ds"].name and r.kind == "sql" for r in rows)
    assert all(r.project_id == console["project"].id and isinstance(r.duration_ms, int) for r in rows)
    # Audit rows still carry counts only.
    audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "query.run")))
    assert len(audits) == 5 and not any("items" in str(a.details) for a in audits)

    resp = client.get(log_url, headers=console["viewer"])
    assert resp.status_code == 200 and [r["status"] for r in resp.json()["runs"]] == ["refused"]


def test_list_filters_and_permissions(client, db, console):
    url, log_url = console["url"], f"/v1/projects/{console['project'].id}/query-log"
    other = add_source(db, console["project"], name="second")
    for i in range(3):
        assert client.post(url, json={"query": f"SELECT {i}"}, headers=console["dev"]).status_code == 200
    assert client.post(url, json={"query": "SELECT 'v'"}, headers=console["viewer"]).status_code == 200
    long_text = "SELECT '" + "x" * 3000 + "'"
    assert client.post(url, json={"query": long_text}, headers=console["owner"]).status_code == 200
    # Same sqlite engine behind every source in this test; only the log's source id differs.
    assert (
        client.post(
            f"{console['base']}/{other.id}/query", json={"query": "SELECT 9"}, headers=console["dev"]
        ).status_code
        == 200
    )

    mine = client.get(log_url, headers=console["dev"]).json()
    assert [r["query_text"] for r in mine["runs"]] == ["SELECT 9", "SELECT 2", "SELECT 1", "SELECT 0"]
    assert mine["has_more"] is False and all("query_truncated" not in r for r in mine["runs"])
    assert client.get(log_url, params={"user": "all"}, headers=console["dev"]).status_code == 403
    assert client.get(log_url, params={"user": "all"}, headers=console["viewer"]).status_code == 403

    everyone = client.get(log_url, params={"user": "all"}, headers=console["owner"]).json()
    assert len(everyone["runs"]) == 6
    truncated = next(r for r in everyone["runs"] if r.get("query_truncated") is True)
    assert len(truncated["query_text"]) == 2000
    assert set(everyone["runs"][0]) >= {
        "id", "project_id", "data_source_id", "source_name", "kind", "engine", "user_id", "user_email",
        "query_text", "status", "statements", "rows", "affected_rows", "duration_ms", "error_message",
        "read_only", "layout", "created_at",
    }  # fmt: skip
    assert everyone["runs"][0]["created_at"].endswith("Z")

    by_source = client.get(log_url, params={"user": "all", "source_id": other.id}, headers=console["owner"]).json()
    assert [r["query_text"] for r in by_source["runs"]] == ["SELECT 9"]

    page = client.get(log_url, params={"user": "all", "limit": 2}, headers=console["owner"]).json()
    assert len(page["runs"]) == 2 and page["has_more"] is True
    older = client.get(
        log_url, params={"user": "all", "limit": 10, "before": page["runs"][-1]["created_at"]}, headers=console["owner"]
    ).json()
    assert len(older["runs"]) + len(page["runs"]) <= 6 and older["has_more"] is False
    assert not {r["id"] for r in older["runs"]} & {r["id"] for r in page["runs"]}
    assert client.get(log_url, params={"before": "yesterday"}, headers=console["owner"]).status_code == 422
    assert client.get(log_url, params={"limit": 0}, headers=console["owner"]).status_code == 422
    assert client.get(log_url, params={"limit": 201}, headers=console["owner"]).status_code == 422


def test_get_and_delete(client, db, console, make_user, make_project, auth_headers):
    url, log_url = console["url"], f"/v1/projects/{console['project'].id}/query-log"
    viewer_run = client.post(url, json={"query": "SELECT 'v'"}, headers=console["viewer"]).json()["run_id"]
    dev_run = client.post(url, json={"query": "SELECT 'd'"}, headers=console["dev"]).json()["run_id"]

    own = client.get(f"{log_url}/{viewer_run}", headers=console["viewer"])
    assert own.status_code == 200 and own.json()["query_text"] == "SELECT 'v'" and "query_truncated" not in own.json()
    assert client.get(f"{log_url}/{dev_run}", headers=console["viewer"]).status_code == 403
    assert client.get(f"{log_url}/{dev_run}", headers=console["owner"]).status_code == 200
    assert client.get(f"{log_url}/nope", headers=console["owner"]).status_code == 404
    stranger = make_user()
    other = make_project(stranger, "Other")
    assert client.get(f"/v1/projects/{other.id}/query-log/{dev_run}", headers=auth_headers(stranger)).status_code == 404

    cutoff = (utcnow() + timedelta(minutes=1)).isoformat() + "Z"
    assert client.delete(log_url, params={"before": cutoff}, headers=console["dev"]).status_code == 403
    assert client.delete(log_url, headers=console["owner"]).status_code == 422
    resp = client.delete(log_url, params={"before": cutoff}, headers=console["owner"])
    assert resp.status_code == 200 and resp.json() == {"deleted": 2}
    assert runs(db) == []


def test_prune(db, console, make_project, make_user, monkeypatch):
    monkeypatch.setattr(query_log, "MAX_RUNS_PER_PROJECT", 3)
    project, ds, user = console["project"], console["ds"], make_user()
    second = make_project(user, "Second")
    now = utcnow()

    def add(pid, age_days):
        run = query_log.record_run(
            db, project_id=pid, ds=ds, user=user, query_text="SELECT 1", read_only=False, layout="api", duration_ms=1
        )
        run.created_at = now - timedelta(days=age_days)

    for age in (0, 1, 2, 3, 4, 91):  # 6 rows: one expired, two beyond the cap
        add(project.id, age)
    for age in (0, 1):
        add(second.id, age)
    db.commit()
    assert query_log.prune(db, now) == 3
    db.commit()
    kept = list(db.scalars(select(QueryRun).where(QueryRun.project_id == project.id).order_by(QueryRun.created_at)))
    assert [(now - r.created_at).days for r in kept] == [2, 1, 0]
    assert db.scalar(select(func.count()).select_from(QueryRun).where(QueryRun.project_id == second.id)) == 2
    assert query_log.prune(db, now) == 0


def test_worker_prunes_once_a_day(monkeypatch):
    from app import worker

    calls = []
    monkeypatch.setattr(worker.jobs, "recover_stale", lambda: 0)
    monkeypatch.setattr(worker.jobs, "redispatch_queued", lambda: 0)
    monkeypatch.setattr("app.services.backups.scheduler_tick", lambda factory: [])
    monkeypatch.setattr(query_log, "prune", lambda session: calls.append(session) or 0)
    monkeypatch.setattr(worker, "_last_query_log_prune", float("-inf"))
    worker.scheduler_tick()
    worker.scheduler_tick()
    assert len(calls) == 1
