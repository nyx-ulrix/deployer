"""DynamoDB engine, phase C2-2 (docs/CLOUD.md): tables created or connected as data sources, items in the
data browser / data API, the JSON query console, schema inference, on-demand backups, delete with a final
backup, App Runner apps reaching their tables through an instance role, and the MCP tools. DynamoDB is an
in-memory fake behind `AwsClient.ddb`; nothing here reaches AWS."""

import json
import re
import secrets
from decimal import Decimal

import pytest

from app.crypto import encrypt_json
from app.errors import CloudError
from app.models import App, AuditLog, DataSource, Job, ProjectMember
from app.services import cloud, cloud_db, cloud_deploy, dynamo, jobs
from tests.test_cloud import connection, deploy
from tests.test_cloud_db import KwFake


def _missing(what: str, code: str = "ResourceNotFoundException") -> CloudError:
    return CloudError(f"AWS {code}: {what}", code=code)


class FakeDynamo(KwFake):
    """KwFake for everything else, plus a small in-memory DynamoDB behind `ddb` that understands the
    expressions Deployer builds (`#f0 = :v0 AND ...`, `SET #s0 = :s0 REMOVE #r0`, attribute_(not_)exists)."""

    def __init__(self, **returns):
        super().__init__(**returns)
        self.tables: dict[str, dict] = {}
        self.items: dict[str, list[dict]] = {}
        self.backups: dict[str, dict] = {}
        self.ddb_fail: dict[str, CloudError] = {}

    def add_table(self, name, keys, items=(), gsi=None):
        desc = {
            "TableName": name,
            "TableStatus": "ACTIVE",
            "KeySchema": [
                {"AttributeName": n, "KeyType": t} for (n, _), t in zip(keys, ("HASH", "RANGE"), strict=False)
            ],
            "AttributeDefinitions": [{"AttributeName": n, "AttributeType": t} for n, t in keys],
        }
        if gsi:
            desc["GlobalSecondaryIndexes"] = [gsi]
        self.tables[name] = desc
        self.items[name] = [dynamo.serialize_item(i) for i in items]

    def ops(self) -> list[str]:
        return [c[1] for c in self.calls if c[0] == "ddb"]

    def params(self, op) -> list[dict]:
        return [c[2] for c in self.calls if c[0] == "ddb" and c[1] == op]

    def ddb(self, op, **p):
        self.calls.append(("ddb", op, p))
        if op in self.ddb_fail:
            raise self.ddb_fail[op]
        return getattr(self, "_" + op)(**p)

    # --- helpers -----------------------------------------------------------------------------------

    def _keys(self, table):
        return [k["AttributeName"] for k in self.tables[table]["KeySchema"]]

    def _find(self, table, key):
        return next((i for i in self.items[table] if all(i.get(k) == key[k] for k in self._keys(table))), None)

    def _check(self, expression, found, names):
        if not expression:
            return
        m = re.fullmatch(r"attribute_(not_)?exists\((#\w+)\)", expression)
        exists = found is not None and names[m.group(2)] in found
        if exists == bool(m.group(1)):
            raise _missing("The conditional request failed", "ConditionalCheckFailedException")

    @staticmethod
    def _matches(item, expression, names, values):
        for part in (expression or "").split(" AND ") if expression else []:
            name, value = (x.strip() for x in part.split("="))
            if item.get(names[name]) != values[value]:
                return False
        return True

    def _table(self, name):
        if name not in self.tables:
            raise _missing(f"Requested resource not found: Table: {name} not found")
        return self.tables[name]

    # --- operations ---------------------------------------------------------------------------------

    def _ListTables(self, **p):
        return {"TableNames": sorted(self.tables)}

    def _DescribeTable(self, TableName):
        desc = self._table(TableName)
        out = {
            **desc,
            "ItemCount": len(self.items[TableName]),
            "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
        }
        desc["TableStatus"] = "ACTIVE"  # a new table is ready on the second look
        return {"Table": out}

    def _CreateTable(self, TableName, KeySchema, AttributeDefinitions, DeletionProtectionEnabled=False, **p):
        if TableName in self.tables:
            raise _missing("Table already exists", "ResourceInUseException")
        self.tables[TableName] = {
            "TableName": TableName,
            "TableStatus": "CREATING",
            "KeySchema": KeySchema,
            "AttributeDefinitions": AttributeDefinitions,
            "DeletionProtectionEnabled": DeletionProtectionEnabled,
        }
        self.items[TableName] = []
        return {"TableDescription": self.tables[TableName]}

    def _UpdateTable(self, TableName, DeletionProtectionEnabled):
        desc = self._table(TableName)
        if desc.get("DeletionProtectionEnabled", False) == DeletionProtectionEnabled:  # be strict: no no-op updates
            raise _missing("Nothing to update", "ValidationException")
        desc["DeletionProtectionEnabled"] = DeletionProtectionEnabled
        return {}

    def _DeleteTable(self, TableName):
        if self._table(TableName).get("DeletionProtectionEnabled"):
            raise _missing("Deletion protection is on", "ValidationException")
        del self.tables[TableName], self.items[TableName]
        return {}

    def _PutItem(self, TableName, Item, ConditionExpression=None, ExpressionAttributeNames=None):
        self._table(TableName)
        found = self._find(TableName, Item)
        self._check(ConditionExpression, found, ExpressionAttributeNames or {})
        if found is not None:
            self.items[TableName].remove(found)
        self.items[TableName].append(Item)
        return {}

    def _GetItem(self, TableName, Key):
        found = self._find(TableName, Key)
        return {"Item": found} if found else {}

    def _DeleteItem(self, TableName, Key, ConditionExpression=None, ExpressionAttributeNames=None):
        found = self._find(TableName, Key)
        self._check(ConditionExpression, found, ExpressionAttributeNames or {})
        if found is not None:
            self.items[TableName].remove(found)
        return {}

    def _UpdateItem(self, TableName, Key, UpdateExpression, ExpressionAttributeNames, **p):
        found = self._find(TableName, Key)
        self._check(p.get("ConditionExpression"), found, ExpressionAttributeNames)
        values = p.get("ExpressionAttributeValues") or {}
        sets = re.search(r"SET (.*?)(?: REMOVE|$)", UpdateExpression)
        for part in sets.group(1).split(", ") if sets else []:
            name, value = (x.strip() for x in part.split("="))
            found[ExpressionAttributeNames[name]] = values[value]
        removes = re.search(r"REMOVE (.*)$", UpdateExpression)
        for name in removes.group(1).split(", ") if removes else []:
            found.pop(ExpressionAttributeNames[name], None)
        return {"Attributes": found}

    def _read(self, TableName, Limit, ExclusiveStartKey=None, **p):
        self._table(TableName)
        keys = self._keys(TableName)
        rows = sorted(self.items[TableName], key=lambda i: [json.dumps(i[k], default=str) for k in keys])
        names, values = p.get("ExpressionAttributeNames") or {}, p.get("ExpressionAttributeValues") or {}
        if ExclusiveStartKey:
            start = next(n for n, i in enumerate(rows) if all(i[k] == v for k, v in ExclusiveStartKey.items()))
            rows = rows[start + 1 :]
        rows = [i for i in rows if self._matches(i, p.get("KeyConditionExpression"), names, values)]
        evaluated, rest = rows[:Limit], rows[Limit:]
        out = [i for i in evaluated if self._matches(i, p.get("FilterExpression"), names, values)]
        page = {"Items": out, "Count": len(out), "ScannedCount": len(evaluated)}
        if rest:
            page["LastEvaluatedKey"] = {k: evaluated[-1][k] for k in self._keys(TableName)}
        return page

    _Scan = _Query = _read

    def _CreateBackup(self, TableName, BackupName):
        self._table(TableName)
        arn = f"arn:aws:dynamodb:eu-west-1:1:table/{TableName}/backup/{len(self.backups)}"
        details = {"BackupArn": arn, "BackupName": BackupName, "BackupStatus": "CREATING", "BackupSizeBytes": 10}
        self.backups[arn] = {**details, "TableName": TableName}
        return {"BackupDetails": details}

    def _DescribeBackup(self, BackupArn):
        self.backups[BackupArn]["BackupStatus"] = "AVAILABLE"
        return {"BackupDescription": {"BackupDetails": self.backups[BackupArn]}}

    def _ListBackups(self, TableName):
        return {"BackupSummaries": [b for b in self.backups.values() if b["TableName"] == TableName]}


