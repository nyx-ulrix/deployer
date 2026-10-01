"""Cloud Firestore engine, phase C2-3 (docs/CLOUD.md): a Firebase project's Firestore database connected as a
data source, documents (and subcollections by path) in the data browser / data API, the JSON query console,
schema inference, the JSON export, Cloud Run apps getting the database, and the MCP tools. Firestore is an
in-memory fake behind `GcpClient.firestore`; the real client's URL building and token flow run against
httpx.MockTransport. Nothing here reaches Google."""

import json
import re
import secrets
from urllib.parse import parse_qs, unquote

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.errors import CloudError
from app.models import App, AuditLog, DataSource, ProjectMember
from app.services import cloud, cloud_deploy, cloud_gcp, firestore
from tests.test_cloud import FakeCloud, connection, deploy

PROJECT = "demo-proj-123"
ROOT = f"projects/{PROJECT}/databases/(default)/documents"


def _fail(message: str, code: str, status: int) -> CloudError:
    return CloudError(f"Google API error {status}: {message}", code=code, status=status)


class FakeFirestore(FakeCloud):
    """FakeCloud for the hosting calls, plus a small in-memory Firestore behind `firestore` that understands the
    REST paths and structuredQuery shapes services/firestore.py sends."""

    def __init__(self, **returns):
        super().__init__(**returns)
        self.docs: dict[str, dict] = {}  # "users/u1" -> {field: Firestore Value}
        self.fs_fail: dict[str, CloudError] = {}  # verb or method -> error
        self.databases = [
            {"name": f"projects/{PROJECT}/databases/(default)", "locationId": "nam5", "type": "FIRESTORE_NATIVE"},
            {"name": f"projects/{PROJECT}/databases/legacy", "locationId": "eur3", "type": "DATASTORE_MODE"},
        ]
        self.indexes = [
            {
                "name": f"projects/{PROJECT}/databases/(default)/collectionGroups/orders/indexes/CICAgOjXh4EK",
                "queryScope": "COLLECTION",
                "fields": [
                    {"fieldPath": "status", "order": "ASCENDING"},
                    {"fieldPath": "total", "order": "DESCENDING"},
                    {"fieldPath": "__name__", "order": "DESCENDING"},
                ],
            }
        ]

    def put(self, path: str, doc: dict) -> None:
        self.docs[path] = {k: firestore.to_value(v, ROOT) for k, v in doc.items()}

    def fs_calls(self) -> list[tuple]:
        return [c[1:] for c in self.calls if c[0] == "firestore"]

    # --- the REST surface ---------------------------------------------------------------------------

    def firestore(self, method, path, body=None, params=None):
        self.calls.append(("firestore", method, path, body, params))
        m = re.fullmatch(r"databases(?:/([^/:]+))?(/documents|/collectionGroups/-/indexes)?(/[^:]*)?(?::(\w+))?", path)
        assert m, path
        database, kind, tail, verb = m.groups()
        failure = self.fs_fail.get(verb or method)
        if failure:
            raise failure
        if database is None:
            return {"databases": self.databases}
        database = unquote(database)
        if kind is None:
            found = [d for d in self.databases if d["name"].endswith(f"/{database}")]
            if not found:
                raise _fail(f"Database {database} not found", "NOT_FOUND", 404)
            return found[0]
        if kind != "/documents":
            return {"indexes": self.indexes}
        assert database == "(default)"
        parts = [unquote(p) for p in (tail or "").strip("/").split("/") if p]
        params = dict(params or {}) if not isinstance(params, list) else params
        if verb == "runQuery":
            return [{"document": d} for d in self._query(parts, body["structuredQuery"])] or [{"readTime": "t"}]
        if verb == "runAggregationQuery":
            query = {**body["structuredAggregationQuery"]["structuredQuery"]}
            n = len(self._query(parts, query))
            return [{"result": {"aggregateFields": {"n": {"integerValue": str(n)}}}, "readTime": "t"}]
        if verb == "listCollectionIds":
            segs = [p.split("/") for p in self.docs]
            return {
                "collectionIds": sorted(
                    {s[len(parts)] for s in segs if len(s) > len(parts) and s[: len(parts)] == parts}
                )
            }
        key = "/".join(parts)
        if method == "POST":  # create
            doc_id = (params or {}).get("documentId") if isinstance(params, dict) else None
            doc_id = doc_id or f"auto{len(self.docs)}"
            if f"{key}/{doc_id}" in self.docs:
                raise _fail("Document already exists", "ALREADY_EXISTS", 409)
            self.docs[f"{key}/{doc_id}"] = dict(body["fields"])
            return self._doc(f"{key}/{doc_id}")
        if key not in self.docs:
            raise _fail(f"No document to {method.lower()}: {key}", "NOT_FOUND", 404)
        if method == "GET":
            return self._doc(key)
        if method == "DELETE":
            assert params == {"currentDocument.exists": "true"}
            del self.docs[key]
            return {}
        assert method == "PATCH" and ("currentDocument.exists", "true") in params
        for name, field in params:
            if name == "updateMask.fieldPaths":
                plain = field.strip("`").replace("\\`", "`")
                if plain in body["fields"]:
                    self.docs[key][plain] = body["fields"][plain]
                else:
                    self.docs[key].pop(plain, None)
        return self._doc(key)

    def _doc(self, path: str) -> dict:
        return {"name": f"{ROOT}/{path}", "fields": self.docs[path], "createTime": "t", "updateTime": "t"}

    def _get(self, path: str, field: str):
        if field == "__name__":
            return {"referenceValue": f"{ROOT}/{path}"}
        value = {"mapValue": {"fields": self.docs[path]}}
        for part in field.split("."):
            value = ((value.get("mapValue") or {}).get("fields") or {}).get(part.strip("`"))
            if value is None:
                return None
        return value

    def _matches(self, path: str, f: dict | None) -> bool:
        if not f:
            return True
        if "compositeFilter" in f:
            results = [self._matches(path, x) for x in f["compositeFilter"]["filters"]]
            return all(results) if f["compositeFilter"]["op"] == "AND" else any(results)
        if "unaryFilter" in f:
            value = self._get(path, f["unaryFilter"]["field"]["fieldPath"])
            is_null = value is None or "nullValue" in value
            return is_null if f["unaryFilter"]["op"] == "IS_NULL" else not is_null
        ff = f["fieldFilter"]
        value = self._get(path, ff["field"]["fieldPath"])
        if value is None:
            return False
        have, want = firestore.from_value(value, ROOT), firestore.from_value(ff["value"], ROOT)
        op = ff["op"]
        if op == "EQUAL":
            return have == want
        if op == "IN":
            return have in want
        if op == "ARRAY_CONTAINS":
            return isinstance(have, list) and want in have
        return {"GREATER_THAN": have > want, "LESS_THAN": have < want, "NOT_EQUAL": have != want}[op]

    def _query(self, parent: list[str], q: dict) -> list[dict]:
        (selector,) = q["from"]
        cid, deep = selector["collectionId"], selector.get("allDescendants", False)
        prefix = "/".join(parent)
        paths = []
        for p in self.docs:
            segs = p.split("/")
            if segs[-2] != cid or not p.startswith(f"{prefix}/" if prefix else ""):
                continue
            if deep or segs[:-2] == parent:
                paths.append(p)
        paths = sorted(p for p in paths if self._matches(p, q.get("where")))
        for order in reversed(q.get("orderBy") or []):
            field = order["field"]["fieldPath"]
            if field != "__name__":
                paths.sort(
                    key=lambda p, f=field: json.dumps(firestore.from_value(self._get(p, f) or {}, ROOT)),
                    reverse=order["direction"] == "DESCENDING",
                )
        if q.get("startAt"):
            after = q["startAt"]["values"][0]["referenceValue"].removeprefix(ROOT + "/")
            paths = [p for p in paths if p > after]
        paths = paths[q.get("offset", 0) :]
        if "limit" in q:
            paths = paths[: q["limit"]]
        out = []
        for p in paths:
            doc = self._doc(p)
            if q.get("select"):
                keep = {f["fieldPath"] for f in q["select"]["fields"]}
                doc = {**doc, "fields": {k: v for k, v in doc["fields"].items() if k in keep}}
            out.append(doc)
        return out


