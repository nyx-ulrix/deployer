"""Saved queries (docs/QUERY_EDITOR.md): CRUD, validation, permissions and export/import."""

import os
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import (
    ApiKey,
    DataSource,
    InstanceSetting,
    Project,
    ProjectInvite,
    ProjectMember,
    SavedQuery,
    SchemaLink,
    User,
    UserIdentity,
    utcnow,
)
from app.services import transfer
from tests.test_query_console import add_source, project_setup  # noqa: F401 (fixtures)

PASS = "correct horse battery staple"


def test_crud_and_validation(client, db, project_setup):  # noqa: F811
    url = f"/v1/projects/{project_setup['project'].id}/saved-queries"
    ds = add_source(db, project_setup["project"])
    gone = add_source(db, project_setup["project"], name="gone", deleted_at=utcnow())
    doc = '{"cells":[{"id":"c1","text":"SELECT 1"}]}'

    created = client.post(
        url,
        json={"name": "  Top items ", "folder": " reports ", "query_text": doc, "data_source_id": ds.id, "kind": "sql"},
        headers=project_setup["dev"],
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Top items" and body["folder"] == "reports" and body["query_text"] == doc
    assert body["data_source_id"] == ds.id and body["kind"] == "sql" and body["owner_email"].endswith("@example.com")
    assert set(body) == {
        "id", "project_id", "data_source_id", "owner_id", "owner_email", "name", "folder", "query_text", "kind",
        "created_at", "updated_at",
    }  # fmt: skip
    assert body["created_at"].endswith("Z") and body["updated_at"].endswith("Z")

    for bad in (
        {"name": "", "query_text": "x", "kind": "sql"},
        {"name": "n" * 121, "query_text": "x", "kind": "sql"},
        {"name": "n", "folder": "a/b", "query_text": "x", "kind": "sql"},
        {"name": "n", "query_text": "x" * 200_001, "kind": "sql"},
        {"name": "n", "query_text": "x", "kind": "graphql"},
        {"name": "n", "query_text": "x", "kind": "sql", "data_source_id": "nope"},
        {"name": "n", "query_text": "x", "kind": "sql", "data_source_id": gone.id},
    ):
        resp = client.post(url, json=bad, headers=project_setup["dev"])
        assert resp.status_code == 422, (bad.get("data_source_id") or bad.get("folder") or bad["name"][:5], resp.text)

    loose = client.post(
        url, json={"name": "b", "folder": "", "query_text": "", "kind": "any"}, headers=project_setup["owner"]
    )
    assert loose.status_code == 201 and loose.json()["folder"] is None and loose.json()["data_source_id"] is None
    unfoldered = client.post(url, json={"name": "a", "query_text": "", "kind": "nosql"}, headers=project_setup["owner"])
    assert unfoldered.status_code == 201

    listed = client.get(url, headers=project_setup["viewer"]).json()
    assert [(q["folder"], q["name"]) for q in listed] == [(None, "a"), (None, "b"), ("reports", "Top items")]

    db.expire_all()
    before = db.get(SavedQuery, body["id"]).updated_at
    patched = client.patch(
        f"{url}/{body['id']}",
        json={"name": "Top 10", "folder": None, "data_source_id": None, "updated_at": "ignored"},
        headers=project_setup["dev"],
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Top 10" and patched.json()["folder"] is None
    assert patched.json()["data_source_id"] is None and patched.json()["query_text"] == doc
    db.expire_all()
    assert db.get(SavedQuery, body["id"]).updated_at >= before
    assert client.patch(f"{url}/{body['id']}", json={"folder": "x/y"}, headers=project_setup["dev"]).status_code == 422
    assert (
        client.patch(f"{url}/{body['id']}", json={"data_source_id": gone.id}, headers=project_setup["dev"]).status_code
        == 422
    )
    assert client.patch(f"{url}/nope", json={"name": "z"}, headers=project_setup["dev"]).status_code == 404

    # Deleting the source clears the reference (ON DELETE SET NULL) instead of dropping the snippet.
    relinked = client.patch(f"{url}/{body['id']}", json={"data_source_id": ds.id}, headers=project_setup["dev"])
    assert relinked.status_code == 200
    db.delete(db.get(DataSource, ds.id))
    db.commit()
    db.expire_all()
    assert db.get(SavedQuery, body["id"]).data_source_id is None

    deleted = client.delete(f"{url}/{body['id']}", headers=project_setup["dev"])
    assert deleted.status_code == 200 and deleted.json() == {"ok": True}
    assert client.delete(f"{url}/{body['id']}", headers=project_setup["dev"]).status_code == 404
    assert len(client.get(url, headers=project_setup["viewer"]).json()) == 2


def test_permissions(client, db, project_setup, make_user, make_project, auth_headers):  # noqa: F811
    project = project_setup["project"]
    url = f"/v1/projects/{project.id}/saved-queries"
    snippet = {"name": "n", "query_text": "SELECT 1", "kind": "sql"}
    assert client.post(url, json=snippet, headers=project_setup["viewer"]).status_code == 403
    mine = client.post(url, json=snippet, headers=project_setup["dev"]).json()

    other_dev = make_user()
    db.add(ProjectMember(project_id=project.id, user_id=other_dev.id, role="developer"))
    db.commit()
    other_h = auth_headers(other_dev)
    assert client.patch(f"{url}/{mine['id']}", json={"name": "taken"}, headers=other_h).status_code == 403
    assert client.delete(f"{url}/{mine['id']}", headers=other_h).status_code == 403
    assert client.get(url, headers=other_h).status_code == 200  # reading is fine
    assert (
        client.patch(f"{url}/{mine['id']}", json={"name": "admin edit"}, headers=project_setup["owner"]).status_code
        == 200
    )

    stranger = make_user()
    other = make_project(stranger, "Other")
    foreign = f"/v1/projects/{other.id}/saved-queries/{mine['id']}"
    assert client.patch(foreign, json={"name": "x"}, headers=auth_headers(stranger)).status_code == 404
    assert client.delete(foreign, headers=auth_headers(stranger)).status_code == 404
    assert client.get(url).status_code == 401

    assert client.delete(f"{url}/{mine['id']}", headers=project_setup["owner"]).status_code == 200


def test_export_and_imports_carry_saved_queries(client, db, project_setup, make_user, auth_headers):  # noqa: F811
    project = project_setup["project"]
    ds = add_source(db, project)
    dev = db.scalar(
        select(User).join(ProjectMember, ProjectMember.user_id == User.id).where(ProjectMember.role == "developer")
    )
    snippet = SavedQuery(
        project_id=project.id,
        owner_id=dev.id,
        data_source_id=ds.id,
        name="Daily",
        folder="reports",
        query_text='{"cells":[]}',
        kind="sql",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    db.add(snippet)
    db.commit()
    ids = {"snippet": snippet.id, "project": project.id, "dev": dev.id}  # the rows are wiped below

    # projects scope, through the API: fresh ids, importer becomes the owner, source remapped.
    resp = client.post(
        "/v1/projects/export", json={"project_ids": [project.id], "passphrase": PASS}, headers=project_setup["owner"]
    )
    assert resp.status_code == 200, resp.text
    importer = make_user()
    ok = client.post(
        "/v1/projects/import",
        files={"file": ("x.json", resp.content)},
        data={"passphrase": PASS},
        headers=auth_headers(importer),
    )
    assert ok.status_code == 200, ok.text
    [new_project] = ok.json()["projects"]
    copied = client.get(f"/v1/projects/{new_project['id']}/saved-queries", headers=auth_headers(importer)).json()
    assert len(copied) == 1 and copied[0]["id"] != snippet.id and copied[0]["owner_id"] == importer.id
    assert (
        copied[0]["name"] == "Daily" and copied[0]["folder"] == "reports" and copied[0]["query_text"] == '{"cells":[]}'
    )
    new_source = db.scalar(select(DataSource.id).where(DataSource.project_id == new_project["id"]))
    assert copied[0]["data_source_id"] == new_source and copied[0]["created_at"] == "2026-01-02T03:04:05Z"

    # instance scope: restored as-is; a snippet whose source is unknown keeps everything but the link.
    path, _ = transfer.build_export_file(db, scope="instance", projects=[project], passphrase=PASS)
    try:
        payload = transfer.read_export_file(path, PASS, "instance")
    finally:
        os.unlink(path)
    assert [q["id"] for q in payload["saved_queries"]] == [ids["snippet"]]
    payload["data_sources"] = []  # pretend the source did not make it
    for model in (
        SavedQuery,
        SchemaLink,
        ApiKey,
        ProjectInvite,
        ProjectMember,
        DataSource,
        Project,
        UserIdentity,
        InstanceSetting,
    ):
        db.query(model).delete()
    db.query(User).delete()
    db.commit()
    transfer.import_instance(db, payload)
    db.expire_all()
    restored = db.get(SavedQuery, ids["snippet"])
    assert restored.owner_id == ids["dev"] and restored.project_id == ids["project"] and restored.data_source_id is None
    assert restored.folder == "reports" and restored.created_at == datetime(2026, 1, 2, 3, 4, 5)
    assert restored.updated_at >= utcnow() - timedelta(minutes=5)
