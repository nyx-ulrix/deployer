"""Firebase Realtime Database engine, phase C2-4 (docs/CLOUD.md): a Firebase project's Realtime Database connected
(or its default one created) as a data source, the JSON tree read lazily (shallow) and written by path, Firebase's
REST query parameters, the JSON console, schema inference, the JSON export, Cloud Run apps getting the database and
the MCP tools. The database is an in-memory fake behind `GcpClient.rtdb`; the real client's URLs, token scopes,
size cap and error parsing run against httpx.MockTransport. Nothing here reaches Google."""

import copy
import json
import secrets
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.errors import CloudError
from app.models import App, AuditLog, DataSource, ProjectMember
from app.services import cloud, cloud_deploy, cloud_gcp, rtdb
from tests.test_cloud import FakeCloud, connection, deploy

PROJECT = "demo-proj-123"
URL = f"https://{PROJECT}-default-rtdb.firebaseio.com"
INSTANCE = {
    "name": f"projects/123456789/locations/us-central1/instances/{PROJECT}-default-rtdb",
    "databaseUrl": URL,
    "type": "DEFAULT_DATABASE",
    "state": "ACTIVE",
}


def _fail(message: str, status: int) -> CloudError:
    return CloudError(f"Google API error {status}: {message}", status=status)


class FakeRtdb(FakeCloud):
    """FakeCloud for the hosting calls, plus an in-memory Realtime Database behind `rtdb` that understands the
    paths and query parameters services/rtdb.py sends (answers are unordered, like Firebase's REST API)."""

    def __init__(self, **returns):
        super().__init__(**returns)
        self.tree: dict = {}
        self.instances = [dict(INSTANCE)]
        self.indexed = {"users": {"age"}}  # .indexOn rules: path -> children ordered by
        self.rtdb_fail: dict[str, CloudError] = {}  # method -> error
        self.pushed = 0

    def rtdb_calls(self) -> list[tuple]:
        return [c[1:] for c in self.calls if c[0] == "rtdb"]

    def rtdb_instances(self):
        self.calls.append(("rtdb_instances",))
        return copy.deepcopy(self.instances)

    def create_rtdb_instance(self, location, database_id):
        self.calls.append(("create_rtdb_instance", location, database_id))
        if "create_rtdb_instance" in self.fail:
            raise _fail(self.fail["create_rtdb_instance"], 403)
        inst = {
            "name": f"projects/123456789/locations/{location}/instances/{database_id}",
            "databaseUrl": f"https://{database_id}.{location}.firebasedatabase.app",
            "type": "DEFAULT_DATABASE",
            "state": "ACTIVE",
        }
        self.instances.append(inst)
        return inst

    def _node(self, parts):
        node = self.tree
        for p in parts:
            node = node.get(p) if isinstance(node, dict) else None
        return node

    def _set(self, parts, value):
        node = self.tree
        for p in parts[:-1]:
            if not isinstance(node.get(p), dict):
                node[p] = {}
            node = node[p]
        if value is None:
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = copy.deepcopy(value)

    def rtdb(self, method, base_url, path="", body=None, params=None):
        self.calls.append(("rtdb", method, base_url, path, body, params))
        assert base_url in {i["databaseUrl"] for i in self.instances}, base_url
        if method in self.rtdb_fail:
            raise self.rtdb_fail[method]
        from urllib.parse import unquote

        parts = [unquote(p) for p in path.split("/") if p]
        params = dict(params or {})
        if method == "GET":
            value = copy.deepcopy(self._node(parts))
            if params.get("shallow") == "true":
                assert set(params) == {"shallow"}
                if isinstance(value, dict):  # like Firebase: objects cut to true, plain values kept
                    return {k: True if isinstance(v, dict) else v for k, v in reversed(value.items())}
                return value
            if "orderBy" not in params or not isinstance(value, dict):
                return value
            order = json.loads(params["orderBy"])
            if order not in rtdb.ORDER_SPECIAL and order not in self.indexed.get("/".join(parts), set()):
                raise _fail(
                    f'Index not defined, add ".indexOn": "{order}", for path "/{"/".join(parts)}", to the rules', 400
                )
            items = rtdb.ordered(value, order)

            def by(kv):
                return (
                    kv[0] if order == "$key" else kv[1] if order == "$value" else rtdb._child(kv[1], order.split("/"))
                )

            for name, keep in (
                ("startAt", lambda have, want: rtdb._rank(have) >= rtdb._rank(want)),
                ("endAt", lambda have, want: rtdb._rank(have) <= rtdb._rank(want)),
                ("equalTo", lambda have, want: have == want),
            ):
                if name in params:
                    want = json.loads(params[name])
                    items = [kv for kv in items if keep(by(kv), want)]
            if "limitToFirst" in params:
                items = items[: int(params["limitToFirst"])]
            if "limitToLast" in params:
                items = items[-int(params["limitToLast"]) :]
            return dict(reversed(items))  # unordered on purpose
        if method == "PUT":
            self._set(parts, body)
            return body
        if method == "PATCH":
            for k, v in body.items():
                self._set(parts + k.split("/"), v)
            return body
        if method == "POST":
            self.pushed += 1
            key = f"-Npush{self.pushed:04d}"
            self._set([*parts, key], body)
            return {"name": key}
        assert method == "DELETE"
        self._set(parts, None)
        return None