@pytest.fixture
def gcp(monkeypatch):
    fake = FakeFirestore(
        project_info={"projectId": PROJECT, "projectNumber": "123456789"},
        create_version=lambda site, config: f"sites/{site}/versions/v1",
        ensure_repository=f"us-central1-docker.pkg.dev/{PROJECT}/deployer",
        docker_login=("us-central1-docker.pkg.dev", "oauth2accesstoken", "ya29." + secrets.token_hex(16)),
        create_service=f"projects/{PROJECT}/locations/us-central1/operations/op1",
        update_service=f"projects/{PROJECT}/locations/us-central1/operations/op2",
        operation={"done": True, "error": None},
    )
    fake.put(
        "users/u1",
        {"name": "Ann", "age": 31, "address": {"city": "Oslo"}, "joined": {"$timestamp": "2026-01-02T03:04:05Z"}},
    )
    fake.put("users/u2", {"name": "Bo", "age": 25, "address": {"city": "Rome"}, "avatar": {"$base64": "aGk="}})
    fake.put("users/u3", {"name": "Cy", "age": 40, "tags": ["admin"], "boss": {"$ref": "users/u1"}})
    fake.put("users/u1/orders/o1", {"total": 12.5, "status": "open"})
    fake.put("users/u1/orders/o2", {"total": 3, "status": "paid"})
    fake.put("users/u2/orders/o9", {"total": 99, "status": "open"})
    fake.put("orders/x1", {"total": 7, "status": "open", "at": {"$geo": {"latitude": 1.5, "longitude": 2.5}}})
    cloud_gcp.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    yield fake
    cloud_gcp.set_factory(None)


