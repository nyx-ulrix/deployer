"""Firestore databases, managed exports and scheduled backups (docs/CLOUD.md "Firestore backups"): creating a named
database, exports to a Cloud Storage bucket (named or made on request) and imports into a new database, backup
schedules, backups and restores into a new database, the billing confirmations, the MCP tools and the Google roles.
Firestore Admin is an in-memory fake behind `GcpClient.firestore` that only accepts the documented REST paths (and
the real client's path guard); the real client's URLs run against httpx.MockTransport. Nothing here reaches Google."""

import json
import re
import secrets
from urllib.parse import parse_qs, unquote

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.errors import CloudError
from app.models import AuditLog, DataSource, Job, ProjectMember
from app.services import cloud, cloud_db, cloud_gcp, jobs
from tests.test_cloud import connection
from tests.test_firestore import PROJECT, FakeFirestore, _fail

# Firestore Admin REST v1 (https://firestore.googleapis.com/v1/projects/<project>/...): the calls this feature makes.
ADMIN_PATHS = [
    ("POST", r"databases"),  # projects.databases.create (?databaseId=)
    ("POST", r"databases:restore"),  # projects.databases.restore
    ("POST", r"databases/[^/:]+:exportDocuments"),  # projects.databases.exportDocuments
    ("POST", r"databases/[^/:]+:importDocuments"),  # projects.databases.importDocuments
    ("GET", r"databases/[^/:]+/operations"),  # projects.databases.operations.list
    ("GET", r"databases/[^/:]+/operations/[^/:]+"),  # projects.databases.operations.get
    ("GET", r"databases/[^/:]+/backupSchedules"),  # projects.databases.backupSchedules.list
    ("POST", r"databases/[^/:]+/backupSchedules"),  # projects.databases.backupSchedules.create
    ("DELETE", r"databases/[^/:]+/backupSchedules/[^/:]+"),  # projects.databases.backupSchedules.delete
    ("GET", r"locations/[^/:]+/backups"),  # projects.locations.backups.list
]
DEFAULT = f"projects/{PROJECT}/databases/(default)"