@pytest.fixture
def gcp(monkeypatch):
    fake = FakeRtdb(
        project_info={"projectId": PROJECT, "projectNumber": "123456789"},
        create_version=lambda site, config: f"sites/{site}/versions/v1",
        ensure_repository=f"us-central1-docker.pkg.dev/{PROJECT}/deployer",
        docker_login=("us-central1-docker.pkg.dev", "oauth2accesstoken", "ya29." + secrets.token_hex(16)),
        create_service=f"projects/{PROJECT}/locations/us-central1/operations/op1",
        update_service=f"projects/{PROJECT}/locations/us-central1/operations/op2",
        operation={"done": True, "error": None},
    )
    fake.tree = {
        "users": {
            "ann": {"name": "Ann", "age": 31, "address": {"city": "Oslo"}},
            "bo": {"name": "Bo", "age": 25, "address": {"city": "Rome"}},
            "cy": {"name": "Cy", "age": 40, "tags": {"admin": True}},
        },
        "rooms": {"lobby": {"topic": "hello", "messages": {"m1": {"text": "hi"}, "m2": {"text": "yo"}}}},
        "motd": "Welcome",
        "scores": {"10": 3, "9": 7, "a": 1},
    }
    cloud_gcp.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    yield fake
    cloud_gcp.set_factory(None)


def base(team):
    return f"/v1/projects/{team['project'].id}"


def connect(client, team, conn, name="Live data"):
    body = {"connection_id": conn.id, "name": name, "instance": f"{PROJECT}-default-rtdb"}
    resp = client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    return resp.json()


def tree_url(team, source):
    return f"{base(team)}/data-sources/{source['id']}/rtdb"


@pytest.fixture
def viewer(db, team, make_user, auth_headers):
    user = make_user()
    db.add(ProjectMember(project_id=team["project"].id, user_id=user.id, role="viewer"))
    db.commit()
    return auth_headers(user)


# --- paths, values, query parameters, order --------------------------------------------------------------