def base(team):
    return f"/v1/projects/{team['project'].id}"


def connect(client, team, conn, name="App data", database=None):
    body = {"connection_id": conn.id, "name": name, **({"database": database} if database else {})}
    resp = client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    return resp.json()


def docs_url(team, source, collection):
    return f"{base(team)}/data-sources/{source['id']}/collections/{collection}/documents"


@pytest.fixture
def viewer(db, team, make_user, auth_headers):
    user = make_user()
    db.add(ProjectMember(project_id=team["project"].id, user_id=user.id, role="viewer"))
    db.commit()
    return auth_headers(user)


# --- values, paths -----------------------------------------------------------------------------------


def test_values_paths_and_field_names():
    doc = {
        "n": 1,
        "f": 1.5,
        "s": "x",
        "b": True,
        "z": None,
        "ts": {"$timestamp": "2026-01-01T00:00:00Z"},
        "bin": {"$base64": "aGk="},
        "ref": {"$ref": "users/u1"},
        "geo": {"$geo": {"latitude": 1.0, "longitude": 2.0}},
        "nested": {"list": [1, "a", {"deep": False}]},
    }
    raw = {k: firestore.to_value(v, ROOT) for k, v in doc.items()}
    assert raw["n"] == {"integerValue": "1"} and raw["f"] == {"doubleValue": 1.5}
    assert raw["ref"] == {"referenceValue": f"{ROOT}/users/u1"} and raw["z"] == {"nullValue": None}
    assert {k: firestore.from_value(v, ROOT) for k, v in raw.items()} == doc
    assert firestore.from_value({"doubleValue": "NaN"}, ROOT) == "NaN"  # not a JSON number
    schema = firestore.from_value(raw["ts"], ROOT, for_schema=True)
    assert schema.year == 2026 and firestore.from_value(raw["bin"], ROOT, for_schema=True) == b"hi"
    for bad in (float("inf"), 2**64, {"$base64": "%%"}, {"$ref": "users"}, {"$geo": {"latitude": "x"}}, object()):
        with pytest.raises(Exception):  # noqa: B017 - each is an ApiError with its own message
            firestore.to_value(bad, ROOT)
    assert firestore.check_path("users/u1/orders", "collection") == ["users", "u1", "orders"]
    for bad_path in ("users/u1", "", "a//b", "users/../x", 5):
        with pytest.raises(Exception, match="Not a Firestore"):
            firestore.check_path(bad_path, "collection")
    assert firestore.field_path("address.city") == "address.city"
    assert firestore.field_path("first name.x`y") == "`first name`.`x\\`y`"


# --- connect / remove ----------------------------------------------------------------------------------


