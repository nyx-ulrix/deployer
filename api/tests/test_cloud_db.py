"""Cloud databases phase C2-1 (docs/CLOUD.md): AWS RDS created or connected as data sources, the
firewall that follows this PC's IP, delete with a final snapshot, App Runner apps getting the database
through cloud_deploy.cloud_env + a VPC connector, MCP tools and migration 0013. AWS is faked; nothing
here reaches a real cloud."""

import json
import sqlite3

import pytest
from alembic import command
from sqlalchemy import select

from app.crypto import decrypt_json
from app.errors import CloudError
from app.models import App, AuditLog, DataSource, Job
from app.services import alerts, cloud, cloud_db, cloud_deploy, connections, jobs
from tests.apps_support import make_app
from tests.test_cloud import FakeCloud, connection, deploy

PC_IP = "203.0.113.7"
HOST = "deployer-shop-db.abc123.eu-west-1.rds.amazonaws.com"


class KwFake(FakeCloud):
    """FakeCloud that also keeps keyword arguments (as a trailing dict) for the firewall calls."""

    def __getattr__(self, name):
        call = super().__getattr__(name)

        def with_kwargs(*args, **kwargs):
            result = call(*args)
            if kwargs:
                self.calls[-1] = (*self.calls[-1], kwargs)
            return result

        return with_kwargs


@pytest.fixture
def aws(monkeypatch):
    status = iter(["creating", "backing-up"])
    fake = KwFake(
        identity={"account": "123456789012", "arn": "arn:aws:iam::123456789012:user/deployer"},
        public_ip=PC_IP,
        default_vpc="vpc-0a1b2c3d",
        ensure_security_group=lambda name, vpc, description: "sg-db1" if name.startswith("deployer-db-") else "sg-x",
        db_instance=lambda instance: {"status": next(status, "available"), "host": HOST, "port": 3306},
        ensure_vpc_connector={"arn": "arn:aws:apprunner:eu-west-1:1:vpcconnector/deployer-vpc", "group_id": "sg-conn"},
        ensure_repository=lambda name: f"123456789012.dkr.ecr.eu-west-1.amazonaws.com/{name}",
        registry_login=("123456789012.dkr.ecr.eu-west-1.amazonaws.com", "AWS", "ecr-pw"),
        ensure_boundary={"arn": "arn:aws:iam::123456789012:policy/deployer-boundary", "current": True},
        ensure_access_role="arn:aws:iam::123456789012:role/deployer-apprunner-ecr-access",
        create_service={"arn": "arn:svc", "url": "https://abc.eu-west-1.awsapprunner.com", "operation_id": "op1"},
        operation="SUCCEEDED",
        delete_db_instance=True,
        ddb=lambda operation: {"TableNames": []},
        db_resources=[
            {
                "id": "shop-prod",
                "kind": "instance",
                "engine": "postgres",
                "status": "available",
                "host": "shop-prod.abc.eu-west-1.rds.amazonaws.com",
                "port": 5432,
                "public": True,
                "vpc_id": "vpc-9",
                "security_groups": ["sg-theirs"],
                "database": "shop",
                "username": "admin",
            },
            {"id": "legacy", "kind": "instance", "engine": "oracle-ee", "public": True, "host": "h", "port": 1521},
            {"id": "private", "kind": "cluster", "engine": "aurora-mysql", "public": False, "host": "p", "port": 3306},
        ],
    )
    from app.services import cloud_aws

    cloud_aws.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_db, "POLL_S", 0)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    tls = []
    monkeypatch.setattr(cloud_db, "_require_tls", lambda engine, config: tls.append((engine, config["host"])))
    fake.tls = tls
    fake.tested = []

    def try_config(kind, engine, config):
        fake.tested.append((engine, dict(config)))
        return (True, "Connected", "8.0.39") if fake.returns.get("reachable", True) else (False, "timed out", None)

    monkeypatch.setattr(connections, "try_config", try_config)
    yield fake
    cloud_aws.set_factory(None)