def test_paths_values_query_parameters_and_order():
    assert (
        rtdb.check_path("/users/ann/") == ["users", "ann"] and rtdb.check_path("") == [] and rtdb.check_path(None) == []
    )
    for bad in ("users/a.b", "a//b", "x$", "a[0]", "#", 5, "/".join(["k"] * 33)):
        with pytest.raises(Exception, match="Realtime Database|at most|is text"):
            rtdb.check_path(bad)
    rtdb.check_value({"a": [1, {"b": None}], ".sv": "timestamp", "n": 1.5})
    for bad in ({"a.b": 1}, {"x": float("nan")}, {"s": object()}):
        with pytest.raises(Exception, match="key|NaN|Unsupported"):
            rtdb.check_value(bad)
    assert rtdb.query_params({"shallow": True}) == {"shallow": "true"}
    assert rtdb.query_params({"orderBy": "address/city", "equalTo": "Oslo", "limitToFirst": 5}) == {
        "orderBy": '"address/city"',
        "equalTo": '"Oslo"',
        "limitToFirst": "5",
    }
    assert rtdb.query_params({"orderBy": "$value", "startAt": 3, "endAt": True}) == {
        "orderBy": '"$value"',
        "startAt": "3",
        "endAt": "true",
    }
    for bad, message in (
        ({"shallow": True, "orderBy": "$key"}, "shallow cannot"),
        ({"limitToFirst": 3}, "need"),
        ({"orderBy": "$key", "limitToFirst": 0}, "1 or more"),
        ({"orderBy": "$key", "limitToFirst": 1, "limitToLast": 1}, "not both"),
        ({"orderBy": "$key", "startAt": {"a": 1}}, "text, number"),
    ):
        with pytest.raises(Exception, match=message):
            rtdb.query_params(bad)
    # Firebase's order: null, false, true, numbers, text, objects; keys: 32-bit whole numbers first.
    values = {"a": "x", "b": 2, "c": None, "d": True, "e": {"o": 1}, "f": False, "g": 1.5}
    assert [k for k, _ in rtdb.ordered(values, "$value")] == ["c", "f", "d", "g", "b", "a", "e"]
    assert [k for k, _ in rtdb.ordered({"10": 0, "9": 0, "a": 0, "-1": 0, "007": 0}, "$key")] == [
        "-1",
        "9",
        "10",
        "007",
        "a",
    ]
    assert [k for k, _ in rtdb.ordered(["x", None, "z"], None)] == ["0", "2"]
    assert rtdb.ordered("plain", "$key") is None


# --- connect / create / remove ------------------------------------------------------------------------------


def test_connect_create_and_never_delete(client, db, team, gcp):
    conn = connection(db, "firebase")
    options = client.get(f"{base(team)}/cloud/databases/options", headers=team["dev"]).json()
    assert "JSON tree" in options["rtdb"]["short"] and "documents" in options["firestore"]["short"]
    assert [loc["id"] for loc in options["rtdb"]["locations"]] == list(rtdb.LOCATIONS)
    firebase = next(loc for loc in options["locations"] if loc["id"] == "firebase")
    assert "Realtime Database" in firebase["what"] and "coming soon" not in firebase["note"]
    listing = client.get(f"{base(team)}/cloud/connections/{conn.id}/databases", headers=team["admin"]).json()
    assert (
        listing["rtdb"]
        == [
            {
                "id": f"{PROJECT}-default-rtdb",
                "url": URL,
                "location": "us-central1",
                "type": "DEFAULT_DATABASE",
                "state": "ACTIVE",
                "problem": None,
            }
        ]
        and listing["rtdb_problem"] is None
    )

    connect_url = f"{base(team)}/cloud/databases/connect"
    missing = client.post(
        connect_url, json={"connection_id": conn.id, "name": "X", "instance": "nope"}, headers=team["admin"]
    )
    assert missing.status_code == 400 and "create the default one" in missing.json()["error"]["message"]
    body = {"connection_id": conn.id, "name": "X", "instance": f"{PROJECT}-default-rtdb"}
    assert client.post(connect_url, json=body, headers=team["dev"]).status_code == 403
    gcp.rtdb_fail["GET"] = _fail("Permission denied", 401)
    denied = client.post(connect_url, json=body, headers=team["admin"])
    assert denied.status_code == 400 and "Realtime Database Admin" in denied.json()["error"]["message"]
    del gcp.rtdb_fail["GET"]

    source = connect(client, team, conn)
    assert source["engine"] == "firebase_rtdb" and source["kind"] == "nosql" and source["status"] == "ok"
    cloud_info = source["cloud"]
    assert cloud_info["service"] == "rtdb" and cloud_info["url"] == URL and cloud_info["resource_kind"] == "database"
    assert cloud_info["resource_id"] == f"{PROJECT}-default-rtdb" and cloud_info["created"] is False
    assert cloud_info["resources"] == [] and source["display"]["host"] == f"{PROJECT}-default-rtdb.firebaseio.com"
    info = client.get(f"{base(team)}/data-sources/{source['id']}/connection", headers=team["dev"]).json()
    assert info["uri"] == URL and info["password"] is None and info["project_id"] == PROJECT
    assert client.post(f"{base(team)}/data-sources/{source['id']}/check", headers=team["dev"]).json()["status"] == "ok"
    edit = client.patch(f"{base(team)}/data-sources/{source['id']}", json={"config": {"x": 1}}, headers=team["admin"])
    assert edit.status_code == 422
    assert client.delete(f"/v1/instance/cloud/{conn.id}", headers=team["owner"]).status_code == 409
    gcp.calls.clear()
    assert client.delete(f"{base(team)}/data-sources/{source['id']}", headers=team["admin"]).json() == {"ok": True}
    assert gcp.rtdb_calls() == [] and gcp.tree["motd"] == "Welcome"