def test_connect_lists_databases_and_never_deletes_them(client, db, team, gcp):
    conn = connection(db, "firebase")
    options = client.get(f"{base(team)}/cloud/databases/options", headers=team["dev"]).json()
    firebase = next(loc for loc in options["locations"] if loc["id"] == "firebase")
    assert firebase.get("available") is not False and firebase["only"] == "nosql"
    assert "collections" in options["firestore"]["what"] and "Datastore User" in options["firestore"]["network"]
    listing = client.get(f"{base(team)}/cloud/connections/{conn.id}/databases", headers=team["admin"]).json()
    assert listing["provider"] == "firebase" and listing["firestore_problem"] is None
    assert [(d["id"], bool(d["problem"])) for d in listing["firestore"]] == [("(default)", False), ("legacy", True)]

    body = {"connection_id": conn.id, "name": "X", "database": "missing-db"}
    missing = client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"])
    assert missing.status_code == 400 and "Firebase console" in missing.json()["error"]["message"]
    body["database"] = "legacy"
    datastore = client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"])
    assert datastore.status_code == 400 and "Datastore mode" in datastore.json()["error"]["message"]
    body["database"] = "Bad Name"
    assert client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"]).status_code == 422
    assert client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["dev"]).status_code == 403

    source = connect(client, team, conn)
    assert source["engine"] == "firestore" and source["kind"] == "nosql" and source["status"] == "ok"
    assert source["cloud"]["provider"] == "firebase" and source["cloud"]["service"] == "firestore"
    assert source["cloud"]["resource_id"] == "(default)" and source["cloud"]["resource_kind"] == "database"
    assert source["cloud"]["created"] is False and source["cloud"]["resources"] == []
    assert source["display"]["host"] == "firestore.googleapis.com"
    info = client.get(f"{base(team)}/data-sources/{source['id']}/connection", headers=team["dev"]).json()
    assert info["password"] is None and info["project_id"] == PROJECT and info["database"] == "(default)"
    checked = client.post(f"{base(team)}/data-sources/{source['id']}/check", headers=team["dev"]).json()
    assert checked["status"] == "ok"
    edit = client.patch(f"{base(team)}/data-sources/{source['id']}", json={"config": {"x": 1}}, headers=team["admin"])
    assert edit.status_code == 422
    audit = db.query(AuditLog).filter(AuditLog.action == "data_source.create").one()
    assert audit.details["cloud"] == "connect" and audit.details["engine"] == "firestore"
    # The Firebase project can't be removed while a database uses it; removing the source never deletes data.
    owner = team["owner"]
    assert client.delete(f"/v1/instance/cloud/{conn.id}", headers=owner).status_code == 409
    gcp.calls.clear()
    assert client.delete(f"{base(team)}/data-sources/{source['id']}", headers=team["admin"]).json() == {"ok": True}
    assert gcp.fs_calls() == [] and "users/u1" in gcp.docs


def test_listing_problem_still_lets_a_database_be_typed(client, db, team, gcp):
    conn = connection(db, "firebase")
    gcp.fs_fail["GET"] = _fail("The caller does not have permission", "PERMISSION_DENIED", 403)
    listing = client.get(f"{base(team)}/cloud/connections/{conn.id}/databases", headers=team["admin"]).json()
    assert listing["firestore"] == [] and "permission" in listing["firestore_problem"]


# --- data browser / data API ---------------------------------------------------------------------------


