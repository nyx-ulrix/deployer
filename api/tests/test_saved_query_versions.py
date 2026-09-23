"""Saved-query versions (docs/QUERY_EDITOR.md "Phase 2 — versions"): strict version control, no silent overwrites."""

import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.db import Base, get_engine
from app.models import ProjectMember, SavedQuery, SavedQueryVersion
from app.services import transfer
from tests.test_query_console import project_setup  # noqa: F401 (fixture)

PASS = "correct horse battery staple"
API_DIR = Path(__file__).resolve().parents[1]


def _create(client, project_setup, text="SELECT 1", **extra):  # noqa: F811
    url = f"/v1/projects/{project_setup['project'].id}/saved-queries"
    resp = client.post(
        url, json={"name": "n", "query_text": text, "kind": "sql", **extra}, headers=project_setup["dev"]
    )
    assert resp.status_code == 201, resp.text
    return url, resp.json()


def test_create_patch_and_conflicts(client, db, project_setup):  # noqa: F811
    url, sq = _create(client, project_setup, message="first")
    assert sq["version"] == 1 and sq["updated_by_email"] == sq["owner_email"]
    versions = client.get(f"{url}/{sq['id']}/versions", headers=project_setup["viewer"]).json()["versions"]
    assert [(v["version"], v["message"], v["chars"]) for v in versions] == [(1, "first", 8)]

    # missing version -> 422; text patch bumps to v2 with author/message on the row.
    assert client.patch(f"{url}/{sq['id']}", json={"query_text": "x"}, headers=project_setup["dev"]).status_code == 422
    patched = client.patch(
        f"{url}/{sq['id']}",
        json={"query_text": "SELECT 2", "message": "bump", "version": 1},
        headers=project_setup["owner"],
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["version"] == 2 and patched.json()["query_text"] == "SELECT 2"
    assert patched.json()["updated_by_email"] != sq["owner_email"]
    v2 = client.get(f"{url}/{sq['id']}/versions/2", headers=project_setup["viewer"]).json()
    assert v2["query_text"] == "SELECT 2" and v2["message"] == "bump" and v2["chars"] == 8
    assert v2["author_email"] == patched.json()["updated_by_email"] and v2["author_id"] != sq["owner_id"]
    assert client.get(f"{url}/{sq['id']}/versions/9", headers=project_setup["viewer"]).status_code == 404

    # metadata-only patch: needs the version, does not bump it, no new row.
    meta = client.patch(f"{url}/{sq['id']}", json={"name": "renamed", "version": 2}, headers=project_setup["dev"])
    assert meta.status_code == 200 and meta.json()["version"] == 2 and meta.json()["name"] == "renamed"
    listed = client.get(url, headers=project_setup["viewer"]).json()
    assert listed[0]["version"] == 2 and listed[0]["updated_by_email"] == v2["author_email"]

    # stale version -> 409 carrying the current row (full text) so the client can diff/merge.
    stale = client.patch(
        f"{url}/{sq['id']}", json={"query_text": "SELECT 3", "version": 1}, headers=project_setup["dev"]
    )
    assert stale.status_code == 409, stale.text
    err = stale.json()["error"]
    assert err["code"] == "version_conflict" and err["message"] == "Someone saved a newer version"
    assert err["details"]["current"]["version"] == 2 and err["details"]["current"]["query_text"] == "SELECT 2"
    assert (
        client.patch(f"{url}/{sq['id']}", json={"name": "z", "version": 1}, headers=project_setup["dev"]).status_code
        == 409
    )

    versions = client.get(f"{url}/{sq['id']}/versions", headers=project_setup["viewer"]).json()["versions"]
    assert [v["version"] for v in versions] == [2, 1] and "query_text" not in versions[0]
    assert set(versions[0]) == {"id", "version", "author_id", "author_email", "message", "created_at", "chars"}


def test_two_developers_editing(client, db, project_setup, make_user, auth_headers):  # noqa: F811
    url, sq = _create(client, project_setup)
    other = make_user()
    db.add(ProjectMember(project_id=project_setup["project"].id, user_id=other.id, role="developer"))
    db.commit()
    other_h = auth_headers(other)

    first = client.patch(f"{url}/{sq['id']}", json={"query_text": "A", "version": 1}, headers=project_setup["dev"])
    assert first.status_code == 200 and first.json()["version"] == 2
    second = client.patch(f"{url}/{sq['id']}", json={"query_text": "B", "version": 1}, headers=other_h)
    assert second.status_code == 409 and second.json()["error"]["details"]["current"]["query_text"] == "A"
    current = second.json()["error"]["details"]["current"]["version"]
    merged = client.patch(f"{url}/{sq['id']}", json={"query_text": "AB", "version": current}, headers=other_h)
    assert merged.status_code == 200 and merged.json()["version"] == 3
    assert merged.json()["updated_by_email"] == other.email


def test_restore_and_permissions(client, db, project_setup):  # noqa: F811
    url, sq = _create(client, project_setup, text="v1 text")
    assert (
        client.patch(
            f"{url}/{sq['id']}", json={"query_text": "v2 text", "version": 1}, headers=project_setup["dev"]
        ).status_code
        == 200
    )

    stale = client.post(
        f"{url}/{sq['id']}/restore", json={"version": 1, "current_version": 1}, headers=project_setup["dev"]
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "version_conflict"
    assert (
        client.post(
            f"{url}/{sq['id']}/restore", json={"version": 7, "current_version": 2}, headers=project_setup["dev"]
        ).status_code
        == 404
    )
    restored = client.post(
        f"{url}/{sq['id']}/restore", json={"version": 1, "current_version": 2}, headers=project_setup["dev"]
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["version"] == 3 and restored.json()["query_text"] == "v1 text"
    versions = client.get(f"{url}/{sq['id']}/versions", headers=project_setup["dev"]).json()["versions"]
    assert [v["version"] for v in versions] == [3, 2, 1] and versions[0]["message"] == "Restored version 1"
    assert client.get(f"{url}/{sq['id']}/versions/1", headers=project_setup["dev"]).json()["query_text"] == "v1 text"

    # viewers read history but never write.
    viewer = project_setup["viewer"]
    assert client.get(f"{url}/{sq['id']}/versions", headers=viewer).status_code == 200
    assert client.patch(f"{url}/{sq['id']}", json={"name": "x", "version": 3}, headers=viewer).status_code == 403
    assert (
        client.post(f"{url}/{sq['id']}/restore", json={"version": 1, "current_version": 3}, headers=viewer).status_code
        == 403
    )

    # delete cascades the history.
    assert client.delete(f"{url}/{sq['id']}", headers=project_setup["dev"]).status_code == 200
    assert db.scalar(select(SavedQueryVersion).where(SavedQueryVersion.saved_query_id == sq["id"])) is None
    assert client.get(f"{url}/{sq['id']}/versions", headers=viewer).status_code == 404


def test_export_and_import_carry_versions(client, db, project_setup, make_user, auth_headers):  # noqa: F811
    project = project_setup["project"]
    url, sq = _create(client, project_setup, text="one")
    client.patch(f"{url}/{sq['id']}", json={"query_text": "two", "version": 1}, headers=project_setup["dev"])

    resp = client.post(
        "/v1/projects/export", json={"project_ids": [project.id], "passphrase": PASS}, headers=project_setup["owner"]
    )
    importer = make_user()
    ok = client.post(
        "/v1/projects/import",
        files={"file": ("x.json", resp.content)},
        data={"passphrase": PASS},
        headers=auth_headers(importer),
    )
    assert ok.status_code == 200, ok.text
    [new_project] = ok.json()["projects"]
    [copied] = client.get(f"/v1/projects/{new_project['id']}/saved-queries", headers=auth_headers(importer)).json()
    assert copied["version"] == 2 and copied["id"] != sq["id"]
    history = client.get(
        f"/v1/projects/{new_project['id']}/saved-queries/{copied['id']}/versions", headers=auth_headers(importer)
    ).json()["versions"]
    assert [v["version"] for v in history] == [2, 1] and copied["updated_by_email"] == history[0]["author_email"]

    path, _ = transfer.build_export_file(db, scope="instance", projects=[project], passphrase=PASS)
    try:
        payload = transfer.read_export_file(path, PASS, "instance")
    finally:
        os.unlink(path)
    assert [(v["saved_query_id"], v["version"]) for v in payload["saved_query_versions"]] == [
        (sq["id"], 1),
        (sq["id"], 2),
    ]
    # instance scope: restored as-is (same ids) into an empty instance.
    with get_engine().begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    transfer.import_instance(db, payload)
    db.expire_all()
    assert db.get(SavedQuery, sq["id"]).version == 2
    assert (
        db.scalar(
            select(SavedQueryVersion).where(
                SavedQueryVersion.saved_query_id == sq["id"], SavedQueryVersion.version == 1
            )
        ).query_text
        == "one"
    )


def test_migration_backfills_version_one(tmp_path):
    """Upgrade a pre-0004 database: every saved query gets a version-1 row authored by its owner."""
    db_file = tmp_path / "scratch.db"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file.as_posix()}")
    command.upgrade(cfg, "0003")

    conn = sqlite3.connect(db_file)
    conn.execute(
        "INSERT INTO users (id, email, is_instance_owner, is_active, created_at, updated_at) "
        "VALUES ('u1', 'owner@example.com', 1, 1, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO projects (id, slug, name, owner_id, created_at, updated_at) "
        "VALUES ('p1', 'p1', 'P', 'u1', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO saved_queries (id, project_id, owner_id, name, query_text, kind, created_at, updated_at) "
        "VALUES ('q1', 'p1', 'u1', 'Old', 'SELECT old', 'sql', '2026-01-01', '2026-01-02 03:04:05')"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "head")
    conn = sqlite3.connect(db_file)
    assert conn.execute("SELECT version FROM saved_queries").fetchall() == [(1,)]
    # 0006 (docs/DEPLOYMENTS.md): apps, deployments and domains.app_id.
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"apps", "deployments"} <= tables
    assert "app_id" in [row[1] for row in conn.execute("PRAGMA table_info(domains)")]
    # 0007 (docs/DEPLOYMENTS.md "Database access"): off by default.
    assert "database_access" in [row[1] for row in conn.execute("PRAGMA table_info(apps)")]
    rows = conn.execute(
        "SELECT version, query_text, author_id, author_email, message, created_at FROM saved_query_versions"
    ).fetchall()
    assert rows == [
        (1, "SELECT old", "u1", "owner@example.com", "Imported from before version history", "2026-01-02 03:04:05")
    ]
    conn.close()