ORDERS = [
    {"customer": "c1", "n": 1, "total": 12.5, "tags": {"$set": ["new", "gift"]}},
    {"customer": "c1", "n": 2, "total": 3, "photo": {"$base64": "aGk="}},
    {"customer": "c2", "n": 1, "total": 7, "status": "open"},
]


@pytest.fixture
def aws(monkeypatch):
    fake = FakeDynamo(
        identity={"account": "123456789012", "arn": "arn:aws:iam::123456789012:user/deployer"},
        public_ip="203.0.113.7",
        db_resources=[],
        ensure_repository=lambda name: f"123456789012.dkr.ecr.eu-west-1.amazonaws.com/{name}",
        registry_login=("123456789012.dkr.ecr.eu-west-1.amazonaws.com", "AWS", "ecr-pw"),
        ensure_access_role="arn:aws:iam::123456789012:role/deployer-apprunner-ecr-access",
        ensure_instance_role=lambda name, policy: f"arn:aws:iam::123456789012:role/{name}",
        create_service={"arn": "arn:svc", "url": "https://abc.eu-west-1.awsapprunner.com", "operation_id": "op1"},
        update_service="op2",
        operation="SUCCEEDED",
    )
    fake.add_table(
        "orders",
        [("customer", "S"), ("n", "N")],
        ORDERS,
        gsi={
            "IndexName": "by-status",
            "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
        },
    )
    fake.add_table("users", [("id", "S")], [{"id": "u1", "email": "a@example.com"}])
    fake.add_table("secrets-elsewhere", [("id", "S")], [{"id": "x"}])
    from app.services import cloud_aws

    cloud_aws.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_db, "POLL_S", 0)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    yield fake
    cloud_aws.set_factory(None)