class FakeAdmin(FakeFirestore):
    """FakeFirestore plus the admin surface: databases, long-running operations (done on their second read),
    backup schedules and backups."""

    def __init__(self, **returns):
        super().__init__(**returns)
        self.ops: dict[str, dict] = {}
        self.schedules: dict[str, dict] = {}
        self.admin_fail: dict[str, CloudError] = {}  # path substring -> error
        self.op_error: dict | None = None  # every operation ends with this error
        self.backups = [
            {
                "name": f"projects/{PROJECT}/locations/nam5/backups/b1",
                "database": DEFAULT,
                "state": "READY",
                "snapshotTime": "2026-09-30T00:00:00Z",
                "expireTime": "2026-10-07T00:00:00Z",
                "stats": {"sizeBytes": "2048", "documentCount": "7"},
            },
            {
                "name": f"projects/{PROJECT}/locations/eur3/backups/b2",
                "database": f"projects/{PROJECT}/databases/legacy",
                "state": "READY",
                "snapshotTime": "2026-10-01T00:00:00Z",
            },
        ]

    def admin_calls(self) -> list[tuple]:
        return [
            c[1:]
            for c in self.calls
            if c[0] == "firestore" and any(m == c[1] and re.fullmatch(p, c[2]) for m, p in ADMIN_PATHS)
        ]

    def _op(self, database: str, kind: str, **meta) -> dict:
        name = f"projects/{PROJECT}/databases/{database}/operations/op-{len(self.ops)}"
        self.ops[name] = {
            "name": name,
            "done": False,
            "metadata": {
                "@type": f"type.googleapis.com/google.firestore.admin.v1.{kind}",
                "operationState": "PROCESSING",
                "startTime": f"2026-10-02T00:00:{len(self.ops):02d}Z",
                **meta,
            },
        }
        return dict(self.ops[name])

    def firestore(self, method, path, body=None, params=None):
        assert cloud_gcp._FIRESTORE_PATH.match(path), path  # the real client's guard accepts it
        if not any(m == method and re.fullmatch(p, path) for m, p in ADMIN_PATHS):
            return super().firestore(method, path, body, params)
        self.calls.append(("firestore", method, path, body, params))
        for part, err in self.admin_fail.items():
            if part in path:
                raise err
        database = unquote(path.split("/")[1].split(":")[0]) if path.startswith("databases/") else None
        if path == "databases":
            assert set(body) == {"locationId", "type"} and set(params) == {"databaseId"}
            name = f"projects/{PROJECT}/databases/{params['databaseId']}"
            self.databases.append({"name": name, "locationId": body["locationId"], "type": body["type"]})
            return self._op(params["databaseId"], "CreateDatabaseMetadata")
        if path == "databases:restore":
            assert set(body) == {"databaseId", "backup"}
            name = f"projects/{PROJECT}/databases/{body['databaseId']}"
            location = body["backup"].split("/")[3]
            self.databases.append({"name": name, "locationId": location, "type": "FIRESTORE_NATIVE"})
            return self._op(body["databaseId"], "RestoreDatabaseMetadata", backup=body["backup"])
        if path.endswith(":exportDocuments"):
            assert set(body) <= {"outputUriPrefix", "collectionIds"}
            return self._op(
                database, "ExportDocumentsMetadata", outputUriPrefix=body["outputUriPrefix"],
                collectionIds=body.get("collectionIds", []),
            )  # fmt: skip
        if path.endswith(":importDocuments"):
            assert set(body) <= {"inputUriPrefix", "collectionIds"}
            return self._op(database, "ImportDocumentsMetadata", inputUriPrefix=body["inputUriPrefix"])
        if path.endswith("/operations"):
            return {"operations": [o for o in self.ops.values() if f"/databases/{database}/" in o["name"]]}
        if "/operations/" in path:
            op = self.ops[f"projects/{PROJECT}/{unquote(path)}"]
            if self.op_error:
                return {**op, "done": True, "error": self.op_error}
            was_done, op["done"] = op["done"], True
            op["metadata"]["operationState"] = "SUCCESSFUL"
            return {**op, "done": was_done}  # done on the second read
        if path.endswith("/backupSchedules"):
            if method == "GET":
                return {"backupSchedules": list(self.schedules.values())}
            assert set(body) in ({"retention", "dailyRecurrence"}, {"retention", "weeklyRecurrence"}), body
            sid = f"sched-{len(self.schedules)}"
            self.schedules[sid] = {
                "name": f"{DEFAULT}/backupSchedules/{sid}",
                "createTime": "2026-10-02T00:00:00Z",
                **body,
            }
            return self.schedules[sid]
        if "/backupSchedules/" in path:
            sid = path.rsplit("/", 1)[-1]
            if sid not in self.schedules:
                raise _fail("Backup schedule not found", "NOT_FOUND", 404)
            del self.schedules[sid]
            return {}
        return {"backups": self.backups}


@pytest.fixture
def gcp(monkeypatch):
    fake = FakeAdmin()
    fake.put("users/u1", {"name": "Ann"})
    cloud_gcp.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_db, "POLL_S", 0)
    yield fake
    cloud_gcp.set_factory(None)


@pytest.fixture
def viewer(db, team, make_user, auth_headers):
    user = make_user()
    db.add(ProjectMember(project_id=team["project"].id, user_id=user.id, role="viewer"))
    db.commit()
    return auth_headers(user)


def base(team):
    return f"/v1/projects/{team['project'].id}"


def connected(client, db, team) -> tuple:
    conn = connection(db, "firebase")
    body = {"connection_id": conn.id, "name": "Main", "database": "(default)"}
    resp = client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    return conn, resp.json()


def run_job(db, job_id: str) -> Job:
    jobs.run_queued()
    db.expire_all()
    return db.get(Job, job_id)