def test_create_default_database_is_confirmed_and_idempotent(client, db, team, gcp):
    conn = connection(db, "firebase")
    gcp.instances = []
    url = f"{base(team)}/cloud/databases"
    body = {"connection_id": conn.id, "name": "Chat", "engine": "firebase_rtdb", "location": "europe-west1"}
    unconfirmed = client.post(url, json=body, headers=team["admin"])
    assert unconfirmed.status_code == 422 and unconfirmed.json()["error"]["code"] == "billing_not_confirmed"
    assert "US$5 per GB" in unconfirmed.json()["error"]["message"] and gcp.args("create_rtdb_instance") == []
    body["confirm_billing"] = True
    bad = client.post(url, json={**body, "location": "mars-north1"}, headers=team["admin"])
    assert bad.status_code == 422
    created = client.post(url, json=body, headers=team["admin"])
    assert created.status_code == 201, created.text
    assert created.json()["job"] is None
    assert gcp.args("create_rtdb_instance") == [("europe-west1", f"{PROJECT}-default-rtdb")]
    source = created.json()["data_source"]
    assert source["cloud"]["url"] == f"https://{PROJECT}-default-rtdb.europe-west1.firebasedatabase.app"
    assert source["cloud"]["region"] == "europe-west1" and source["cloud"]["created"] is False
    audit = db.query(AuditLog).filter(AuditLog.action == "data_source.create").one()
    assert audit.details["cloud"] == "create" and audit.details["engine"] == "firebase_rtdb"
    # It exists now: a second create connects it instead of making another.
    again = client.post(url, json={**body, "name": "Chat 2"}, headers=team["admin"])
    assert again.status_code == 201 and len(gcp.args("create_rtdb_instance")) == 1
    # An existing default database that is disabled is not connected blindly.
    gcp.instances[-1]["state"] = "DISABLED"
    disabled = client.post(url, json={**body, "name": "Chat 4"}, headers=team["admin"])
    assert disabled.status_code == 400 and "disabled" in disabled.json()["error"]["message"]
    assert len(gcp.args("create_rtdb_instance")) == 1
    # Firebase refusing (no role / API) says what to turn on.
    gcp.instances = []
    gcp.fail["create_rtdb_instance"] = "Google API error 403: The caller does not have permission"
    denied = client.post(url, json={**body, "name": "Chat 3"}, headers=team["admin"])
    assert denied.status_code == 502 and "Management API" in denied.json()["error"]["message"]


# --- read and write by path -----------------------------------------------------------------------------------