def base(team):
    return f"/v1/projects/{team['project'].id}"


def create(client, team, conn, headers=None, **extra):
    body = {"connection_id": conn.id, "name": "Shop DB", "engine": "mysql", "confirm_billing": True, **extra}
    return client.post(f"{base(team)}/cloud/databases", json=body, headers=headers or team["admin"])


def test_create_needs_admin_and_billing_confirmation_then_builds_the_instance(client, db, team, aws):
    conn = connection(db)
    assert create(client, team, conn, team["dev"]).status_code == 403
    refused = create(client, team, conn, confirm_billing=False)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "billing_not_confirmed"
    assert "US$" in refused.json()["error"]["message"]
    assert create(client, team, conn, engine="oracle").status_code == 422
    assert aws.calls == []

    resp = create(client, team, conn)
    assert resp.status_code == 201, resp.text
    out = resp.json()
    source, job_id = out["data_source"], out["job"]["id"]
    assert source["status"] == "creating" and source["mode"] == "external" and source["engine"] == "mysql"
    assert source["cloud"]["created"] is True and source["cloud"]["resource_id"].startswith("deployer-shop-db-")
    assert source["cloud"]["job_id"] == job_id and source["database_name"] == "shopdb"
    # Nothing reaches the half-made database meanwhile, and Check status leaves it alone.
    conn_info = client.get(f"{base(team)}/data-sources/{source['id']}/connection", headers=team["dev"])
    assert conn_info.status_code == 409 and conn_info.json()["error"]["code"] == "cloud_database_creating"
    checked = client.post(f"{base(team)}/data-sources/{source['id']}/check", headers=team["dev"])
    assert checked.json()["status"] == "creating"
    assert client.delete(f"{base(team)}/data-sources/{source['id']}", headers=team["admin"]).status_code == 409

    jobs.run_queued()
    db.expire_all()
    ds = db.get(DataSource, source["id"])
    assert db.get(Job, job_id).status == "succeeded", db.get(Job, job_id).error
    assert ds.status == "ok" and ds.status_message == "Connected (server 8.0.39)"
    config = decrypt_json(ds.config_encrypted)
    assert config["host"] == HOST and config["tls"] is True and config["tls_verify"] is False
    assert len(config["password"]) >= 30 and config["username"] == "deployer"
    assert aws.tls == [("mysql", HOST)]
    names = aws.names()
    assert names[:5] == ["default_vpc", "ensure_security_group", "public_ip", "allow_ingress", "create_db_instance"]
    assert aws.args("allow_ingress")[0] == ("sg-db1", 3306, {"cidr": f"{PC_IP}/32"})
    params = aws.args("create_db_instance")[0][0]
    assert params["DBInstanceIdentifier"] == ds.cloud_state["instance_id"]
    assert {k: params[k] for k in ("Engine", "DBInstanceClass", "AllocatedStorage", "StorageType")} == {
        "Engine": "mysql",
        "DBInstanceClass": "db.t4g.micro",
        "AllocatedStorage": 20,
        "StorageType": "gp3",
    }
    assert params["PubliclyAccessible"] and params["DeletionProtection"] and params["StorageEncrypted"]
    assert params["BackupRetentionPeriod"] == 7 and params["VpcSecurityGroupIds"] == ["sg-db1"]
    assert params["MasterUserPassword"] == config["password"]
    # The password is never returned, logged or audited.
    job = db.get(Job, job_id)
    listed = client.get(f"{base(team)}/data-sources", headers=team["dev"])
    assert config["password"] not in listed.text and config["password"] not in json.dumps(job.result)
    audit = db.query(AuditLog).filter(AuditLog.action == "data_source.create").one()
    assert config["password"] not in json.dumps(audit.details) and audit.details["cloud"] == "create"
    # ... only through the existing connection-details reveal.
    shown = client.get(f"{base(team)}/data-sources/{ds.id}/connection", headers=team["dev"]).json()
    assert shown["password"] == config["password"] and "ssl=true" in shown["uri"]
    # The connection cannot be removed while a database uses it.
    gone = client.delete(f"/v1/instance/cloud/{conn.id}", headers=team["owner"])
    assert gone.status_code == 409 and "Shop DB" in gone.json()["error"]["message"]