def base(team):
    return f"/v1/projects/{team['project'].id}"


def connect(client, team, conn, tables=("orders", "users"), name="Shop data"):
    body = {"connection_id": conn.id, "name": name, "tables": list(tables)}
    resp = client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    return resp.json()


def docs_url(team, source, table):
    return f"{base(team)}/data-sources/{source['id']}/collections/{table}/documents"


@pytest.fixture
def viewer(db, team, make_user, auth_headers):
    user = make_user()
    db.add(ProjectMember(project_id=team["project"].id, user_id=user.id, role="viewer"))
    db.commit()
    return auth_headers(user)


# --- values ----------------------------------------------------------------------------------------


def test_values_round_trip():
    doc = {"n": 1, "f": 1.5, "s": "x", "b": True, "z": None, "bin": {"$base64": "aGk="}, "set": {"$set": [3, 1, 2]}}
    doc["nested"] = {"list": [1, "a", {"$set": ["b", "a"]}]}
    raw = dynamo.serialize_item(doc)
    assert raw["n"] == {"N": "1"} and raw["f"] == {"N": "1.5"} and sorted(raw["set"]["NS"]) == ["1", "2", "3"]
    out = dynamo.item_out(raw)
    assert out["set"] == {"$set": [1, 2, 3]} and out["nested"]["list"][2] == {"$set": ["a", "b"]}
    assert out == {**doc, "set": {"$set": [1, 2, 3]}, "nested": {"list": [1, "a", {"$set": ["a", "b"]}]}}
    with pytest.raises(Exception, match="non-empty"):
        dynamo.serialize({"$set": []})
    with pytest.raises(Exception, match="NaN"):
        dynamo.serialize(float("nan"))
    desc = {
        "KeySchema": [{"AttributeName": "n", "KeyType": "RANGE"}, {"AttributeName": "c", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "c", "AttributeType": "S"},
            {"AttributeName": "n", "AttributeType": "N"},
        ],
    }
    assert dynamo.key_names(desc) == ["c", "n"]
    assert dynamo.key_of(desc, '{"c": "a", "n": 2}') == {"c": {"S": "a"}, "n": {"N": "2"}}
    with pytest.raises(Exception, match="key as JSON"):
        dynamo.key_of(desc, "a")
    single = {
        "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "id", "AttributeType": "N"}],
    }
    assert dynamo.key_of(single, "42") == {"id": {"N": "42"}}
    assert dynamo.plain(Decimal("2.50")) == 2.5 and dynamo.plain(Decimal("3")) == 3


# --- create / connect / delete -------------------------------------------------------------------------