def test_browse_lazily_query_and_write_by_path(client, db, team, gcp, viewer):
    source = connect(client, team, connection(db, "firebase"))
    url, dev = tree_url(team, source), team["dev"]
    root = client.get(url, params={"shallow": "true"}, headers=viewer).json()
    assert root["path"] == "" and [c["key"] for c in root["children"]] == ["motd", "rooms", "scores", "users"]
    assert {c["key"]: c["value"] for c in root["children"]}["motd"] == "Welcome"
    assert gcp.rtdb_calls()[-1][2:] == ("", None, {"shallow": "true"})
    lobby = client.get(url, params={"path": "rooms/lobby", "shallow": "true"}, headers=viewer).json()
    assert lobby["value"] == {"topic": "hello", "messages": True}
    assert client.get(url, params={"path": "motd"}, headers=viewer).json() == {"path": "motd", "value": "Welcome"}
    leaf = {"path": "motd", "value": "Welcome"}  # no children: the tree shows a leaf
    assert client.get(url, params={"path": "motd", "shallow": "true"}, headers=viewer).json() == leaf
    assert client.get(url, params={"path": "nothing/here"}, headers=viewer).json()["value"] is None
    # Firebase's query parameters; children come back in Firebase's order (the REST answer is unordered).
    by_age = client.get(url, params={"path": "users", "orderBy": "age", "startAt": "26"}, headers=viewer).json()
    assert [c["key"] for c in by_age["children"]] == ["ann", "cy"]
    sent = gcp.rtdb_calls()[-1][4]
    assert sent == {"orderBy": '"age"', "startAt": "26"}
    oslo = client.get(url, params={"path": "users", "orderBy": "address/city", "equalTo": "Oslo"}, headers=viewer)
    assert oslo.status_code == 400 and ".indexOn" in oslo.json()["error"]["message"]
    last = client.get(url, params={"path": "users", "orderBy": "$key", "limitToLast": 2}, headers=viewer).json()
    assert [c["key"] for c in last["children"]] == ["bo", "cy"]
    scores = client.get(url, params={"path": "scores", "orderBy": "$key"}, headers=viewer).json()
    assert [c["key"] for c in scores["children"]] == ["9", "10", "a"]
    assert client.get(url, params={"path": "a.b"}, headers=viewer).status_code == 400
    assert client.get(url, params={"shallow": "true", "orderBy": "$key"}, headers=viewer).status_code == 400

    put = client.put(url, json={"path": "users/di", "value": {"name": "Di", "age": 22}}, headers=dev)
    assert put.status_code == 200 and gcp.tree["users"]["di"] == {"name": "Di", "age": 22}
    patched = client.patch(url, json={"path": "users/ann", "value": {"age": 32, "address/city": "Bergen"}}, headers=dev)
    assert patched.status_code == 200 and gcp.tree["users"]["ann"]["address"]["city"] == "Bergen"
    assert gcp.tree["users"]["ann"]["name"] == "Ann"  # update keeps the other children
    pushed = client.post(url, json={"path": "rooms/lobby/messages", "value": {"text": "new"}}, headers=dev).json()
    assert pushed["key"].startswith("-N") and gcp.tree["rooms"]["lobby"]["messages"][pushed["key"]] == {"text": "new"}
    assert client.delete(url, params={"path": "users/di"}, headers=dev).json() == {"path": "users/di", "deleted": True}
    assert "di" not in gcp.tree["users"]
    for method, kwargs in (("put", {"json": {"path": "", "value": {}}}), ("delete", {"params": {"path": "/"}})):
        refused = getattr(client, method)(url, headers=dev, **kwargs)
        assert refused.status_code == 400 and refused.json()["error"]["code"] == "root_write"
    assert client.put(url, json={"path": "x", "value": {"bad.key": 1}}, headers=dev).status_code == 400
    assert client.put(url, json={"path": "x"}, headers=dev).status_code == 400  # null: use delete
    assert client.patch(url, json={"path": "x", "value": 5}, headers=dev).status_code == 400
    # Viewers and anon keys read; writes need developer+.
    key = client.post(f"{base(team)}/api-keys", json={"name": "k", "role": "anon"}, headers=team["admin"]).json()
    anon = {"Authorization": f"Bearer {key['secret']}"}
    assert client.get(url, params={"path": "motd"}, headers=anon).json()["value"] == "Welcome"
    assert client.put(url, json={"path": "motd", "value": "x"}, headers=anon).status_code == 403
    assert client.put(url, json={"path": "motd", "value": "x"}, headers=viewer).status_code == 403
    # A too-big answer is refused, not buffered; collections / documents don't apply to a JSON tree.
    gcp.rtdb_fail["GET"] = CloudError("More than 32 MB of data at this path", code="TOO_LARGE", status=413)
    assert client.get(url, headers=viewer).status_code == 413
    del gcp.rtdb_fail["GET"]
    docs = client.get(f"{base(team)}/data-sources/{source['id']}/collections/users/documents", headers=viewer)
    assert docs.status_code == 400 and "rtdb_read" in docs.json()["error"]["message"]
    coll = client.post(f"{base(team)}/data-sources/{source['id']}/collections", json={"name": "x"}, headers=dev)
    assert coll.status_code == 400