def test_create_without_default_vpc_fails_plainly(client, db, team, aws):
    aws.returns["default_vpc"] = None
    source = create(client, team, connection(db)).json()["data_source"]
    jobs.run_queued()
    db.expire_all()
    ds = db.get(DataSource, source["id"])
    assert ds.status == "error" and "Create default VPC" in ds.status_message
    assert "create_db_instance" not in aws.names()


def test_firewall_follows_the_pc_ip(client, db, team, aws):
    source = create(client, team, connection(db)).json()["data_source"]
    jobs.run_queued()
    aws.calls.clear()
    assert cloud_db.refresh_pc_ips(jobs.get_sessionmaker(), force=True) == 0
    assert aws.names() == ["public_ip"]  # same IP: no firewall change

    aws.returns["public_ip"] = "198.51.100.9"
    aws.calls.clear()
    assert cloud_db.refresh_pc_ips(jobs.get_sessionmaker(), force=True) == 1
    assert aws.args("allow_ingress") == [("sg-db1", 3306, {"cidr": "198.51.100.9/32"})]
    assert aws.args("revoke_ingress") == [("sg-db1", 3306, {"cidr": f"{PC_IP}/32"})]
    db.expire_all()
    assert db.get(DataSource, source["id"]).cloud_state["allowed_ip"] == "198.51.100.9"
    assert cloud_db.refresh_pc_ips(jobs.get_sessionmaker()) == 0  # throttled between scheduler ticks


def test_created_database_ip_for_admins_and_fixed_host(client, db, team, aws):
    source = create(client, team, connection(db)).json()["data_source"]
    jobs.run_queued()
    url = f"{base(team)}/data-sources"

    def cloud_of(role):
        return next(s for s in client.get(url, headers=team[role]).json() if s["id"] == source["id"])["cloud"]

    # This PC's public IP (the firewall rule) is shown to admins only.
    assert cloud_of("admin")["allowed_ip"] == PC_IP and cloud_of("dev")["allowed_ip"] is None
    checked = client.post(f"{url}/{source['id']}/check", headers=team["dev"]).json()
    assert checked["cloud"]["allowed_ip"] is None
    # Its cloud metadata describes the RDS instance, so the Edit dialog cannot re-point it.
    moved = client.patch(f"{url}/{source['id']}", json={"config": {"host": "db.example.com"}}, headers=team["admin"])
    assert moved.status_code == 422 and "host and port" in moved.json()["error"]["message"]
    same = {"host": f" {HOST} ", "port": "3306"}  # the same endpoint, written differently
    assert client.patch(f"{url}/{source['id']}", json={"config": same}, headers=team["admin"]).status_code == 200
    db.expire_all()
    assert decrypt_json(db.get(DataSource, source["id"]).config_encrypted)["host"] == HOST


def test_delete_created_database_takes_a_final_snapshot(client, db, team, aws):
    source = create(client, team, connection(db)).json()["data_source"]
    jobs.run_queued()
    db.expire_all()
    instance = db.get(DataSource, source["id"]).cloud_state["instance_id"]
    aws.calls.clear()
    aws.returns["db_instance"] = None  # gone once deleted
    held = iter([True])  # the deleted instance's network interface holds the group for a moment

    def release(group):
        if next(held, False):
            raise CloudError("AWS DependencyViolation: in use", code="DependencyViolation")

    aws.returns["delete_security_group"] = release
    resp = client.delete(f"{base(team)}/data-sources/{source['id']}", headers=team["admin"])
    assert resp.status_code == 200 and resp.json()["job"]["type"] == "data_source.cloud_delete"
    db.expire_all()
    assert db.get(DataSource, source["id"]) is None
    jobs.run_queued()
    job = db.get(Job, resp.json()["job"]["id"])
    assert job.status == "succeeded", job.error
    (deleted, snapshot) = aws.args("delete_db_instance")[0]
    assert deleted == instance and snapshot.startswith(f"{instance}-final-")
    assert aws.names() == ["delete_db_instance", "db_instance", "delete_security_group", "delete_security_group"]
    assert job.result["final_snapshot"] == snapshot