def test_browse_page_filter_and_subcollections(client, db, team, gcp, viewer):
    source = connect(client, team, connection(db, "firebase"))
    url = docs_url(team, source, "users")
    page = client.get(url, params={"limit": 2}, headers=viewer).json()
    assert page["total"] == 3 and [d["_id"] for d in page["documents"]] == ["u1", "u2"]
    assert page["documents"][0] == {
        "_id": "u1",
        "name": "Ann",
        "age": 31,
        "address": {"city": "Oslo"},
        "joined": {"$timestamp": "2026-01-02T03:04:05Z"},
    }
    rest = client.get(url, params={"limit": 2, "cursor": page["next_cursor"]}, headers=viewer).json()
    assert [d["_id"] for d in rest["documents"]] == ["u3"] and rest["next_cursor"] is None
    assert rest["documents"][0]["boss"] == {"$ref": "users/u1"}
    assert client.get(url, params={"cursor": "%%%"}, headers=viewer).status_code == 400
    # Equality filters: dotted names reach into maps, _id is the document id.
    by_city = client.get(url, params={"filter": '{"address.city": "Rome"}'}, headers=viewer).json()
    assert [d["_id"] for d in by_city["documents"]] == ["u2"] and by_city["total"] == 1
    by_id = client.get(url, params={"filter": '{"_id": "u3"}'}, headers=viewer).json()
    assert [d["name"] for d in by_id["documents"]] == ["Cy"]
    query = gcp.fs_calls()[-2][2]["structuredQuery"]
    assert query["where"]["fieldFilter"]["field"]["fieldPath"] == "__name__"
    assert query["orderBy"] == [{"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"}]
    # Subcollections are paths; a document lists its own.
    subs = client.get(f"{url}/u1/collections", headers=viewer).json()
    assert subs == {"collections": ["users/u1/orders"]}
    orders = client.get(docs_url(team, source, "users/u1/orders"), headers=viewer).json()
    assert [d["_id"] for d in orders["documents"]] == ["o1", "o2"] and orders["total"] == 2
    assert client.get(docs_url(team, source, "users/u1"), headers=viewer).status_code == 400  # a document path
    # The data API with an anon key reads; writes need developer+.
    key = client.post(f"{base(team)}/api-keys", json={"name": "k", "role": "anon"}, headers=team["admin"]).json()
    anon = {"Authorization": f"Bearer {key['secret']}"}
    assert client.get(docs_url(team, source, "orders"), headers=anon).json()["documents"][0]["_id"] == "x1"
    insert = {"document": {"total": 1}}
    assert client.post(docs_url(team, source, "orders"), json=insert, headers=anon).status_code == 403
    assert client.post(docs_url(team, source, "orders"), json=insert, headers=viewer).status_code == 403


def test_insert_update_delete_documents(client, db, team, gcp):
    source = connect(client, team, connection(db, "firebase"))
    url, dev = docs_url(team, source, "users/u2/orders"), team["dev"]
    created = client.post(
        url, json={"document": {"_id": "o10", "total": 5, "at": {"$timestamp": "2026-05-01T00:00:00Z"}}}, headers=dev
    )
    assert created.status_code == 200, created.text
    assert created.json()["document"] == {"_id": "o10", "total": 5, "at": {"$timestamp": "2026-05-01T00:00:00Z"}}
    assert gcp.docs["users/u2/orders/o10"]["total"] == {"integerValue": "5"}
    dup = client.post(url, json={"document": {"_id": "o10"}}, headers=dev)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "document_exists"
    auto = client.post(url, json={"document": {"total": 1}}, headers=dev).json()["document"]
    assert auto["_id"].startswith("auto")
    assert client.post(url, json={"document": {"_id": "a/b"}}, headers=dev).status_code == 400

    immutable = client.patch(f"{url}/o10", json={"set": {"_id": "x"}}, headers=dev)
    assert immutable.status_code == 400 and immutable.json()["error"]["code"] == "immutable_field"
    updated = client.patch(f"{url}/o10", json={"set": {"total": 6, "odd name": True}, "unset": ["at"]}, headers=dev)
    assert updated.json()["document"] == {"_id": "o10", "total": 6, "odd name": True}
    mask = [v for k, v in gcp.fs_calls()[-1][3] if k == "updateMask.fieldPaths"]
    assert mask == ["total", "`odd name`", "at"]
    gone = client.patch(f"{url}/nope", json={"set": {"a": 1}}, headers=dev)
    assert gone.status_code == 404 and gone.json()["error"]["code"] == "document_not_found"
    assert client.delete(f"{url}/o10", headers=dev).json() == {"ok": True}
    assert client.delete(f"{url}/o10", headers=dev).status_code == 404
    # Collections appear with their first document; none are created or dropped here.
    coll = f"{base(team)}/data-sources/{source['id']}/collections"
    refused = client.post(coll, json={"name": "more"}, headers=dev)
    assert refused.status_code == 400 and "first document" in refused.json()["error"]["message"]
    assert client.delete(f"{coll}/users", headers=team["admin"]).status_code == 400
    assert "users/u1" in gcp.docs