def test_rtdb_routes_refuse_other_sources(client, db, team, gcp, make_source):
    other = make_source(team["project"], kind="nosql", engine="mongodb")
    out = client.get(f"{base(team)}/data-sources/{other.id}/rtdb", headers=team["dev"])
    assert out.status_code == 400 and out.json()["error"]["code"] == "wrong_source_kind"


# --- query console, schema, export ------------------------------------------------------------------------------


def test_query_console_json_requests(client, db, team, gcp, viewer):
    source = connect(client, team, connection(db, "firebase"))
    url = f"{base(team)}/data-sources/{source['id']}/query"

    def run(request, headers=viewer, max_rows=2):
        text = request if isinstance(request, str) else json.dumps(request)
        return client.post(url, json={"query": text, "max_rows": max_rows}, headers=headers)

    out = run({"path": "users", "orderBy": "age"}).json()
    assert out["engine"] == "firebase_rtdb" and out["error"] is None
    assert [d["_key"] for d in out["result_docs"]] == ["bo", "ann"] and out["truncated"] is True
    assert out["result_docs"][0]["name"] == "Bo" and gcp.rtdb_calls()[-1][4]["limitToFirst"] == "3"
    assert "More children" in out["output"]
    plain = run({"path": "motd"}).json()
    assert plain["result"] == {"path": "motd", "value": "Welcome"} and plain["result_docs"] is None
    scores = run({"path": "scores"}, max_rows=10).json()["result_docs"]
    assert scores == [{"_key": "9", "_value": 7}, {"_key": "10", "_value": 3}, {"_key": "a", "_value": 1}]
    refused = run({"operation": "set", "path": "motd", "value": "x"})
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "read_only_role"
    dev = team["dev"]
    assert run({"operation": "set", "path": "motd", "value": "Hi"}, dev).json()["output"] == "set /motd"
    assert gcp.tree["motd"] == "Hi"
    pushed = run({"operation": "push", "path": "rooms/lobby/messages", "value": {"text": "x"}}, dev).json()
    assert "new key -N" in pushed["output"]
    assert run({"operation": "update", "path": "users/bo", "value": {"age": 26}}, dev).json()["error"] is None
    assert gcp.tree["users"]["bo"]["age"] == 26
    assert run({"operation": "delete", "path": "motd"}, dev).json()["result"] == {"path": "motd", "deleted": True}
    # Mistakes come back in-band.
    assert "JSON" in run("db.users.find()", dev).json()["error"]["message"]
    assert "Unknown field 'limit'" in run({"path": "users", "limit": 3}).json()["error"]["message"]
    assert "must be one of" in run({"operation": "drop"}).json()["error"]["message"]
    assert (
        "only go with get"
        in run({"operation": "delete", "path": "x", "orderBy": "$key"}, dev).json()["error"]["message"]
    )
    assert "whole database" in run({"operation": "delete", "path": ""}, dev).json()["error"]["message"]
    assert ".indexOn" in run({"path": "users", "orderBy": "name"}).json()["error"]["message"]