def test_create_a_named_firestore_database(client, db, team, gcp):
    conn = connection(db, "firebase")
    options = client.get(f"{base(team)}/cloud/databases/options", headers=team["dev"]).json()["firestore"]
    assert (
        "one database per project" in options["create_cost"]
        and {"id": "nam5", "label": options["locations"][0]["label"]} in options["locations"]
    )
    body = {"connection_id": conn.id, "name": "Orders", "engine": "firestore", "location": "eur3"}
    refused = client.post(f"{base(team)}/cloud/databases", json=body, headers=team["admin"])
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "billing_not_confirmed"
    assert "Firestore database" in refused.json()["error"]["message"] and gcp.admin_calls() == []
    body["confirm_billing"] = True
    assert client.post(f"{base(team)}/cloud/databases", json=body, headers=team["dev"]).status_code == 403
    bad = client.post(f"{base(team)}/cloud/databases", json={**body, "location": "mars1"}, headers=team["admin"])
    assert bad.status_code == 422
    taken = client.post(f"{base(team)}/cloud/databases", json={**body, "database": "(default)"}, headers=team["admin"])
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "database_exists"

    resp = client.post(f"{base(team)}/cloud/databases", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    source, job = resp.json()["data_source"], resp.json()["job"]
    database = source["cloud"]["resource_id"]
    assert source["status"] == "creating" and re.fullmatch(r"deployer-orders-[0-9a-f]{8}", database)
    assert source["cloud"]["created"] is False and source["cloud"]["resources"] == []  # never deleted by Deployer
    docs = client.get(f"{base(team)}/data-sources/{source['id']}/collections/users/documents", headers=team["dev"])
    assert docs.status_code == 409 and docs.json()["error"]["code"] == "cloud_database_creating"
    assert run_job(db, job["id"]).status == "succeeded"
    ds = db.get(DataSource, source["id"])
    assert ds.status == "ok" and ds.cloud_state["location"] == "eur3" and ds.engine == "firestore"
    create, *polls = gcp.admin_calls()
    assert create == ("POST", "databases", {"locationId": "eur3", "type": "FIRESTORE_NATIVE"}, {"databaseId": database})
    assert polls and all(c[0] == "GET" and c[1].startswith(f"databases/{database}/operations/") for c in polls)
    audit = db.query(AuditLog).filter(AuditLog.action == "data_source.create").one()
    assert audit.details["cloud"] == "create" and audit.details["engine"] == "firestore"
    # Removing it only forgets it: nothing in Google is deleted.
    gcp.calls.clear()
    assert client.delete(f"{base(team)}/data-sources/{source['id']}", headers=team["admin"]).json() == {"ok": True}
    assert gcp.fs_calls() == []


def test_failed_operation_leaves_the_source_in_error(client, db, team, gcp):
    conn = connection(db, "firebase")
    body = {"connection_id": conn.id, "name": "X", "engine": "firestore", "confirm_billing": True}
    out = client.post(f"{base(team)}/cloud/databases", json=body, headers=team["admin"]).json()
    gcp.op_error = {"code": 9, "message": "The project has no billing account"}
    job = run_job(db, out["job"]["id"])
    ds = db.get(DataSource, out["data_source"]["id"])
    assert job.status == "failed" and ds.status == "error" and "no billing account" in ds.status_message


def test_managed_export_and_import_into_a_new_database(client, db, team, gcp, viewer):
    _, source = connected(client, db, team)
    url = f"{base(team)}/data-sources/{source['id']}/firestore"
    body = {"bucket": "my-exports", "collections": ["users"]}
    refused = client.post(f"{url}/exports", json=body, headers=team["admin"])
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "billing_not_confirmed"
    body["confirm_billing"] = True
    assert client.post(f"{url}/exports", json=body, headers=team["dev"]).status_code == 403
    bad = client.post(f"{url}/exports", json={**body, "bucket": "Not A Bucket"}, headers=team["admin"])
    assert bad.status_code == 422
    nested = client.post(f"{url}/exports", json={**body, "collections": ["users/u1/orders"]}, headers=team["admin"])
    assert nested.status_code == 422  # collection ids, not paths
    gcp.fail["bucket"] = "Google API error 404: bucket not found"
    missing = client.post(f"{url}/exports", json=body, headers=team["admin"])
    assert missing.status_code == 400 and missing.json()["error"]["code"] == "bucket_unavailable"
    del gcp.fail["bucket"]

    out = client.post(f"{url}/exports", json=body, headers=team["admin"])
    assert out.status_code == 201, out.text
    out = out.json()
    assert out["bucket"] == "my-exports" and gcp.args("bucket") == [("my-exports",)] * 2
    assert re.fullmatch(r"gs://my-exports/deployer-exports/default/\d{8}-\d{6}", out["output_uri"])
    assert out["operation"]["kind"] == "export" and out["operation"]["state"] == "PROCESSING"
    sent = {"outputUriPrefix": out["output_uri"], "collectionIds": ["users"]}
    assert gcp.admin_calls()[-1] == ("POST", "databases/(default):exportDocuments", sent, None)
    made = client.post(f"{url}/exports", json={"create_bucket": True, "confirm_billing": True}, headers=team["admin"])
    assert made.status_code == 201 and made.json()["bucket"] == f"deployer-{PROJECT}-firestore"
    assert gcp.args("create_bucket") == [(f"deployer-{PROJECT}-firestore", "US")]  # nam5 -> the US multi-region
    assert db.query(AuditLog).filter(AuditLog.action == "data_source.cloud_export").count() == 2

    overview = client.get(f"{url}/backups", headers=viewer).json()
    assert overview["bucket"] == f"deployer-{PROJECT}-firestore" and overview["problems"] == {}
    assert [o["uri"] for o in overview["operations"]] == [made.json()["output_uri"], out["output_uri"]]
    assert "one read per document" in overview["costs"]["export"]

    imp = {"input_uri": out["output_uri"], "name": "Copy", "database": "copy-db"}
    assert client.post(f"{url}/import", json=imp, headers=team["admin"]).status_code == 422  # billing
    imp["confirm_billing"] = True
    bad_uri = client.post(f"{url}/import", json={**imp, "input_uri": "https://evil.example/x"}, headers=team["admin"])
    assert bad_uri.status_code == 422
    over = client.post(f"{url}/import", json={**imp, "database": "(default)"}, headers=team["admin"])
    assert over.status_code == 409  # never over an existing database
    resp = client.post(f"{url}/import", json=imp, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    copy = resp.json()["data_source"]
    assert copy["status"] == "creating" and copy["cloud"]["resource_id"] == "copy-db"
    gcp.calls.clear()
    assert run_job(db, resp.json()["job"]["id"]).status == "succeeded"
    calls = [(c[0], c[1]) for c in gcp.admin_calls()]
    assert calls[0] == ("POST", "databases") and ("POST", "databases/copy-db:importDocuments") in calls
    assert gcp.admin_calls()[calls.index(("POST", "databases/copy-db:importDocuments"))][2] == {
        "inputUriPrefix": out["output_uri"]
    }
    assert gcp.admin_calls()[0][2]["locationId"] == "nam5"  # the source database's location
    assert db.get(DataSource, copy["id"]).status == "ok"


def test_backup_schedules_backups_and_restore(client, db, team, gcp, viewer):
    _, source = connected(client, db, team)
    url = f"{base(team)}/data-sources/{source['id']}/firestore"
    daily = {"recurrence": "daily", "retention_days": 7}
    refused = client.post(f"{url}/backup-schedules", json=daily, headers=team["admin"])
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "billing_not_confirmed"
    daily["confirm_billing"] = True
    too_long = client.post(f"{url}/backup-schedules", json={**daily, "retention_days": 8}, headers=team["admin"])
    assert too_long.status_code == 422  # daily backups are kept 7 days at most
    made = client.post(f"{url}/backup-schedules", json=daily, headers=team["admin"])
    assert made.status_code == 201, made.text
    assert made.json() == {
        "id": "sched-0", "recurrence": "daily", "day": None, "retention_days": 7, "created_at": "2026-10-02T00:00:00Z",
    }  # fmt: skip
    assert gcp.admin_calls()[-1][2] == {"retention": "604800s", "dailyRecurrence": {}}
    again = client.post(f"{url}/backup-schedules", json=daily, headers=team["admin"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "schedule_exists"
    weekly = {"recurrence": "weekly", "retention_days": 28, "confirm_billing": True}
    assert client.post(f"{url}/backup-schedules", json=weekly, headers=team["admin"]).status_code == 422  # no day
    weekly["day"] = "SUNDAY"
    assert client.post(f"{url}/backup-schedules", json=weekly, headers=team["admin"]).status_code == 201
    assert gcp.admin_calls()[-1][2] == {"retention": "2419200s", "weeklyRecurrence": {"day": "SUNDAY"}}

    overview = client.get(f"{url}/backups", headers=viewer).json()
    assert [(s["recurrence"], s["day"], s["retention_days"]) for s in overview["schedules"]] == [
        ("daily", None, 7),
        ("weekly", "SUNDAY", 28),
    ]
    assert [b["id"] for b in overview["backups"]] == ["b1"]  # only this database's
    assert overview["backups"][0] | {"name": None} == {
        "name": None, "id": "b1", "location": "nam5", "state": "READY", "snapshot_time": "2026-09-30T00:00:00Z",
        "expire_time": "2026-10-07T00:00:00Z", "size_bytes": 2048, "documents": 7,
    }  # fmt: skip
    gone = client.delete(f"{url}/backup-schedules/sched-0", headers=team["admin"])
    assert gone.json() == {"ok": True} and ("DELETE", "databases/(default)/backupSchedules/sched-0", None, None) in (
        gcp.admin_calls()
    )
    assert client.delete(f"{url}/backup-schedules/sched-0", headers=team["admin"]).status_code == 404
    assert client.delete(f"{url}/backup-schedules/sched-1", headers=team["dev"]).status_code == 403

    backup = overview["backups"][0]["name"]
    restore = {"backup": backup, "name": "Restored", "confirm_billing": False}
    assert client.post(f"{url}/restore", json=restore, headers=team["admin"]).status_code == 422
    restore["confirm_billing"] = True
    other = {**restore, "backup": "projects/someone-else/locations/nam5/backups/b1"}
    assert client.post(f"{url}/restore", json=other, headers=team["admin"]).status_code == 422
    resp = client.post(f"{url}/restore", json=restore, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    new = resp.json()["data_source"]
    database = new["cloud"]["resource_id"]
    assert run_job(db, resp.json()["job"]["id"]).status == "succeeded"
    assert ("POST", "databases:restore", {"databaseId": database, "backup": backup}, None) in gcp.admin_calls()
    ds = db.get(DataSource, new["id"])
    assert ds.status == "ok" and ds.cloud_state["location"] == "nam5" and ds.cloud_state["restore_from"] == backup
    actions = {a.action for a in db.query(AuditLog)}
    assert {"data_source.cloud_backup_schedule", "data_source.cloud_backup_schedule_delete"} <= actions


def test_missing_role_empties_only_that_list(client, db, team, gcp):
    _, source = connected(client, db, team)
    gcp.admin_fail["backups"] = _fail("The caller does not have permission", "PERMISSION_DENIED", 403)
    overview = client.get(f"{base(team)}/data-sources/{source['id']}/firestore/backups", headers=team["dev"]).json()
    assert overview["backups"] == [] and "Cloud Datastore Owner" in overview["problems"]["backups"]
    assert set(overview["problems"]) == {"backups"}  # the schedules and exports still listed


def test_not_for_other_engines(client, db, team, gcp, make_source):
    other = make_source(team["project"], "nosql")
    resp = client.get(f"{base(team)}/data-sources/{other.id}/firestore/backups", headers=team["dev"])
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "wrong_source_kind"


def test_mcp_firestore_backup_tools(client, db, team, gcp):
    _, source = connected(client, db, team)
    key = client.post(f"{base(team)}/api-keys", json={"name": "k", "role": "service"}, headers=team["admin"])
    service = {"Authorization": f"Bearer {key.json()['secret']}"}

    def call(tool, auth, **arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        out = client.post(f"{base(team)}/mcp", json=body, headers=auth).json()
        if "error" in out:
            return True, out["error"]
        return out["result"]["isError"], json.loads(out["result"]["content"][0]["text"])

    err, listed = call("list_firestore_backups", service, source_id=source["id"])
    assert not err and listed["backups"][0]["id"] == "b1"
    err, _ = call("firestore_export", service, source_id=source["id"], bucket="b-1x", confirm_billing=True)
    assert err  # a service key is not an admin
    err, out = call("firestore_export", team["admin"], source_id=source["id"], bucket="b-1x", confirm_billing=False)
    assert err and out["error"]["code"] == "billing_not_confirmed"
    err, out = call("set_firestore_backup_schedule", team["admin"], source_id=source["id"], recurrence="weekly",
                    day="MONDAY", retention_days=14, confirm_billing=True)  # fmt: skip
    assert not err and out["recurrence"] == "weekly"
    err, out = call("delete_firestore_backup_schedule", team["admin"], source_id=source["id"], schedule_id=out["id"])
    assert not err and out == {"ok": True}
    err, out = call("restore_firestore_backup", team["admin"], source_id=source["id"], name="R",
                    backup=listed["backups"][0]["name"], confirm_billing=True)  # fmt: skip
    assert not err and out["data_source"]["status"] == "creating"
    err, out = call("create_cloud_database", team["admin"], connection_id=source["cloud"]["connection_id"], name="N",
                    engine="firestore", location="eur3", database="new-one", confirm_billing=True)  # fmt: skip
    assert not err and out["data_source"]["cloud"]["resource_id"] == "new-one"


def test_google_requirements_include_firestore_backups():
    reqs = cloud.requirements()["firebase"]
    roles = {r["role"]: r for r in reqs["roles"]}
    for role in ("roles/datastore.importExportAdmin", "roles/datastore.owner", "roles/storage.admin"):
        assert roles[role]["only_for"] == "firestore_backups"
    assert roles["roles/storage.admin"]["on"] == "bucket"
    assert "storage.googleapis.com" in {a["api"] for a in reqs["apis"]}


def test_real_client_admin_and_storage_urls():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    config = {"service_account": {"client_email": "admin@x", "private_key": pem}, "project_id": PROJECT}
    token = "ya29." + secrets.token_hex(8)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == cloud_gcp.TOKEN_URL:
            assert parse_qs(request.content.decode())["grant_type"]
            return httpx.Response(200, json={"access_token": token, "expires_in": 3600})
        assert request.headers["Authorization"] == f"Bearer {token}"
        if request.url.path == "/storage/v1/b" and request.method == "POST":
            return httpx.Response(409, json={"error": {"code": 409, "message": "exists"}})
        if request.url.path.startswith("/storage/v1/b/"):
            return httpx.Response(403, json={"error": {"code": 403, "message": "no access"}})
        return httpx.Response(200, json={"name": "op"})

    cloud_gcp.set_transport(httpx.MockTransport(handle))
    try:
        gcp = cloud_gcp.client(config)
        gcp.firestore("POST", "databases:restore", {"databaseId": "r1", "backup": "b"})
        gcp.firestore("POST", "databases", {"locationId": "nam5"}, {"databaseId": "new-db"})
        gcp.firestore("GET", "locations/-/backups")
        gcp.firestore("DELETE", "databases/(default)/backupSchedules/s1")
        gcp.firestore("GET", "databases/(default)/operations/AbC-1")
        paths = [r.url.raw_path.decode() for r in seen if r.url.host == "firestore.googleapis.com"]
        assert paths == [
            f"/v1/projects/{PROJECT}/databases:restore",
            f"/v1/projects/{PROJECT}/databases?databaseId=new-db",
            f"/v1/projects/{PROJECT}/locations/-/backups",
            f"/v1/projects/{PROJECT}/databases/(default)/backupSchedules/s1",
            f"/v1/projects/{PROJECT}/databases/(default)/operations/AbC-1",
        ]
        for bad in ("locations/-/backups/../../x", "databases/(default)/operations/../../../other", "projects/x"):
            with pytest.raises(CloudError, match="unexpected Firestore path"):
                gcp.firestore("GET", bad)
        with pytest.raises(CloudError, match="taken by another Google project"):
            gcp.create_bucket("deployer-x-firestore", "US")
        insert = next(r for r in seen if r.method == "POST" and r.url.path == "/storage/v1/b")
        assert insert.url.params["project"] == PROJECT
        assert json.loads(insert.content)["iamConfiguration"]["publicAccessPrevention"] == "enforced"
        with pytest.raises(CloudError, match="Invalid Cloud Storage bucket"):
            gcp.bucket("../etc")
    finally:
        cloud_gcp.set_transport(None)
    assert all(
        r.url.host in ("oauth2.googleapis.com", "firestore.googleapis.com", "storage.googleapis.com") for r in seen
    )