def test_create_table_needs_billing_confirmation_then_creates_it(client, db, team, aws):
    conn = connection(db)
    body = {"connection_id": conn.id, "name": "Events", "engine": "dynamodb", "confirm_billing": False}
    refused = client.post(f"{base(team)}/cloud/databases", json=body, headers=team["admin"])
    assert refused.status_code == 422 and "per million" in refused.json()["error"]["message"]
    assert client.post(f"{base(team)}/cloud/databases", json=body, headers=team["dev"]).status_code == 403
    body |= {"confirm_billing": True, "sort_key": {"name": "at", "type": "N"}}
    resp = client.post(f"{base(team)}/cloud/databases", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    source = resp.json()["data_source"]
    assert source["status"] == "creating" and source["engine"] == "dynamodb" and source["kind"] == "nosql"
    table = source["cloud"]["resource_id"]
    assert table.startswith("deployer-events-") and source["cloud"]["tables"] == [table]
    assert source["cloud"]["resources"] == [f"DynamoDB table {table} (deleted after a final backup)"]
    jobs.run_queued()
    db.expire_all()
    ds = db.get(DataSource, source["id"])
    assert db.get(Job, resp.json()["job"]["id"]).status == "succeeded" and ds.status == "ok"
    params = aws.params("CreateTable")[0]
    assert params["BillingMode"] == "PAY_PER_REQUEST" and params["DeletionProtectionEnabled"] is True
    assert params["KeySchema"] == [
        {"AttributeName": "id", "KeyType": "HASH"},
        {"AttributeName": "at", "KeyType": "RANGE"},
    ]
    assert params["AttributeDefinitions"][1] == {"AttributeName": "at", "AttributeType": "N"}
    assert params["Tags"] == [{"Key": "managed-by", "Value": "deployer"}]
    # No password anywhere: DynamoDB is reached with the AWS connection's key.
    info = client.get(f"{base(team)}/data-sources/{ds.id}/connection", headers=team["dev"]).json()
    assert info["password"] is None and info["tables"] == [table] and info["region"] == "eu-west-1"
    listed = client.get(f"{base(team)}/data-sources", headers=team["dev"]).json()
    assert listed[0]["display"]["host"] == "dynamodb.eu-west-1.amazonaws.com"
    audit = db.query(AuditLog).filter(AuditLog.action == "data_source.create").one()
    assert audit.details["cloud"] == "create" and audit.details["engine"] == "dynamodb"
    # No firewall to follow this PC's IP: the scheduler leaves DynamoDB alone.
    aws.calls.clear()
    assert cloud_db.refresh_pc_ips(jobs.get_sessionmaker(), force=True) == 0 and aws.calls == []


def test_delete_created_table_keeps_a_final_backup(client, db, team, aws):
    conn = connection(db)
    body = {"connection_id": conn.id, "name": "Events", "engine": "dynamodb", "confirm_billing": True}
    source = client.post(f"{base(team)}/cloud/databases", json=body, headers=team["admin"]).json()["data_source"]
    jobs.run_queued()
    table = source["cloud"]["resource_id"]
    project = team["project"]
    blocked = client.delete(f"/v1/projects/{project.id}?confirm={project.slug}", headers=team["owner"])
    assert blocked.status_code == 409  # never orphan a billed table
    aws.calls.clear()
    resp = client.delete(f"{base(team)}/data-sources/{source['id']}", headers=team["admin"])
    assert resp.json()["job"]["type"] == "data_source.cloud_delete"
    jobs.run_queued()
    job = db.get(Job, resp.json()["job"]["id"])
    assert job.status == "succeeded", job.error
    assert aws.ops() == ["DescribeTable", "UpdateTable", "CreateBackup", "DescribeBackup", "DeleteTable"]
    assert aws.params("UpdateTable")[0] == {"TableName": table, "DeletionProtectionEnabled": False}
    assert aws.params("CreateBackup")[0]["BackupName"].startswith(f"{table}-final-")
    assert table not in aws.tables and job.result["final_backups"]


def test_retried_delete_skips_the_protection_switch(db, team, aws):
    """A delete job that failed after switching deletion protection off (e.g. the backup timed out) can run
    again: it does not repeat the switch, and a table already gone counts as removed."""
    aws.add_table("deployer-gone-1", [("id", "S")])
    aws.tables["deployer-gone-1"]["DeletionProtectionEnabled"] = False
    out = cloud_db._delete_tables(
        type("Ctx", (), {"progress": lambda *a, **k: None})(), aws, {"tables": ["deployer-gone-1", "missing"]}
    )
    assert "UpdateTable" not in aws.ops() and "deployer-gone-1" not in aws.tables
    assert out["removed"] == ["DynamoDB table deployer-gone-1", "DynamoDB table missing"]


def test_connect_lists_tables_and_never_deletes_them(client, db, team, aws):
    conn = connection(db)
    listing = client.get(f"{base(team)}/cloud/connections/{conn.id}/databases", headers=team["admin"]).json()
    assert listing["tables"] == ["orders", "secrets-elsewhere", "users"] and listing["tables_problem"] is None
    bad = {"connection_id": conn.id, "name": "X", "tables": ["nope"]}
    failed = client.post(f"{base(team)}/cloud/databases/connect", json=bad, headers=team["admin"])
    assert failed.status_code == 400 and "nope" in failed.json()["error"]["message"]
    source = connect(client, team, conn)
    assert source["status"] == "ok" and source["status_message"] == "Connected (2 tables)"
    assert source["cloud"]["created"] is False and source["cloud"]["resources"] == []
    checked = client.post(f"{base(team)}/data-sources/{source['id']}/check", headers=team["dev"]).json()
    assert checked["status"] == "ok"
    edit = client.patch(f"{base(team)}/data-sources/{source['id']}", json={"config": {"x": 1}}, headers=team["admin"])
    assert edit.status_code == 422
    aws.calls.clear()
    assert client.delete(f"{base(team)}/data-sources/{source['id']}", headers=team["admin"]).json() == {"ok": True}
    assert aws.calls == [] and "orders" in aws.tables


# --- data browser / data API -------------------------------------------------------------------------


def test_browse_page_and_filter_items(client, db, team, aws, viewer):
    source = connect(client, team, connection(db))
    url = docs_url(team, source, "orders")
    page = client.get(url, params={"limit": 2}, headers=viewer).json()
    assert page["key"] == ["customer", "n"] and page["total"] == 3 and len(page["documents"]) == 2
    first = page["documents"][0]
    assert first == {"customer": "c1", "n": 1, "total": 12.5, "tags": {"$set": ["gift", "new"]}}
    rest = client.get(url, params={"limit": 2, "cursor": page["next_cursor"]}, headers=viewer).json()
    assert [d["customer"] for d in rest["documents"]] == ["c2"] and rest["next_cursor"] is None
    assert client.get(url, params={"cursor": "%%%"}, headers=viewer).status_code == 400
    # Naming the partition key reads just that partition (Query); anything else scans with a filter.
    aws.calls.clear()
    by_customer = client.get(url, params={"filter": '{"customer": "c1", "total": 3}'}, headers=viewer).json()
    assert [d["n"] for d in by_customer["documents"]] == [2] and by_customer["total"] is None
    query = aws.params("Query")[0]
    assert query["KeyConditionExpression"] == "#f0 = :v0" and query["FilterExpression"] == "#f1 = :v1"
    assert query["ExpressionAttributeValues"][":v0"] == {"S": "c1"}
    scanned = client.get(url, params={"filter": '{"status": "open"}', "limit": 1}, headers=viewer).json()
    assert [d["customer"] for d in scanned["documents"]] == ["c2"]  # read on past pages that matched nothing
    # Only the source's own tables, even ones in the same account.
    other = client.get(docs_url(team, source, "secrets-elsewhere"), headers=viewer)
    assert other.status_code == 404
    # The data API with an anon key reads; writes need developer+.
    key = client.post(f"{base(team)}/api-keys", json={"name": "k", "role": "anon"}, headers=team["admin"]).json()
    anon = {"Authorization": f"Bearer {key['secret']}"}
    assert client.get(docs_url(team, source, "users"), headers=anon).json()["documents"][0]["id"] == "u1"
    assert (
        client.post(docs_url(team, source, "users"), json={"document": {"id": "u2"}}, headers=anon).status_code == 403
    )
    assert (
        client.post(docs_url(team, source, "users"), json={"document": {"id": "u2"}}, headers=viewer).status_code == 403
    )


def test_insert_update_delete_items(client, db, team, aws):
    source = connect(client, team, connection(db))
    url, dev = docs_url(team, source, "orders"), team["dev"]
    missing = client.post(url, json={"document": {"customer": "c3"}}, headers=dev)
    assert missing.status_code == 400 and missing.json()["error"]["code"] == "missing_key"
    item = {"customer": "c3", "n": 1, "total": 9.99, "tags": {"$set": ["x"]}}
    created = client.post(url, json={"document": item}, headers=dev)
    assert created.status_code == 200 and created.json()["document"] == item
    dup = client.post(url, json={"document": item}, headers=dev)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "document_exists"

    doc_id = json.dumps({"customer": "c3", "n": 1})
    immutable = client.patch(f"{url}/{doc_id}", json={"set": {"n": 2}}, headers=dev)
    assert immutable.status_code == 400 and immutable.json()["error"]["code"] == "immutable_field"
    updated = client.patch(f"{url}/{doc_id}", json={"set": {"total": 10}, "unset": ["tags"]}, headers=dev).json()
    assert updated["document"] == {"customer": "c3", "n": 1, "total": 10}
    gone = client.patch(f"{url}/{json.dumps({'customer': 'zz', 'n': 1})}", json={"set": {"a": 1}}, headers=dev)
    assert gone.status_code == 404
    assert client.patch(f"{url}/c3", json={"set": {"a": 1}}, headers=dev).status_code == 400  # needs both keys
    assert client.delete(f"{url}/{doc_id}", headers=dev).json() == {"ok": True}
    assert client.delete(f"{url}/{doc_id}", headers=dev).status_code == 404
    # A partition-only table takes the plain key value as the id.
    users = docs_url(team, source, "users")
    assert client.patch(f"{users}/u1", json={"set": {"name": "Ann"}}, headers=dev).json()["document"]["name"] == "Ann"
    # Tables are managed in AWS, not here.
    coll = f"{base(team)}/data-sources/{source['id']}/collections"
    assert client.post(coll, json={"name": "more"}, headers=dev).status_code == 400
    assert client.delete(f"{coll}/orders", headers=team["admin"]).status_code == 400
    assert "orders" in aws.tables


# --- query console, schema, export -----------------------------------------------------------------------


def test_query_console_json_requests(client, db, team, aws, viewer):
    source = connect(client, team, connection(db))
    url = f"{base(team)}/data-sources/{source['id']}/query"

    def run(request, headers):
        text = request if isinstance(request, str) else json.dumps(request)
        return client.post(url, json={"query": text, "max_rows": 2}, headers=headers)

    query = {
        "operation": "Query",
        "TableName": "orders",
        "KeyConditionExpression": "#c = :c",
        "ExpressionAttributeNames": {"#c": "customer"},
        "ExpressionAttributeValues": {":c": "c1"},
    }
    out = run(query, viewer).json()
    assert out["engine"] == "dynamodb" and out["error"] is None
    assert [d["n"] for d in out["result_docs"]] == [1, 2] and out["result"]["Count"] == 2
    scan = run({"operation": "Scan", "TableName": "orders", "Limit": 50}, viewer).json()
    assert aws.params("Scan")[-1]["Limit"] == 2 and scan["truncated"] is True  # capped at max_rows
    assert "ExclusiveStartKey" in scan["output"] and scan["result"]["LastEvaluatedKey"]["customer"] == "c1"
    put = {"operation": "PutItem", "TableName": "users", "Item": {"id": "u9", "age": 30}}
    refused = run(put, viewer)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "read_only_role"
    assert run(put, team["dev"]).json()["error"] is None
    got = run({"operation": "GetItem", "TableName": "users", "Key": {"id": "u9"}}, viewer).json()
    assert got["result_docs"] == [{"id": "u9", "age": 30}]
    # Mistakes come back in-band, like a MongoDB shell error.
    assert "JSON" in run("db.users.find()", team["dev"]).json()["error"]["message"]
    assert (
        "must be one of"
        in run({"operation": "DeleteTable", "TableName": "users"}, team["dev"]).json()["error"]["message"]
    )
    other = run({"operation": "Scan", "TableName": "secrets-elsewhere"}, team["dev"]).json()
    assert "TableName must be one of" in other["error"]["message"]
    aws.ddb_fail["Query"] = CloudError(
        "AWS ValidationException: Query condition missed key schema element", code="ValidationException"
    )
    assert "ValidationException" in run(query, viewer).json()["error"]["message"]
    runs = client.get(f"{base(team)}/query-log", params={"source_id": source["id"]}, headers=team["dev"]).json()["runs"]
    assert runs and runs[0]["status"] == "error"


def test_schema_inference_and_export(client, db, team, aws):
    source = connect(client, team, connection(db))
    out = client.get(f"{base(team)}/schema", params={"source_id": source["id"]}, headers=team["dev"]).json()
    schema = out["sources"][0]
    assert schema["status"] == "ok", schema["error"]
    orders = next(e for e in schema["entities"] if e["name"] == "orders")
    assert [f["name"] for f in orders["fields"]][:2] == ["customer", "n"]
    by_name = {f["name"]: f for f in orders["fields"]}
    assert by_name["customer"]["primary_key"] and by_name["n"]["primary_key"] and not by_name["customer"]["unique"]
    assert by_name["total"]["data_type"] == "int|double"
    assert by_name["tags"]["data_type"].startswith("array") and by_name["photo"]["data_type"] == "binData"
    assert by_name["status"]["indexed"] and by_name["status"]["occurrence"] < 1
    assert orders["indexes"][1] == {"name": "by-status", "fields": ["status"], "unique": False}
    assert orders["row_count"] == 3
    assert not [c for c in out["conventions"] if c.get("entity") == "orders" and c["rule"] in ("N1", "N2")]
    export = client.get(
        f"{base(team)}/schema/export", params={"format": "mongo", "source_id": source["id"]}, headers=team["dev"]
    )
    assert export.status_code == 200 and '"TableName": "orders"' in export.text and "KeySchema" in export.text


# --- backups -----------------------------------------------------------------------------------------


def test_on_demand_backups(client, db, team, aws, viewer):
    source = connect(client, team, connection(db))
    url = f"{base(team)}/data-sources/{source['id']}/cloud-backups"
    assert client.get(url, headers=viewer).json()["backups"] == []
    assert client.post(url, json={"confirm_billing": True}, headers=team["dev"]).status_code == 403
    refused = client.post(url, json={"confirm_billing": False}, headers=team["admin"])
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "billing_not_confirmed"
    made = client.post(url, json={"confirm_billing": True, "table": "orders"}, headers=team["admin"])
    assert made.status_code == 201 and made.json()["backups"][0]["name"].startswith("orders-")
    assert (
        client.post(
            url, json={"confirm_billing": True, "table": "secrets-elsewhere"}, headers=team["admin"]
        ).status_code
        == 404
    )
    client.post(url, json={"confirm_billing": True}, headers=team["admin"])
    listed = client.get(url, headers=viewer).json()
    assert sorted(b["table"] for b in listed["backups"]) == ["orders", "orders", "users"]
    assert "Restore" in listed["restore"]
    audit = db.query(AuditLog).filter(AuditLog.action == "data_source.cloud_backup").first()
    assert audit.details["tables"] == ["orders"]


# --- apps ----------------------------------------------------------------------------------------------


def test_app_runner_app_gets_its_tables_through_an_instance_role(client, db, docker, team, aws):
    conn = connection(db)
    source = connect(client, team, conn)
    body = {"name": "Api", "repo_url": "https://github.com/acme/api", "preset": "node", "target": "aws_app"}
    body |= {"cloud_connection_id": conn.id, "database_access": True}
    resp = client.post(f"{base(team)}/apps", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    app = db.get(App, resp.json()["id"])
    dep = deploy(db, app)
    assert dep.status == "live", dep.error
    ((name, policy),) = aws.args("ensure_instance_role")
    assert name == cloud_deploy.instance_role_name(app) and name.startswith("deployer-app-")
    statement = policy["Statement"][0]
    assert statement["Resource"] == [
        "arn:aws:dynamodb:eu-west-1:1:table/orders",
        "arn:aws:dynamodb:eu-west-1:1:table/users",
        "arn:aws:dynamodb:eu-west-1:1:table/orders/index/*",
        "arn:aws:dynamodb:eu-west-1:1:table/users/index/*",
    ]
    assert "dynamodb:DeleteTable" not in statement["Action"] and "dynamodb:PutItem" in statement["Action"]
    ((*args, kwargs),) = aws.args("create_service")
    assert args[5] is None  # no VPC: DynamoDB is reached over AWS's own endpoint
    assert kwargs == {"instance_role_arn": f"arn:aws:iam::123456789012:role/{name}"}
    env = args[3]
    assert env["DEPLOYER_DB_SHOP_DATA_TABLE"] == "orders" and env["DEPLOYER_DB_SHOP_DATA_TABLES"] == "orders,users"
    assert env["DEPLOYER_DB_SHOP_DATA_REGION"] == "eu-west-1"
    assert not any("PASSWORD" in k or "URL" in k for k in env if k.startswith("DEPLOYER_DB_"))
    assert "deployer-app-" in dep.log

    # Database access off: the role stays but may use nothing.
    client.patch(f"{base(team)}/apps/{app.id}", json={"database_access": False}, headers=team["admin"])
    aws.calls.clear()
    db.expire_all()
    assert deploy(db, db.get(App, app.id)).status == "live"
    assert aws.args("ensure_instance_role") == [(name, None)]
    # Deleting the app removes the role too.
    db.expire_all()
    assert f"IAM role {name} (what the app may use)" in cloud_deploy.resources(
        "aws_app", db.get(App, app.id).cloud_state
    )
    aws.calls.clear()
    deleted = client.delete(f"{base(team)}/apps/{app.id}", headers=team["admin"])
    assert deleted.status_code == 200, deleted.text
    jobs.run_queued()
    assert aws.args("delete_instance_role") == [(name,)]
    assert source["id"]


def test_app_with_rds_and_dynamodb_gets_a_gateway_endpoint(client, db, docker, team, aws):
    conn = connection(db)
    connect(client, team, conn, tables=("users",), name="Users")
    rds = DataSource(
        project_id=team["project"].id,
        name="Main",
        kind="sql",
        engine="mysql",
        mode="external",
        database_name="main",
        config_encrypted=encrypt_json({"host": "h", "port": 3306, "password": secrets.token_urlsafe(16)}),
        status="ok",
        cloud_connection_id=conn.id,
        cloud_state={"provider": "aws", "service": "rds", "created": False, "instance_id": "m", "vpc_id": "vpc-1"},
    )
    db.add(rds)
    db.commit()
    aws.returns["ensure_vpc_connector"] = {"arn": "arn:connector", "group_id": "sg-conn"}
    body = {"name": "Api", "repo_url": "https://github.com/acme/api", "preset": "node", "target": "aws_app"}
    body |= {"cloud_connection_id": conn.id, "database_access": True}
    app = db.get(App, client.post(f"{base(team)}/apps", json=body, headers=team["admin"]).json()["id"])
    dep = deploy(db, app)
    assert dep.status == "live", dep.error
    assert aws.args("ensure_dynamodb_endpoint") == [("vpc-1",)] and "gateway endpoint" in dep.log


# --- MCP, policy ---------------------------------------------------------------------------------------


def test_mcp_dynamodb_tools(client, db, team, aws):
    key = client.post(f"{base(team)}/api-keys", json={"name": "k", "role": "service"}, headers=team["admin"])
    headers = {"Authorization": f"Bearer {key.json()['secret']}"}
    conn = connection(db)

    def call(tool, auth=None, **arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        out = client.post(f"{base(team)}/mcp", json=body, headers=auth or headers).json()["result"]
        return out["isError"], json.loads(out["content"][0]["text"])

    def admin_call(tool, **arguments):  # the cloud account tools are admin-only, like their routes
        return call(tool, auth=team["admin"], **arguments)

    _, options = call("cloud_database_options")
    assert "partition key" in options["dynamodb"]["keys"] and options["dynamodb"]["key_types"][0]["id"] == "S"
    _, listed = admin_call("list_cloud_databases", connection_id=conn.id)
    assert "orders" in listed["tables"]
    err, source = admin_call("connect_cloud_database", connection_id=conn.id, name="Shop", tables=["orders"])
    assert not err and source["engine"] == "dynamodb"
    _, page = call("list_documents", source_id=source["id"], collection="orders", limit=2)
    _, rest = call("list_documents", source_id=source["id"], collection="orders", cursor=page["next_cursor"])
    assert len(page["documents"]) + len(rest["documents"]) == 3
    err, out = admin_call("create_cloud_backup", source_id=source["id"], confirm_billing=False)
    assert err and out["error"]["code"] == "billing_not_confirmed"
    err, out = admin_call("create_cloud_backup", source_id=source["id"], confirm_billing=True)
    assert not err and out["backups"][0]["table"] == "orders"
    _, backups = call("list_cloud_backups", source_id=source["id"])
    assert len(backups["backups"]) == 1
    err, created = admin_call(
        "create_cloud_database",
        connection_id=conn.id,
        name="Events",
        engine="dynamodb",
        partition_key={"name": "pk", "type": "S"},
        confirm_billing=True,
    )
    assert not err and created["data_source"]["status"] == "creating"
    err, out = call("run_query", source_id=source["id"], query='{"operation": "Scan", "TableName": "orders"}')
    assert not err and len(out["result_docs"]) == 3


def test_policy_scopes_dynamodb():
    statements = {s["Sid"]: s for s in cloud.AWS_POLICY["Statement"]}
    # ListBackups has no resource-level permissions: scoped to a table ARN, AWS would always deny it.
    assert "dynamodb:ListBackups" in statements["DynamoDBList"]["Action"]
    assert statements["DynamoDBList"]["Resource"] == "*"
    assert statements["DynamoDBTables"]["Resource"] == "arn:aws:dynamodb:*:*:table/deployer-*"
    assert "dynamodb:DeleteTable" in statements["DynamoDBTables"]["Action"]
    assert not {"dynamodb:DeleteTable", "dynamodb:CreateTable"} & set(statements["DynamoDBData"]["Action"])
    assert statements["AppRunnerInstanceRoles"]["Resource"] == "arn:aws:iam::*:role/deployer-app-*"
    assert statements["DynamoDBEndpointTag"]["Condition"]["StringEquals"]["ec2:CreateAction"] == "CreateVpcEndpoint"
    # IAM's managed-policy limit is 6,144 characters, whitespace not counted.
    assert len(json.dumps(cloud.AWS_POLICY, separators=(",", ":"))) <= 6144