# --- query console, schema, export -----------------------------------------------------------------------


def test_query_console_json_requests(client, db, team, gcp, viewer):
    source = connect(client, team, connection(db, "firebase"))
    url = f"{base(team)}/data-sources/{source['id']}/query"

    def run(request, headers=viewer, max_rows=2):
        text = request if isinstance(request, str) else json.dumps(request)
        return client.post(url, json={"query": text, "max_rows": max_rows}, headers=headers)

    query = {
        "from": "users",
        "where": [{"field": "age", "op": ">", "value": 26}],
        "orderBy": [{"field": "age", "direction": "desc"}],
    }
    out = run(query).json()
    assert out["engine"] == "firestore" and out["error"] is None
    assert [d["name"] for d in out["result_docs"]] == ["Cy", "Ann"] and out["result_docs"][0]["_path"] == "users/u3"
    sent = gcp.fs_calls()[-1][2]["structuredQuery"]
    assert sent["where"]["fieldFilter"] == {
        "field": {"fieldPath": "age"},
        "op": "GREATER_THAN",
        "value": {"integerValue": "26"},
    }
    assert sent["orderBy"][0]["direction"] == "DESCENDING" and sent["limit"] == 3  # one more, to see truncation
    capped = run({"from": "users"}).json()
    assert len(capped["result_docs"]) == 2 and capped["truncated"] is True and "offset" in capped["output"]
    # Every collection named orders (a collection group), OR filters, unary filters, select.
    group = {
        "from": {"collectionId": "orders"},
        "where": {"or": [{"field": "status", "op": "==", "value": "open"}, {"field": "total", "op": "<", "value": 4}]},
        "select": ["total"],
    }
    found = run(group, max_rows=50).json()["result_docs"]
    assert sorted(d["_path"] for d in found) == [
        "orders/x1",
        "users/u1/orders/o1",
        "users/u1/orders/o2",
        "users/u2/orders/o9",
    ]
    assert all(set(d) == {"_id", "_path", "total"} for d in found)
    assert (
        run({"from": "users", "where": {"field": "tags", "op": "IS_NOT_NULL"}}, max_rows=50).json()["result_docs"][0][
            "_id"
        ]
        == "u3"
    )
    assert run({"operation": "count", "from": "users/u1/orders"}).json()["result"] == {"count": 2}
    got = run({"operation": "get", "path": "users/u2"}).json()
    assert got["result_docs"][0]["avatar"] == {"$base64": "aGk="}
    # Writes need developer+; viewers may only read.
    create = {"operation": "create", "collection": "users", "id": "u9", "data": {"name": "Di"}}
    refused = run(create)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "read_only_role"
    assert run(create, team["dev"]).json()["error"] is None and "users/u9" in gcp.docs
    assert (
        run({"operation": "update", "path": "users/u9", "data": {"age": 5}}, team["dev"]).json()["result_docs"][0][
            "age"
        ]
        == 5
    )
    assert run({"operation": "delete", "path": "users/u9"}, team["dev"]).json()["result"] == {"deleted": "users/u9"}
    # Mistakes come back in-band, like a MongoDB shell error.
    assert "JSON" in run("db.users.find()", team["dev"]).json()["error"]["message"]
    assert "must be one of" in run({"operation": "drop", "from": "users"}).json()["error"]["message"]
    assert "Unknown field 'wher'" in run({"from": "users", "wher": []}).json()["error"]["message"]
    assert '"from"' in run({"where": []}).json()["error"]["message"]
    assert (
        "Unknown op"
        in run({"from": "users", "where": {"field": "a", "op": "~", "value": 1}}).json()["error"]["message"]
    )
    gcp.fs_fail["runQuery"] = _fail(
        "The query requires an index. You can create it here: https://console.firebase.google.com/x",
        "FAILED_PRECONDITION",
        400,
    )
    assert "requires an index" in run(query).json()["error"]["message"]
    runs = client.get(f"{base(team)}/query-log", params={"source_id": source["id"]}, headers=team["dev"]).json()["runs"]
    assert any(r["status"] == "error" for r in runs) and any(r["status"] == "ok" for r in runs)