def test_schema_and_export(client, db, team, gcp):
    source = connect(client, team, connection(db, "firebase"))
    out = client.get(f"{base(team)}/schema", params={"source_id": source["id"]}, headers=team["dev"]).json()
    schema = out["sources"][0]
    assert schema["status"] == "ok", schema["error"]
    assert [e["name"] for e in schema["entities"]] == ["motd", "rooms", "scores", "users"]
    users = next(e for e in schema["entities"] if e["name"] == "users")
    names = {f["name"]: f for f in users["fields"]}
    assert users["fields"][0]["name"] == "_key" and names["_key"]["primary_key"]
    assert names["age"]["data_type"] == "int" and names["address.city"]["data_type"] == "string"
    scores = next(e for e in schema["entities"] if e["name"] == "scores")
    assert "_value" in {f["name"] for f in scores["fields"]}
    export = client.get(
        f"{base(team)}/schema/export", params={"format": "mongo", "source_id": source["id"]}, headers=team["dev"]
    )
    assert export.status_code == 200 and URL in export.text and "motd, rooms, scores, users" in export.text
    assert not [i for i in out["conventions"] if i["rule"] in ("N1", "N2")]  # keys are data, not names

    url = f"{base(team)}/data-sources/{source['id']}/rtdb-export"
    whole = client.get(url, headers=team["dev"]).json()
    assert whole["data"] == gcp.tree and whole["url"] == URL and whole["path"] == ""
    assert gcp.rtdb_calls()[-1][4] == {"format": "export"}
    part = client.get(url, params={"path": "rooms/lobby"}, headers=team["dev"]).json()
    assert part["data"]["topic"] == "hello" and part["path"] == "rooms/lobby"
    assert db.query(AuditLog).filter(AuditLog.action == "data_source.export").count() == 2


# --- apps on Cloud Run ---------------------------------------------------------------------------------------------


