"""DynamoDB point-in-time recovery and restores into a new table (docs/CLOUD.md "C2-2", "Point-in-time recovery
and restores"): the routes and MCP tools against the in-memory fake of tests/test_dynamo.py, and the real
AwsClient against botocore's DynamoDB model (Stubber), so a wrong operation or parameter name fails."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.crypto import encrypt_json
from app.errors import CloudError
from app.models import AuditLog, DataSource, Job
from app.services import cloud, cloud_aws, cloud_db, jobs
from tests.test_cloud import connection
from tests.test_dynamo import ORDERS, FakeDynamo, base, connect, docs_url

EARLIEST = datetime(2026, 9, 1, tzinfo=UTC)


class PitrFake(FakeDynamo):
    """FakeDynamo plus continuous backups and restores (a restore copies the items when it is asked for and
    finishes on the next DescribeTable)."""

    def __init__(self, **returns):
        super().__init__(**returns)
        self.pitr: set[str] = set()
        self.snapshots: dict[str, list] = {}  # backup arn -> the items when it was made

    def _DescribeTable(self, TableName):
        out = super()._DescribeTable(TableName)
        out["Table"]["TableArn"] = f"arn:aws:dynamodb:eu-west-1:1:table/{TableName}"
        return out

    def _CreateBackup(self, TableName, BackupName):
        out = super()._CreateBackup(TableName, BackupName)
        self.snapshots[out["BackupDetails"]["BackupArn"]] = list(self.items[TableName])
        return out

    def _DescribeBackup(self, BackupArn):
        out = super()._DescribeBackup(BackupArn)
        out["BackupDescription"]["SourceTableDetails"] = {"TableName": self.backups[BackupArn]["TableName"]}
        return out

    def _continuous(self, table):
        on = table in self.pitr
        pitr = {"PointInTimeRecoveryStatus": "ENABLED" if on else "DISABLED"}
        if on:
            pitr |= {
                "EarliestRestorableDateTime": EARLIEST,
                "LatestRestorableDateTime": datetime.now(UTC) - timedelta(minutes=5),
                "RecoveryPeriodInDays": 35,
            }
        return {
            "ContinuousBackupsDescription": {
                "ContinuousBackupsStatus": "ENABLED",
                "PointInTimeRecoveryDescription": pitr,
            }
        }

    def _DescribeContinuousBackups(self, TableName):
        self._table(TableName)
        return self._continuous(TableName)

    def _UpdateContinuousBackups(self, TableName, PointInTimeRecoverySpecification):
        self._table(TableName)
        (self.pitr.add if PointInTimeRecoverySpecification["PointInTimeRecoveryEnabled"] else self.pitr.discard)(
            TableName
        )
        return self._continuous(TableName)

    def _restore(self, source, target, items):
        if target in self.tables:
            raise CloudError("Table already exists", code="TableAlreadyExistsException")
        self.tables[target] = {**self.tables[source], "TableName": target, "TableStatus": "CREATING"}
        self.tables[target].pop("DeletionProtectionEnabled", None)
        self.items[target] = list(items)
        return {"TableDescription": self.tables[target]}

    def _RestoreTableFromBackup(self, TargetTableName, BackupArn, BillingModeOverride):
        return self._restore(self.backups[BackupArn]["TableName"], TargetTableName, self.snapshots[BackupArn])

    def _RestoreTableToPointInTime(self, TargetTableName, SourceTableName, BillingModeOverride, **when):
        return self._restore(SourceTableName, TargetTableName, self.items[SourceTableName])

    def _TagResource(self, ResourceArn, Tags):
        return {}


@pytest.fixture
def aws(monkeypatch):
    fake = PitrFake(identity={"account": "1", "arn": "arn:aws:iam::1:user/deployer"})
    fake.add_table("orders", [("customer", "S"), ("n", "N")], ORDERS)
    fake.add_table("users", [("id", "S")], [{"id": "u1"}])
    fake.add_table("secrets-elsewhere", [("id", "S")], [{"id": "x"}])
    cloud_aws.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_db, "POLL_S", 0)
    yield fake
    cloud_aws.set_factory(None)


def urls(team, source):
    root = f"{base(team)}/data-sources/{source['id']}/cloud-backups"
    return root, f"{root}/pitr", f"{root}/restore"


def test_point_in_time_recovery_on_and_off(client, db, team, aws):
    source = connect(client, team, connection(db))
    backups, pitr, _ = urls(team, source)
    listed = client.get(backups, headers=team["dev"]).json()
    assert [(p["table"], p["status"]) for p in listed["pitr"]] == [("orders", "DISABLED"), ("users", "DISABLED")]
    assert "US$0.20 per GB" in listed["pitr_cost"] and "new table" in listed["restore"]
    body = {"table": "orders", "enabled": True}
    assert client.put(pitr, json=body | {"confirm_billing": True}, headers=team["dev"]).status_code == 403
    refused = client.put(pitr, json=body, headers=team["admin"])
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "billing_not_confirmed"
    other = client.put(
        pitr, json={**body, "table": "secrets-elsewhere", "confirm_billing": True}, headers=team["admin"]
    )
    assert other.status_code == 404  # a source only reaches its own tables
    on = client.put(pitr, json=body | {"confirm_billing": True}, headers=team["admin"]).json()
    assert on["status"] == "ENABLED" and on["earliest"] == "2026-09-01T00:00:00Z" and on["latest"] and on["days"] == 35
    assert aws.params("UpdateContinuousBackups")[-1] == {
        "TableName": "orders",
        "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
    }
    off = client.put(pitr, json={"table": "orders", "enabled": False}, headers=team["admin"])  # no billing tick
    assert off.status_code == 200 and off.json()["status"] == "DISABLED"
    audits = db.query(AuditLog).filter(AuditLog.action == "data_source.cloud_pitr").all()
    assert [(a.details["table"], a.details["enabled"]) for a in audits] == [("orders", True), ("orders", False)]
    # An older policy without DescribeContinuousBackups: the backups still list, the table says why.
    aws.ddb_fail["DescribeContinuousBackups"] = CloudError("not authorized", code="AccessDeniedException")
    listed = client.get(backups, headers=team["dev"]).json()
    assert listed["pitr"][0]["status"] is None and "not authorized" in listed["pitr"][0]["problem"]


def test_restore_a_backup_into_a_new_database(client, db, team, aws):
    source = connect(client, team, connection(db))
    backups, _, restore = urls(team, source)
    arn = client.post(backups, json={"confirm_billing": True, "table": "orders"}, headers=team["admin"]).json()[
        "backups"
    ][0]["arn"]
    aws.items["orders"].append(aws.items["orders"][0] | {"n": {"N": "9"}})  # changed after the backup
    body = {"name": "Orders before", "backup_arn": arn}
    refused = client.post(restore, json=body, headers=team["admin"])
    assert refused.status_code == 422 and "US$0.15 per GB restored" in refused.json()["error"]["message"]
    assert client.post(restore, json=body | {"confirm_billing": True}, headers=team["dev"]).status_code == 403
    both = client.post(restore, json=body | {"table": "orders", "confirm_billing": True}, headers=team["admin"])
    assert both.status_code == 422
    elsewhere = aws._CreateBackup("secrets-elsewhere", "x")["BackupDetails"]["BackupArn"]
    foreign = client.post(
        restore, json=body | {"backup_arn": elsewhere, "confirm_billing": True}, headers=team["admin"]
    )
    assert foreign.status_code == 404  # never another table's backup through this source
    taken = client.post(restore, json=body | {"name": "Shop data", "confirm_billing": True}, headers=team["admin"])
    assert taken.status_code == 409  # the data source name is in use

    resp = client.post(restore, json=body | {"confirm_billing": True}, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    new, job = resp.json()["data_source"], resp.json()["job"]
    table = new["cloud"]["resource_id"]
    assert job["type"] == "data_source.cloud_restore" and new["status"] == "creating"
    assert table.startswith("deployer-orders-before-") and new["cloud"]["created"] is True
    assert new["cloud"]["restored_from"]["backup_arn"] == arn and new["cloud"]["restored_from"]["table"] == "orders"
    jobs.run_queued()
    db.expire_all()
    assert db.get(Job, job["id"]).status == "succeeded" and db.get(DataSource, new["id"]).status == "ok"
    params = aws.params("RestoreTableFromBackup")[0]
    assert params == {"TargetTableName": table, "BackupArn": arn, "BillingModeOverride": "PAY_PER_REQUEST"}
    assert aws.params("TagResource")[0]["Tags"] == [cloud_aws.TAG]
    assert aws.params("UpdateTable")[-1] == {"TableName": table, "DeletionProtectionEnabled": True}
    # The copy has the backup's items; the original keeps its own (it was never touched).
    docs = client.get(docs_url(team, new, table), headers=team["dev"]).json()["documents"]
    assert len(docs) == 3 and len(aws.items["orders"]) == 4
    assert "DeleteTable" not in aws.ops()
    audit = db.query(AuditLog).filter(AuditLog.action == "data_source.create").all()[-1]
    assert audit.details["cloud"] == "restore"
    # Removing the copy deletes only the new table, after a final backup.
    aws.calls.clear()
    out = client.delete(f"{base(team)}/data-sources/{new['id']}", headers=team["admin"]).json()
    jobs.run_queued()
    assert db.get(Job, out["job"]["id"]).status == "succeeded"
    assert table not in aws.tables and "orders" in aws.tables


def test_restore_to_a_point_in_time(client, db, team, aws):
    source = connect(client, team, connection(db), tables=("orders",))
    _, pitr, restore = urls(team, source)
    body = {"name": "Orders at noon", "table": "orders", "confirm_billing": True}
    off = client.post(restore, json=body | {"latest": True}, headers=team["admin"])
    assert off.status_code == 409 and off.json()["error"]["code"] == "pitr_not_enabled"
    client.put(pitr, json={"table": "orders", "enabled": True, "confirm_billing": True}, headers=team["admin"])
    assert client.post(restore, json=body, headers=team["admin"]).status_code == 422  # a time or latest
    early = client.post(restore, json=body | {"point_in_time": "2026-08-01T00:00:00Z"}, headers=team["admin"])
    assert early.status_code == 400 and early.json()["error"]["code"] == "invalid_restore_time"
    resp = client.post(restore, json=body | {"point_in_time": "2026-09-02T12:00:00"}, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    latest = client.post(restore, json=body | {"name": "Orders now", "latest": True}, headers=team["admin"])
    assert latest.status_code == 201
    jobs.run_queued()
    first, second = aws.params("RestoreTableToPointInTime")
    assert first["SourceTableName"] == "orders" and first["BillingModeOverride"] == "PAY_PER_REQUEST"
    assert first["RestoreDateTime"] == datetime(2026, 9, 2, 12, tzinfo=UTC)  # no zone: UTC
    assert second["UseLatestRestorableTime"] is True and "RestoreDateTime" not in second
    assert first["TargetTableName"] != second["TargetTableName"] != "orders"
    for r in (resp, latest):
        assert db.get(DataSource, r.json()["data_source"]["id"]).status == "ok"


def orders_source(db, team) -> DataSource:
    """A connected DynamoDB source of the table `orders`, made directly (no AWS call)."""
    src = DataSource(
        project_id=team["project"].id,
        name="Shop",
        kind="nosql",
        engine="dynamodb",
        mode="external",
        database_name="orders",
        config_encrypted=encrypt_json({}),
        status="ok",
        cloud_connection_id=connection(db).id,
        cloud_state={"provider": "aws", "service": "dynamodb", "tables": ["orders"], "region": "eu-west-1"},
    )
    db.add(src)
    db.commit()
    return src


def test_retried_restore_never_asks_twice(db, team, aws):
    """A job interrupted after AWS accepted the restore finds the table already there and just waits."""
    src = orders_source(db, team)
    spec = {"kind": "point_in_time", "table": "orders", "latest": True}
    ds, job = cloud_db.restore_table(db, team["project"].id, src, name="copy", spec=spec, user_id=None)
    db.commit()
    aws._restore("orders", ds.database_name, [])  # the first attempt got this far
    jobs.run_queued()
    db.expire_all()
    assert db.get(Job, job.id).status == "succeeded" and len(aws.params("RestoreTableToPointInTime")) == 1


def test_mcp_restore_tools(client, db, team, aws):
    source = connect(client, team, connection(db), tables=("orders",))
    key = client.post(f"{base(team)}/api-keys", json={"name": "k", "role": "service"}, headers=team["admin"])

    def call(tool, headers, **arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        return client.post(f"{base(team)}/mcp", json=body, headers=headers).json()

    service = {"Authorization": f"Bearer {key.json()['secret']}"}
    assert "Unknown tool" in call("restore_cloud_backup", service, source_id=source["id"])["error"]["message"]
    out = call("set_point_in_time_recovery", team["admin"], source_id=source["id"], table="orders", enabled=True)
    assert out["result"]["isError"] and "billing_not_confirmed" in out["result"]["content"][0]["text"]
    args = {"source_id": source["id"], "table": "orders", "enabled": True, "confirm_billing": True}
    out = json.loads(call("set_point_in_time_recovery", team["admin"], **args)["result"]["content"][0]["text"])
    assert out["status"] == "ENABLED"
    out = call(
        "restore_cloud_backup",
        team["admin"],
        source_id=source["id"],
        name="Copy",
        table="orders",
        latest=True,
        confirm_billing=True,
    )
    created = json.loads(out["result"]["content"][0]["text"])
    assert created["data_source"]["status"] == "creating" and created["job"]["type"] == "data_source.cloud_restore"


def test_policy_allows_restores_into_deployer_tables_only():
    statements = {s["Sid"]: s for s in cloud.AWS_POLICY["Statement"]}
    data = set(statements["DynamoDBData"]["Action"])
    assert {"dynamodb:UpdateContinuousBackups", "dynamodb:RestoreTableFromBackup"} <= data
    # The restore writes the copied items: only ever into a deployer-* table.
    assert "dynamodb:BatchWriteItem" in statements["DynamoDBTables"]["Action"]
    assert "dynamodb:BatchWriteItem" not in data
    assert len(json.dumps(cloud.AWS_POLICY, separators=(",", ":"))) <= 6144


def test_restore_flow_against_the_real_botocore_model(client, db, team):
    """The real AwsClient.ddb with a Stubber on the dynamodb client: botocore validates every request against
    the service model (a wrong operation or parameter name fails) and every canned response too."""
    from botocore.stub import ANY, Stubber

    real = cloud_aws.AwsClient({"region": "eu-west-1", "access_key_id": "test", "secret_access_key": "test"})
    ddb = real._session.client("dynamodb", region_name="eu-west-1")
    real._c = lambda service, region=None: ddb
    cloud_aws.set_factory(lambda config: real)
    src = orders_source(db, team)
    root = f"{base(team)}/data-sources/{src.id}/cloud-backups"
    arn = "arn:aws:dynamodb:eu-west-1:123456789012:table/orders/backup/01700000000000-abcdef12"
    window = {
        "PointInTimeRecoveryStatus": "ENABLED",
        "EarliestRestorableDateTime": EARLIEST,
        "LatestRestorableDateTime": datetime.now(UTC),
    }
    continuous = {
        "ContinuousBackupsDescription": {"ContinuousBackupsStatus": "ENABLED", "PointInTimeRecoveryDescription": window}
    }

    def table(name, status="ACTIVE"):
        return {
            "Table": {
                "TableName": name,
                "TableStatus": status,
                "TableArn": f"arn:aws:dynamodb:eu-west-1:1:table/{name}",
            }
        }

    try:
        with Stubber(ddb) as stub:
            stub.add_response("list_backups", {"BackupSummaries": []}, {"TableName": "orders"})
            stub.add_response("describe_continuous_backups", continuous, {"TableName": "orders"})
            stub.add_response(
                "update_continuous_backups",
                continuous,
                {"TableName": "orders", "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True}},
            )
            stub.add_response(
                "describe_backup",
                {
                    "BackupDescription": {
                        "BackupDetails": {
                            "BackupArn": arn,
                            "BackupName": "orders-1",
                            "BackupStatus": "AVAILABLE",
                            "BackupType": "USER",
                            "BackupCreationDateTime": EARLIEST,
                        },
                        "SourceTableDetails": {
                            "TableName": "orders",
                            "TableId": "11111111-2222-3333-4444-555555555555",
                            "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}],
                            "TableCreationDateTime": EARLIEST,
                            "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
                        },
                    }
                },
                {"BackupArn": arn},
            )
            target = {"TargetTableName": ANY, "BillingModeOverride": "PAY_PER_REQUEST"}
            stub.add_response("restore_table_from_backup", {"TableDescription": {}}, {**target, "BackupArn": arn})
            stub.add_response("describe_table", table("deployer-copy", "CREATING"), {"TableName": ANY})
            stub.add_response("describe_table", table("deployer-copy"), {"TableName": ANY})
            stub.add_response("tag_resource", {}, {"ResourceArn": ANY, "Tags": [cloud_aws.TAG]})
            stub.add_response("update_table", {}, {"TableName": ANY, "DeletionProtectionEnabled": True})
            stub.add_response("describe_continuous_backups", continuous, {"TableName": "orders"})
            stub.add_response(
                "restore_table_to_point_in_time",
                {"TableDescription": {}},
                {**target, "SourceTableName": "orders", "RestoreDateTime": datetime(2026, 9, 2, tzinfo=UTC)},
            )
            stub.add_response("describe_table", table("deployer-copy"), {"TableName": ANY})
            stub.add_response("tag_resource", {}, {"ResourceArn": ANY, "Tags": [cloud_aws.TAG]})
            stub.add_response("update_table", {}, {"TableName": ANY, "DeletionProtectionEnabled": True})

            assert client.get(root, headers=team["dev"]).json()["pitr"][0]["status"] == "ENABLED"
            body = {"table": "orders", "enabled": True, "confirm_billing": True}
            assert client.put(f"{root}/pitr", json=body, headers=team["admin"]).status_code == 200
            body = {"name": "From backup", "backup_arn": arn, "confirm_billing": True}
            assert client.post(f"{root}/restore", json=body, headers=team["admin"]).status_code == 201
            jobs.run_queued()
            body = {
                "name": "At a time",
                "table": "orders",
                "point_in_time": "2026-09-02T00:00:00Z",
                "confirm_billing": True,
            }
            assert client.post(f"{root}/restore", json=body, headers=team["admin"]).status_code == 201
            jobs.run_queued()
            stub.assert_no_pending_responses()
    finally:
        cloud_aws.set_factory(None)
    statuses = [j.status for j in db.query(Job).filter(Job.type == "data_source.cloud_restore")]
    assert statuses == ["succeeded", "succeeded"]