def test_schema_inference_and_exports(client, db, team, gcp):
    source = connect(client, team, connection(db, "firebase"))
    out = client.get(f"{base(team)}/schema", params={"source_id": source["id"]}, headers=team["dev"]).json()
    schema = out["sources"][0]
    assert schema["status"] == "ok", schema["error"]
    assert [e["name"] for e in schema["entities"]] == ["orders", "users"]  # top-level collections
    users = next(e for e in schema["entities"] if e["name"] == "users")
    by_name = {f["name"]: f for f in users["fields"]}
    assert users["fields"][0]["name"] == "_id" and by_name["_id"]["primary_key"] and by_name["_id"]["unique"]
    assert by_name["joined"]["data_type"] == "date" and by_name["avatar"]["data_type"] == "binData"
    assert by_name["address.city"]["data_type"] == "string" and by_name["boss"]["data_type"] == "string"
    assert by_name["age"]["indexed"] and users["row_count"] == 3
    orders = next(e for e in schema["entities"] if e["name"] == "orders")
    assert orders["indexes"][1] == {"name": "CICAgOjXh4EK", "fields": ["status", "total"], "unique": False}
    export = client.get(
        f"{base(team)}/schema/export", params={"format": "mongo", "source_id": source["id"]}, headers=team["dev"]
    )
    assert (
        export.status_code == 200
        and '"collectionGroup": "orders"' in export.text
        and "firestore:indexes" in export.text
    )

    url = f"{base(team)}/data-sources/{source['id']}/firestore/export"
    dumped = client.get(url, headers=team["dev"]).json()
    assert (
        dumped["documents"] == 4
        and dumped["truncated"] is False
        and sorted(dumped["collections"]) == ["orders", "users"]
    )
    assert dumped["collections"]["orders"][0]["at"] == {"$geo": {"latitude": 1.5, "longitude": 2.5}}
    some = client.get(url, params={"collection": ["users/u1/orders", "users"], "limit": 3}, headers=team["dev"]).json()
    assert some["documents"] == 3 and some["truncated"] is True and len(some["collections"]["users/u1/orders"]) == 2
    audit = db.query(AuditLog).filter(AuditLog.action == "data_source.export").first()
    assert audit is not None


# --- apps on Cloud Run ---------------------------------------------------------------------------------