def _project_with_cloud_things(client, db, team, aws):
    conn = connection(db)
    create(client, team, conn)
    jobs.run_queued()
    make_app(
        db,
        team["project"],
        "Api",
        target="aws_app",
        cloud_connection_id=conn.id,
        cloud_state={"service_arn": "arn:svc", "ecr_repository": "deployer-api-1"},
    )
    aws.calls.clear()
    return f"/v1/projects/{team['project'].id}?confirm={team['project'].slug}"


def test_project_delete_asks_what_to_do_with_cloud_resources_and_can_keep_them(client, db, team, aws):
    url = _project_with_cloud_things(client, db, team, aws)
    resp = client.delete(url, headers=team["owner"])
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "cloud_resources_left"
    error = resp.json()["error"]
    assert "database Shop DB" in error["message"] and "cloud=keep" in error["message"]
    found = {r["name"]: r for r in error["details"]["resources"]}
    assert any("RDS instance" in r for r in found["Shop DB"]["resources"]) and found["Api"]["type"] == "app"
    assert client.delete(url + "&cloud=maybe", headers=team["owner"]).status_code == 422

    kept = client.delete(url + "&cloud=keep", headers=team["owner"])
    assert kept.status_code == 200, kept.text
    assert kept.json()["cloud"]["choice"] == "keep" and kept.json()["cloud"]["job_ids"] == []
    assert aws.calls == [] and db.scalars(select(Job).where(Job.type.like("%cloud_%delete%"))).all() == []
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "project.delete")).one()
    assert audit.details["cloud"] == "keep" and {r["name"] for r in audit.details["cloud_resources"]} == {
        "Shop DB",
        "Api",
    }


def test_project_delete_can_delete_cloud_resources_and_alerts_on_failure(client, db, team, aws):
    url = _project_with_cloud_things(client, db, team, aws)
    aws.returns["db_instance"] = None  # gone once deleted
    aws.fail["delete_service"] = "AWS AccessDenied: not allowed"
    resp = client.delete(url + "&cloud=delete", headers=team["owner"])
    assert resp.status_code == 200, resp.text
    job_ids = resp.json()["cloud"]["job_ids"]
    jobs.run_queued()
    db.expire_all()
    done = {db.get(Job, j).type: db.get(Job, j) for j in job_ids}
    assert all(j.project_id is None for j in done.values())  # they outlived the project
    assert done["data_source.cloud_delete"].status == "succeeded"
    assert done["data_source.cloud_delete"].result["final_snapshot"]
    assert done["app.cloud_teardown"].status == "failed"
    conditions = alerts.conditions(db, 0)
    (failed,) = [c for c in conditions.values() if c.alert == "cloud_cleanup_failed"]
    assert "Api" in failed.message and "AccessDenied" in failed.message


def test_project_delete_refuses_cloud_delete_through_a_connection_that_goes_with_the_project(client, db, team, aws):
    create(client, team, connection(db, project_id=team["project"].id))
    jobs.run_queued()
    url = f"{base(team)}?confirm={team['project'].slug}"
    resp = client.delete(url + "&cloud=delete", headers=team["owner"])
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "cloud_connection_in_project"
    assert resp.json()["error"]["details"]["resources"] == ["database Shop DB"]
    assert client.delete(url + "&cloud=keep", headers=team["owner"]).status_code == 200