def test_cloud_run_app_gets_its_realtime_database(client, db, docker, team, gcp):
    conn = connection(db, "firebase")
    connect(client, team, conn, name="Live data")
    body = {"name": "Api", "repo_url": "https://github.com/acme/api", "preset": "node", "target": "firebase_app"}
    body |= {"cloud_connection_id": conn.id, "database_access": True}
    resp = client.post(f"{base(team)}/apps", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    dep = deploy(db, db.get(App, resp.json()["id"]))
    assert dep.status == "live", dep.error
    env = gcp.args("create_service")[0][3]
    assert env["DEPLOYER_DB_LIVE_DATA_URL"] == URL and env["DEPLOYER_DB_LIVE_DATA_PROJECT"] == PROJECT
    assert env["DEPLOYER_DB_LIVE_DATA_DATABASE"] == f"{PROJECT}-default-rtdb"
    assert not any("PASSWORD" in k for k in env)
    assert "123456789-compute@developer.gserviceaccount.com" in dep.log and "Realtime Database Admin" in dep.log


# --- MCP, requirements, the real client -------------------------------------------------------------------------


def test_mcp_rtdb_tools(client, db, team, gcp):
    key = client.post(f"{base(team)}/api-keys", json={"name": "k", "role": "service"}, headers=team["admin"])
    headers = {"Authorization": f"Bearer {key.json()['secret']}"}
    conn = connection(db, "firebase")

    def call(tool, **arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        out = client.post(f"{base(team)}/mcp", json=body, headers=headers).json()["result"]
        return out["isError"], json.loads(out["content"][0]["text"])

    _, listed = call("list_cloud_databases", connection_id=conn.id)
    assert listed["rtdb"][0]["url"] == URL
    err, refused = call(
        "create_cloud_database", connection_id=conn.id, name="Rt", engine="firebase_rtdb", confirm_billing=False
    )
    assert err and refused["error"]["code"] == "billing_not_confirmed"
    err, source = call("connect_cloud_database", connection_id=conn.id, name="Rt", instance=f"{PROJECT}-default-rtdb")
    assert not err and source["engine"] == "firebase_rtdb"
    _, top = call("rtdb_read", source_id=source["id"], shallow=True)
    assert [c["key"] for c in top["children"]] == ["motd", "rooms", "scores", "users"]
    _, young = call("rtdb_read", source_id=source["id"], path="users", orderBy="age", endAt=30)
    assert [c["key"] for c in young["children"]] == ["bo"] and gcp.rtdb_calls()[-1][4]["limitToFirst"] == "200"
    err, pushed = call(
        "rtdb_write", source_id=source["id"], operation="push", path="rooms/lobby/messages", value={"t": 1}
    )
    assert not err and pushed["key"]
    err, out = call("rtdb_write", source_id=source["id"], operation="set", path="flags/beta", value=True)
    assert not err and gcp.tree["flags"] == {"beta": True}
    _, dumped = call("export_documents", source_id=source["id"], path="flags")
    assert dumped["data"] == {"beta": True}
    err, out = call(
        "run_query", source_id=source["id"], query='{"path": "users", "orderBy": "$key", "limitToFirst": 1}'
    )
    assert not err and [d["_key"] for d in out["result_docs"]] == ["ann"]
    err, out = call("list_documents", source_id=source["id"], collection="users")
    assert err and "rtdb_read" in out["error"]["message"]


def test_google_requirements_include_the_realtime_database():
    reqs = cloud.requirements()["firebase"]
    assert "roles/firebasedatabase.admin" in {r["role"] for r in reqs["roles"]}
    assert "firebasedatabase.googleapis.com" in {a["api"] for a in reqs["apis"]}


def test_real_client_rtdb_urls_scopes_errors_and_size_cap(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    config = {"service_account": {"client_email": "rt@x", "private_key": pem}, "project_id": PROJECT}
    tokens = {"cloud": "ya29.c" + secrets.token_hex(6), "rtdb": "ya29.r" + secrets.token_hex(6)}
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == cloud_gcp.TOKEN_URL:
            claims = jwt.decode(parse_qs(request.content.decode())["assertion"][0], options={"verify_signature": False})
            which = "rtdb" if "firebase.database" in claims["scope"] else "cloud"
            return httpx.Response(200, json={"access_token": tokens[which], "expires_in": 3600})
        if request.url.host == "firebasedatabase.googleapis.com":
            assert request.headers["Authorization"] == f"Bearer {tokens['cloud']}"
            if request.method == "POST":
                return httpx.Response(200, json={**INSTANCE, "body": json.loads(request.content)})
            return httpx.Response(200, json={"instances": [INSTANCE]})
        assert request.headers["Authorization"] == f"Bearer {tokens['rtdb']}"
        if request.url.path == "/secret.json":
            return httpx.Response(401, json={"error": "Permission denied"})
        if request.url.path == "/big.json":
            return httpx.Response(200, content=b"[" + b"1," * 600 + b"1]")
        return httpx.Response(200, json={"a b": True})

    cloud_gcp.set_transport(httpx.MockTransport(handle))
    monkeypatch.setattr(cloud_gcp, "RTDB_MAX_BYTES", 1000)
    try:
        gcp = cloud_gcp.client(config)
        ds = DataSource(engine=rtdb.ENGINE, cloud_state={"url": URL, "project_id": PROJECT})
        assert rtdb.call(ds, "GET", ["users", "a b", "x%y"], params={"shallow": "true"}, gcp=gcp) == {"a b": True}
        assert seen[-1].url.raw_path.decode() == "/users/a%20b/x%25y.json?shallow=true"
        assert seen[-1].url.host == f"{PROJECT}-default-rtdb.firebaseio.com"
        with pytest.raises(CloudError) as denied:
            gcp.rtdb("GET", URL, "/secret")
        assert denied.value.status == 401 and "Permission denied" in denied.value.message
        with pytest.raises(CloudError) as big:
            gcp.rtdb("GET", URL, "/big")
        assert big.value.code == "TOO_LARGE"
        for bad_url, bad_path in (
            (f"https://evil.example/{PROJECT}", ""),
            ("http://x.firebaseio.com", ""),
            (URL, "/a/../b"),
        ):
            with pytest.raises(CloudError, match="unexpected Realtime Database"):
                gcp.rtdb("GET", bad_url, bad_path)
        assert gcp.rtdb_instances() == [INSTANCE]
        assert seen[-1].url.path == f"/v1beta/projects/{PROJECT}/locations/-/instances"
        gcp.create_rtdb_instance("europe-west1", f"{PROJECT}-default-rtdb")
        assert seen[-1].url.params["databaseId"] == f"{PROJECT}-default-rtdb"
        assert json.loads(seen[-1].content) == {"type": "DEFAULT_DATABASE"}
        with pytest.raises(CloudError):
            gcp.create_rtdb_instance("../x", "y")
    finally:
        cloud_gcp.set_transport(None)
    # The two scopes get their own tokens; each is exchanged once.
    assert sum(str(r.url) == cloud_gcp.TOKEN_URL for r in seen) == 2