def test_cloud_run_app_gets_its_firestore_database(client, db, docker, team, gcp):
    conn = connection(db, "firebase")
    connect(client, team, conn, name="App data")
    body = {"name": "Api", "repo_url": "https://github.com/acme/api", "preset": "node", "target": "firebase_app"}
    body |= {"cloud_connection_id": conn.id, "database_access": True, "confirm_billing": True}
    resp = client.post(f"{base(team)}/apps", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    app = db.get(App, resp.json()["id"])
    assert app.database_access is True
    dep = deploy(db, app)
    assert dep.status == "live", dep.error
    env = gcp.args("create_service")[0][3]
    assert env["DEPLOYER_DB_APP_DATA_PROJECT"] == PROJECT and env["DEPLOYER_DB_APP_DATA_DATABASE"] == "(default)"
    assert not any("PASSWORD" in k or "URL" in k for k in env if k.startswith("DEPLOYER_DB_"))
    assert "123456789-compute@developer.gserviceaccount.com" in dep.log and "Cloud Datastore User" in dep.log
    # Hosting-only Firebase targets still refuse database access.
    static = {"name": "Site", "repo_url": "https://github.com/acme/site", "preset": "static"}
    static |= {"target": "firebase_hosting", "cloud_connection_id": conn.id, "database_access": True}
    assert client.post(f"{base(team)}/apps", json=static, headers=team["admin"]).status_code == 422


def test_app_runner_app_does_not_get_firestore(client, db, team, gcp):
    """A Firestore database is in a Firebase project: an App Runner app (an AWS connection) never gets it."""
    from app.services import cloud_db

    connect(client, team, connection(db, "firebase"))
    aws_conn = connection(db)
    app = App(project_id=team["project"].id, target="aws_app", cloud_connection_id=aws_conn.id, database_access=True)
    databases, notes = cloud_db.app_databases(db, app)
    assert databases == [] and "another cloud account" in notes[0]


# --- MCP, roles, the real client -------------------------------------------------------------------------


def test_mcp_firestore_tools(client, db, team, gcp):
    key = client.post(f"{base(team)}/api-keys", json={"name": "k", "role": "service"}, headers=team["admin"])
    headers = {"Authorization": f"Bearer {key.json()['secret']}"}
    conn = connection(db, "firebase")

    def call(tool, auth=None, **arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        out = client.post(f"{base(team)}/mcp", json=body, headers=auth or headers).json()["result"]
        return out["isError"], json.loads(out["content"][0]["text"])

    def admin_call(tool, **arguments):  # the cloud account tools are admin-only, like their routes
        return call(tool, auth=team["admin"], **arguments)

    _, options = call("cloud_database_options")
    assert "Firestore" in options["firestore"]["what"]
    _, listed = admin_call("list_cloud_databases", connection_id=conn.id)
    assert listed["firestore"][0]["id"] == "(default)"
    err, source = admin_call("connect_cloud_database", connection_id=conn.id, name="Fire", database="(default)")
    assert not err and source["engine"] == "firestore"
    _, page = call("list_documents", source_id=source["id"], collection="users", limit=2)
    _, rest = call("list_documents", source_id=source["id"], collection="users", cursor=page["next_cursor"])
    assert len(page["documents"]) + len(rest["documents"]) == 3
    _, subs = call("list_subcollections", source_id=source["id"], collection="users", document_id="u1")
    assert subs["collections"] == ["users/u1/orders"]
    err, out = call("insert_document", source_id=source["id"], collection="users/u1/orders", document={"_id": "o3"})
    assert not err and out["document"]["_id"] == "o3"
    _, dumped = call("export_documents", source_id=source["id"], collections=["users/u1/orders"])
    assert [d["_id"] for d in dumped["collections"]["users/u1/orders"]] == ["o1", "o2", "o3"]
    err, out = call("run_query", source_id=source["id"], query='{"operation": "count", "from": "users"}')
    assert not err and out["result"] == {"count": 3}


def test_google_requirements_include_firestore():
    reqs = cloud.requirements()["firebase"]
    assert "roles/datastore.user" in {r["role"] for r in reqs["roles"]}
    assert "firestore.googleapis.com" in {a["api"] for a in reqs["apis"]}
    assert "firebase_app" in cloud.DATABASE_TARGETS and "firebase_hosting" not in cloud.DATABASE_TARGETS


def test_real_client_builds_firestore_urls_and_shares_tokens():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    config = {"service_account": {"client_email": "d@x", "private_key": pem}, "project_id": PROJECT}
    token = "ya29." + secrets.token_hex(8)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == cloud_gcp.TOKEN_URL:
            assert parse_qs(request.content.decode())["grant_type"]
            return httpx.Response(200, json={"access_token": token, "expires_in": 3600})
        assert request.headers["Authorization"] == f"Bearer {token}"
        if request.url.path.endswith(":runQuery"):
            return httpx.Response(400, json=[{"error": {"status": "FAILED_PRECONDITION", "message": "needs an index"}}])
        return httpx.Response(200, json={"name": "x"})

    cloud_gcp.set_transport(httpx.MockTransport(handle))
    try:
        ds = DataSource(engine="firestore", cloud_state={"database": "(default)", "project_id": PROJECT})
        path = firestore.url(ds, ["users", "a:b#c", "orders"], "")
        cloud_gcp.client(config).firestore("GET", path)
        assert seen[-1].url.raw_path.decode() == (
            f"/v1/projects/{PROJECT}/databases/(default)/documents/users/a%3Ab%23c/orders"
        )
        with pytest.raises(CloudError) as failed:
            cloud_gcp.client(config).firestore("POST", firestore.url(ds, [], "runQuery"), {"structuredQuery": {}})
        assert failed.value.code == "FAILED_PRECONDITION" and "needs an index" in failed.value.message
        with pytest.raises(CloudError, match="unexpected Firestore path"):
            cloud_gcp.client(config).firestore("GET", "../../v1/projects/other/secrets")
    finally:
        cloud_gcp.set_transport(None)
    # One token exchange for three clients of the same key.
    assert sum(str(r.url) == cloud_gcp.TOKEN_URL for r in seen) == 1
    assert all(r.url.host in ("oauth2.googleapis.com", "firestore.googleapis.com") for r in seen)
