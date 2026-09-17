import re

from app.models import AuditLog, DataSource, Project, ProjectMember
from app.services.slugs import SLUG_RE, slugify, unique_slug


def test_slugify():
    assert slugify("My Cool Project!") == "my-cool-project"
    assert slugify("Café  Übersicht") == "cafe-ubersicht"
    assert slugify("42 things") == "project-42-things"
    assert slugify("---") == "project"
    assert slugify("ab") == "ab-project"
    long = slugify("x" * 200)
    assert len(long) <= 56
    for name in ["My Cool Project!", "42", "日本語", "a", "x" * 200, "--a--b--"]:
        assert SLUG_RE.match(slugify(name)), name


def test_unique_slug_suffix(db, owner, make_project):
    make_project(owner, "Shop")
    slug = unique_slug(db, "Shop")
    assert re.fullmatch(r"shop-[a-z0-9]{6}", slug)


def test_create_and_list(client, owner, owner_headers, db):
    resp = client.post("/v1/projects", json={"name": "  My Shop ", "description": "Things"}, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    project = resp.json()
    assert project["slug"] == "my-shop"
    assert project["name"] == "My Shop"
    assert project["my_role"] == "owner"
    assert project["owner_id"] == owner.id
    assert project["data_source_counts"] == {"sql": 0, "nosql": 0}

    second = client.post("/v1/projects", json={"name": "My Shop"}, headers=owner_headers).json()
    assert second["slug"].startswith("my-shop-")

    listed = client.get("/v1/projects", headers=owner_headers).json()
    assert sorted(p["id"] for p in listed) == sorted([project["id"], second["id"]])
    assert db.query(ProjectMember).filter_by(project_id=project["id"], role="owner").count() == 1
    assert db.query(AuditLog).filter_by(action="project.create").count() == 2


def test_create_validation(client, owner_headers):
    assert client.post("/v1/projects", json={"name": "   "}, headers=owner_headers).status_code == 422
    assert client.post("/v1/projects", json={}, headers=owner_headers).status_code == 422
    assert client.post("/v1/projects", json={"name": "x"}).status_code == 401


def test_create_with_provisioning(client, owner_headers, fake_provisioning, db):
    resp = client.post(
        "/v1/projects", json={"name": "Data", "provision": {"sql": True, "nosql": True}}, headers=owner_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data_source_counts"] == {"sql": 1, "nosql": 1}
    assert [(k, n) for _, k, n in fake_provisioning.calls] == [("sql", "main-sql"), ("nosql", "main-nosql")]
    names = sorted(s.name for s in db.query(DataSource).filter_by(project_id=body["id"]))
    assert names == ["main-nosql", "main-sql"]


def test_create_provisioning_failure_rolls_back(client, owner_headers, fake_provisioning, db):
    fake_provisioning.fail_kind = "nosql"
    resp = client.post(
        "/v1/projects", json={"name": "Data", "provision": {"sql": True, "nosql": True}}, headers=owner_headers
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "provisioning_failed"
    assert db.query(Project).count() == 0
    assert db.query(DataSource).count() == 0
    assert [k for _, k, _ in fake_provisioning.dropped] == ["sql"]  # already-created database cleaned up


def test_get_requires_membership(client, owner, make_user, make_project, auth_headers, owner_headers):
    project = make_project(owner)
    outsider = make_user()
    viewer = make_user()
    assert client.get(f"/v1/projects/{project.id}", headers=auth_headers(outsider)).status_code == 404
    assert client.get("/v1/projects/nope", headers=owner_headers).status_code == 404
    project2 = make_project(owner, "Other", members={viewer: "viewer"})
    resp = client.get(f"/v1/projects/{project2.id}", headers=auth_headers(viewer))
    assert resp.status_code == 200
    assert resp.json()["my_role"] == "viewer"
    assert [p["id"] for p in client.get("/v1/projects", headers=auth_headers(viewer)).json()] == [project2.id]


def test_patch_requires_admin(client, owner, make_user, make_project, auth_headers):
    dev, admin = make_user(), make_user()
    project = make_project(owner, members={dev: "developer", admin: "admin"})
    url = f"/v1/projects/{project.id}"
    resp = client.patch(url, json={"name": "Renamed"}, headers=auth_headers(dev))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"
    resp = client.patch(url, json={"name": "Renamed", "description": "New"}, headers=auth_headers(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed" and body["description"] == "New"
    assert body["slug"] == project.slug and body["my_role"] == "admin"
    resp = client.patch(url, json={"description": None}, headers=auth_headers(admin))
    assert resp.json()["description"] is None and resp.json()["name"] == "Renamed"


def test_delete(
    client, owner, owner_headers, make_user, make_project, auth_headers, fake_provisioning, db, monkeypatch
):
    admin = make_user()
    created = client.post(
        "/v1/projects", json={"name": "Doomed", "provision": {"sql": True}}, headers=owner_headers
    ).json()
    pid = created["id"]
    db.add(ProjectMember(project_id=pid, user_id=admin.id, role="admin"))
    db.commit()
    client.post(f"/v1/projects/{pid}/api-keys", json={"name": "k", "role": "anon"}, headers=owner_headers)
    client.post(f"/v1/projects/{pid}/invites", json={"role": "viewer"}, headers=owner_headers)

    assert client.delete(f"/v1/projects/{pid}?confirm=doomed", headers=auth_headers(admin)).status_code == 403
    resp = client.delete(f"/v1/projects/{pid}", headers=owner_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "confirmation_required"
    assert client.delete(f"/v1/projects/{pid}?confirm=wrong", headers=owner_headers).status_code == 400

    resp = client.delete(f"/v1/projects/{pid}?confirm=doomed", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}
    # docs/BACKUPS.md: the final snapshot and the drop run as a job that outlives the project rows.
    from app.models import Job
    from app.services import executors, jobs

    job = db.query(Job).filter_by(type="source.finalize_delete").one()
    assert job.project_id is None and job.params["detached"]["name"] == "main-sql"
    assert fake_provisioning.dropped == []

    class FakeExecutor:
        def snapshot(self, **kwargs):
            return {"size_bytes": 1, "sha256": "0" * 64, "consistent_point": {}, "row_counts": {}}

    monkeypatch.setattr(executors, "executor_for", lambda _host: FakeExecutor())
    assert jobs.run_queued() == [(job.id, "succeeded")]
    assert fake_provisioning.dropped == [(pid, "sql", "main-sql")]
    db.expire_all()
    assert db.get(Project, pid) is None
    assert db.query(DataSource).count() == 0
    assert db.query(ProjectMember).count() == 0
    assert db.query(AuditLog).filter_by(action="project.delete", project_id=pid).count() == 1
    assert client.get(f"/v1/projects/{pid}", headers=owner_headers).status_code == 404