def test_export_carries_the_cloud_link_but_no_data_and_a_copy_never_owns_the_instance(client, db, team, aws):
    """docs/CLOUD.md "C2-5": config (with the password) only inside the encrypted file, no rows, and an
    imported copy is a plain external connection that never deletes the original's instance."""
    import os

    from app.models import Project, User
    from app.services import transfer

    create(client, team, connection(db))
    jobs.run_queued()
    source = db.scalars(select(DataSource)).one()
    password = decrypt_json(source.config_encrypted)["password"]
    path, counts = transfer.build_export_file(db, scope="projects", projects=[team["project"]], passphrase="p" * 12)
    try:
        with open(path, encoding="utf-8") as fh:
            assert password not in fh.read()
        payload = transfer.read_export_file(path, "p" * 12, "projects")
    finally:
        os.unlink(path)
    (row,) = payload["data_sources"]
    assert row["cloud_state"]["created"] is True and row["config"]["password"] == password
    assert payload["data"] == {} and counts["rows"] == 0  # the data stays in AWS

    owner = db.get(User, db.get(Project, team["project"].id).owner_id)
    (copy,), _ = transfer.import_projects(db, payload, owner)
    (imported,) = db.scalars(select(DataSource).where(DataSource.project_id == copy.id)).all()
    assert imported.mode == "external" and imported.cloud_connection_id is None and imported.cloud_state is None
    assert not cloud_db.is_created(imported)


def test_delete_reports_what_is_left(client, db, team, aws):
    source = create(client, team, connection(db)).json()["data_source"]
    jobs.run_queued()
    aws.fail["delete_db_instance"] = "AWS AccessDenied: not allowed"
    resp = client.delete(f"{base(team)}/data-sources/{source['id']}", headers=team["admin"])
    jobs.run_queued()
    job = db.get(Job, resp.json()["job"]["id"])
    assert job.status == "failed" and "AccessDenied" in job.error and "RDS instance" in job.error


def test_delete_over_the_api_and_mcp_needs_the_name_and_keeps_the_final_snapshot(client, db, team, aws, make_source):
    source = create(client, team, connection(db)).json()["data_source"]
    jobs.run_queued()
    db.expire_all()
    instance = db.get(DataSource, source["id"]).cloud_state["instance_id"]
    aws.calls.clear()
    aws.returns["db_instance"] = None  # gone once deleted
    keys = {
        role: {
            "Authorization": "Bearer "
            + client.post(f"{base(team)}/api-keys", json={"name": role, "role": role}, headers=team["admin"]).json()[
                "secret"
            ]
        }
        for role in ("anon", "service")
    }
    url = f"{base(team)}/cloud/databases/{source['id']}"
    ok = {"confirm_name": "Shop DB", "confirm_delete": "true"}
    # A developer's session and an anon key may not; an admin's session or a service key may.
    assert client.delete(url, params=ok, headers=team["dev"]).status_code == 403
    assert client.delete(url, params=ok, headers=keys["anon"]).status_code == 403
    for params in ({}, {"confirm_name": "Shop DB"}, {"confirm_name": "shop db", "confirm_delete": "true"}):
        refused = client.delete(url, params=params, headers=keys["service"])
        assert refused.status_code == 422 and refused.json()["error"]["code"] == "delete_not_confirmed"
    details = refused.json()["error"]["details"]
    assert details["name"] == "Shop DB" and details["removes"][0].startswith(f"RDS instance {instance}")
    assert "final snapshot" in details["keeps"] and aws.calls == []
    # Databases that are not in a cloud account stay a dashboard action.
    local = make_source(team["project"])
    plain = client.delete(f"{base(team)}/cloud/databases/{local.id}", params=ok, headers=keys["service"])
    assert plain.status_code == 400 and plain.json()["error"]["code"] == "not_a_cloud_database"

    def call(**arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
        body["params"] = {"name": "delete_cloud_database", "arguments": {"source_id": source["id"], **arguments}}
        out = client.post(f"{base(team)}/mcp", json=body, headers=keys["service"]).json()["result"]
        return out["isError"], json.loads(out["content"][0]["text"])

    err, out = call(confirm_name="Shop DB", confirm_delete=False)
    assert err and out["error"]["code"] == "delete_not_confirmed" and out["error"]["details"] == details
    err, out = call(confirm_name="Shop DB", confirm_delete=True)
    assert not err and out["ok"] and out["job"]["type"] == "data_source.cloud_delete"
    assert out["removes"] == details["removes"] and out["keeps"] == details["keeps"]
    db.expire_all()
    assert db.get(DataSource, source["id"]) is None
    jobs.run_queued()
    job = db.get(Job, out["job"]["id"])
    assert job.status == "succeeded", job.error
    (deleted, snapshot) = aws.args("delete_db_instance")[0]
    assert deleted == instance and snapshot.startswith(f"{instance}-final-")
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "data_source.delete")).one()
    assert audit.details["api_key_id"] and audit.details["name"] == "Shop DB"

    # A connected database is only forgotten; nothing in AWS changes.
    body = {"connection_id": source["cloud"]["connection_id"], "name": "Prod", "resource_id": "shop-prod"}
    body |= {"username": "app", "password": "pw"}
    prod = client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"]).json()
    aws.calls.clear()
    resp = client.delete(
        f"{base(team)}/cloud/databases/{prod['id']}", params={**ok, "confirm_name": "Prod"}, headers=team["admin"]
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["removes"] == [] and "only forgets" in resp.json()["keeps"] and "job" not in resp.json()
    assert aws.calls == [] and db.get(DataSource, prod["id"]) is None


def test_connect_existing_instance(client, db, team, aws):
    conn = connection(db)
    url = f"{base(team)}/cloud/connections/{conn.id}/databases"
    assert client.get(url, headers=team["dev"]).status_code == 403
    listed = client.get(url, headers=team["admin"]).json()
    assert listed["pc_ip"] == PC_IP and listed["region"] == "eu-west-1"
    by_id = {d["id"]: d for d in listed["databases"]}
    assert by_id["shop-prod"]["problem"] is None and by_id["shop-prod"]["deployer_engine"] == "postgresql"
    assert "not supported" in by_id["legacy"]["problem"] and "Public access" in by_id["private"]["problem"]

    body = {"connection_id": conn.id, "name": "Prod", "resource_id": "shop-prod", "username": "app", "password": "pw"}
    aws.returns["reachable"] = False
    failed = client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"])
    assert failed.status_code == 400 and PC_IP in failed.json()["error"]["message"]
    aws.returns["reachable"] = True
    resp = client.post(f"{base(team)}/cloud/databases/connect", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["engine"] == "postgresql" and out["database_name"] == "shop" and out["status"] == "ok"
    assert out["cloud"]["created"] is False and out["cloud"]["resources"] == []
    assert aws.tested[-1][1]["host"] == "shop-prod.abc.eu-west-1.rds.amazonaws.com" and aws.tested[-1][1]["tls"]
    # Never touched in AWS: no firewall rules, and removing it only forgets the connection.
    assert not {"allow_ingress", "ensure_security_group", "create_db_instance"} & set(aws.names())
    aws.calls.clear()
    assert cloud_db.refresh_pc_ips(jobs.get_sessionmaker(), force=True) == 0 and aws.calls == []
    removed = client.delete(f"{base(team)}/data-sources/{out['id']}", headers=team["admin"])
    assert removed.json() == {"ok": True} and aws.calls == []


def test_app_runner_app_gets_the_cloud_database(client, db, docker, team, aws):
    conn = connection(db)
    source = create(client, team, conn).json()["data_source"]
    jobs.run_queued()
    # Database access is allowed on App Runner (it means the AWS databases), not on the other cloud targets.
    body = {"name": "Api", "repo_url": "https://github.com/acme/api", "preset": "node", "target": "aws_app"}
    body |= {"cloud_connection_id": conn.id, "database_access": True, "confirm_billing": True}
    resp = client.post(f"{base(team)}/apps", json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    static = {**body, "preset": "static", "target": "aws_static", "name": "Site"}
    assert client.post(f"{base(team)}/apps", json=static, headers=team["admin"]).status_code == 422
    aws.calls.clear()
    app = db.get(App, resp.json()["id"])
    dep = deploy(db, app)
    assert dep.status == "live", dep.error
    (name, image, port, env, role, connector) = aws.args("create_service")[0]
    assert connector == "arn:aws:apprunner:eu-west-1:1:vpcconnector/deployer-vpc"
    assert env["DEPLOYER_DB_SHOP_DB_HOST"] == HOST and env["DEPLOYER_DB_SHOP_DB_DATABASE"] == "shopdb"
    assert (
        env["DEPLOYER_DB_SHOP_DB_URL"].startswith("mysql://deployer:") and "ssl=true" in env["DEPLOYER_DB_SHOP_DB_URL"]
    )
    assert not {"DEPLOYER_URL", "DEPLOYER_API_KEY", "DEPLOYER_PROJECT_ID"} & set(env)
    assert aws.args("ensure_vpc_connector") == [("vpc-0a1b2c3d",)]
    assert ("sg-db1", 3306, {"source_group": "sg-conn"}) in aws.args("allow_ingress")
    password = decrypt_json(db.get(DataSource, source["id"]).config_encrypted)["password"]
    assert password not in dep.log and "NAT gateway" in dep.log and "Shop DB" in dep.log

    # Without database access the service goes back to App Runner's default egress.
    client.patch(f"{base(team)}/apps/{app.id}", json={"database_access": False}, headers=team["admin"])
    aws.calls.clear()
    db.expire_all()
    assert deploy(db, db.get(App, app.id)).status == "live"
    update = aws.args("update_service")[0]
    assert update[5] is None and not any(k.startswith("DEPLOYER_DB_") for k in update[3])


def test_mcp_cloud_database_tools(client, db, team, aws, sqlite_engine, monkeypatch):
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
    assert [loc["id"] for loc in options["locations"]] == ["local", "external", "aws", "firebase"]
    assert options["aws"]["default_instance_class"] == "db.t4g.micro" and "NAT" in options["aws"]["network"]
    err, out = admin_call(
        "create_cloud_database", connection_id=conn.id, name="Shop DB", engine="mysql", confirm_billing=False
    )
    assert err and out["error"]["code"] == "billing_not_confirmed"
    err, out = admin_call(
        "create_cloud_database", connection_id=conn.id, name="Shop DB", engine="mysql", confirm_billing=True
    )
    assert not err and out["data_source"]["status"] == "creating"
    _, listed = admin_call("list_cloud_databases", connection_id=conn.id)
    assert listed["pc_ip"] == PC_IP
    _, sources = call("list_data_sources")
    assert sources[0]["cloud"] == {
        "provider": "aws",
        "service": "rds",
        "created": True,
        "resource_id": out["data_source"]["cloud"]["resource_id"],
        "region": "eu-west-1",
    }
    # The data tools reach an RDS database like any external one, once AWS has made it.
    sid = out["data_source"]["id"]
    err, waiting = call("list_rows", source_id=sid, table="items")
    assert err and waiting["error"]["code"] == "cloud_database_creating"
    jobs.run_queued()
    monkeypatch.setattr(connections, "get_sql_engine", lambda ds: sqlite_engine)
    err, rows = call("list_rows", source_id=sid, table="items", limit=2)
    assert not err and rows["total"] == 7 and len(rows["rows"]) == 2
    err, _ = call("insert_row", source_id=sid, table="items", values={"id": 99, "name": "new"})
    assert not err
    err, result = call("run_query", source_id=sid, query="SELECT COUNT(*) AS n FROM items")
    assert not err and "8" in json.dumps(result)


def test_policy_covers_databases_and_scopes_the_firewall():
    statements = {s["Sid"]: s for s in cloud.AWS_POLICY["Statement"]}
    assert "rds:CreateDBInstance" in statements["Databases"]["Action"]
    assert "arn:aws:rds:*:*:db:deployer-*" in statements["Databases"]["Resource"]
    rules = statements["DatabaseFirewallRules"]
    assert rules["Condition"] == {"StringEquals": {"aws:ResourceTag/managed-by": "deployer"}}
    assert statements["DatabaseFirewallTag"]["Condition"]["StringEquals"]["ec2:CreateAction"] == "CreateSecurityGroup"
    assert "apprunner:CreateVpcConnector" in statements["AppRunner"]["Action"]


def test_names():
    ds = DataSource(id="0123456789abcdef", name="My Shop -- DB!")
    assert cloud_db.instance_id(ds) == "deployer-my-shop-db-01234567"
    assert cloud_db.db_name("My Shop") == "myshop" and cloud_db.db_name("42") == "app42"
    assert cloud_db.cloud_out(ds) is None  # a plain external source


def test_migration_0013(migration_db):
    cfg, db_file = migration_db
    command.upgrade(cfg, "head")
    conn = sqlite3.connect(db_file)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(data_sources)")}
    assert {"cloud_connection_id", "cloud_state"} <= columns
    conn.close()
    command.downgrade(cfg, "0012")
    conn = sqlite3.connect(db_file)
    assert "cloud_state" not in {row[1] for row in conn.execute("PRAGMA table_info(data_sources)")}
    conn.close()
    command.upgrade(cfg, "head")


def test_ensure_vpc_connector_runs_against_the_real_botocore_models():
    """V-02: the real AwsClient body against botocore's service models (Stubber validates every request
    and response). App Runner has no list_vpc_connectors paginator, so the lookup follows NextToken."""
    from botocore.stub import Stubber

    from app.services.cloud_aws import TAG, AwsClient

    aws = AwsClient({"region": "eu-west-1", "access_key_id": "test", "secret_access_key": "test"})
    clients = {s: aws._session.client(s, region_name="eu-west-1") for s in ("ec2", "apprunner")}
    aws._c = lambda service, region=None: clients[service]
    vpc, arn = "vpc-1", "arn:aws:apprunner:eu-west-1:123456789012:vpcconnector/deployer-vpc-1/1/abc"

    def connector(name, status="ACTIVE"):
        return {"VpcConnectorName": name, "VpcConnectorArn": arn, "Status": status}

    with Stubber(clients["ec2"]) as ec2, Stubber(clients["apprunner"]) as ar:
        for _ in range(2):
            ec2.add_response("create_security_group", {"GroupId": "sg-1"})
        # Found on the second page.
        ar.add_response("list_vpc_connectors", {"VpcConnectors": [connector("other")], "NextToken": "t1"}, {})
        ar.add_response("list_vpc_connectors", {"VpcConnectors": [connector("deployer-vpc-1")]}, {"NextToken": "t1"})
        # Missing (only an inactive one): created in the VPC's subnets.
        ar.add_response("list_vpc_connectors", {"VpcConnectors": [connector("deployer-vpc-1", "INACTIVE")]}, {})
        ec2.add_response("describe_subnets", {"Subnets": [{"SubnetId": "subnet-a"}, {"SubnetId": "subnet-b"}]})
        ar.add_response(
            "create_vpc_connector",
            {"VpcConnector": connector("deployer-vpc-1")},
            {
                "VpcConnectorName": "deployer-vpc-1",
                "Subnets": ["subnet-a", "subnet-b"],
                "SecurityGroups": ["sg-1"],
                "Tags": [TAG],
            },
        )
        assert aws.ensure_vpc_connector(vpc) == {"arn": arn, "group_id": "sg-1"}
        assert aws.ensure_vpc_connector(vpc) == {"arn": arn, "group_id": "sg-1"}
        ar.assert_no_pending_responses()
        ec2.assert_no_pending_responses()
