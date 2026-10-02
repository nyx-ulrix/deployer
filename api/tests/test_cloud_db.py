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
from app.models import App, AuditLog, DataSource, Deployment, Job
from app.services import alerts, cloud, cloud_db, cloud_deploy, connections, jobs
from tests.apps_support import make_app
from tests.test_cloud import FakeCloud, connection, deploy

PC_IP = "203.0.113.7"
NAT_IP = "198.51.100.42"
HOST = "deployer-shop-db.abc123.eu-west-1.rds.amazonaws.com"
CONNECTOR = "arn:aws:apprunner:eu-west-1:1:vpcconnector/deployer-vpc"
NAT_CONNECTOR = "arn:aws:apprunner:eu-west-1:1:vpcconnector/deployer-nat-vpc"


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
        ensure_vpc_connector=lambda vpc, private_subnets=None: {
            "arn": NAT_CONNECTOR if private_subnets else CONNECTOR,
            "group_id": "sg-conn",
        },
        ensure_nat_network={"subnet_ids": ["subnet-p1", "subnet-p2"], "nat_id": "nat-1", "public_ip": NAT_IP},
        nat_gateway_state=("available", None),
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
    assert connector == CONNECTOR
    assert env["DEPLOYER_DB_SHOP_DB_HOST"] == HOST and env["DEPLOYER_DB_SHOP_DB_DATABASE"] == "shopdb"
    assert (
        env["DEPLOYER_DB_SHOP_DB_URL"].startswith("mysql://deployer:") and "ssl=true" in env["DEPLOYER_DB_SHOP_DB_URL"]
    )
    assert not {"DEPLOYER_URL", "DEPLOYER_API_KEY", "DEPLOYER_PROJECT_ID"} & set(env)
    assert aws.args("ensure_vpc_connector") == [("vpc-0a1b2c3d",)]
    assert ("sg-db1", 3306, {"source_group": "sg-conn"}) in aws.args("allow_ingress")
    password = decrypt_json(db.get(DataSource, source["id"]).config_encrypted)["password"]
    assert password not in dep.log and "reach the internet too" in dep.log and "Shop DB" in dep.log

    # Without database access the service goes back to App Runner's default egress.
    client.patch(f"{base(team)}/apps/{app.id}", json={"database_access": False}, headers=team["admin"])
    aws.calls.clear()
    db.expire_all()
    assert deploy(db, db.get(App, app.id)).status == "live"
    update = aws.args("update_service")[0]
    assert update[5] is None and not any(k.startswith("DEPLOYER_DB_") for k in update[3])


def test_internet_access_adds_a_shared_nat_gateway_removed_with_its_last_user(client, db, docker, team, aws):
    """docs/CLOUD.md "C2-6": opt-in, admin + billing confirmation, only on App Runner apps with database access.
    The deploy makes the NAT network (found by tag when it exists) and points the service at the private-subnet
    connector; apps of the account share one NAT gateway per VPC; it goes when the last user opts out or is deleted."""
    conn = connection(db)
    create(client, team, conn)
    jobs.run_queued()
    apps = f"{base(team)}/apps"
    body = {"name": "Api", "repo_url": "https://github.com/acme/api", "preset": "node", "target": "aws_app"}
    body |= {"cloud_connection_id": conn.id, "database_access": True, "confirm_billing": True}
    wrong = client.post(apps, json={**body, "database_access": False, "internet_access": True}, headers=team["admin"])
    assert wrong.status_code == 422 and wrong.json()["error"]["details"]["field"] == "internet_access"
    app = client.post(apps, json=body, headers=team["admin"]).json()
    assert app["internet_access"] is False
    url = f"{apps}/{app['id']}"
    assert client.patch(url, json={"internet_access": True}, headers=team["dev"]).status_code == 403
    unconfirmed = client.patch(url, json={"internet_access": True}, headers=team["admin"])
    assert unconfirmed.status_code == 422 and unconfirmed.json()["error"]["code"] == "billing_not_confirmed"
    assert "NAT gateway" in unconfirmed.json()["error"]["message"] and "US$" in unconfirmed.json()["error"]["message"]
    on = client.patch(url, json={"internet_access": True, "confirm_billing": True}, headers=team["admin"])
    assert on.status_code == 200 and on.json()["internet_access"] is True, on.text
    assert db.get(App, app["id"]).cloud_state == {"internet_access": True}
    assert cloud_deploy.enqueue_teardown(db, db.get(App, app["id"]), None) is None  # a switch, not a resource

    aws.calls.clear()
    dep = deploy(db, db.get(App, app["id"]))
    assert dep.status == "live", dep.error
    vpc = "vpc-0a1b2c3d"
    assert aws.args("ensure_nat_network") == [(vpc,)] and aws.args("nat_gateway_state") == [("nat-1",)]
    assert aws.args("ensure_vpc_connector") == [(vpc,), (vpc, ["subnet-p1", "subnet-p2"])]
    assert aws.args("create_service")[0][5] == NAT_CONNECTOR
    assert NAT_IP in dep.log and "subnet-p1" in dep.log
    db.expire_all()
    first = db.get(App, app["id"])
    assert first.cloud_state["nat_vpc"] == vpc
    shown = client.get(url, headers=team["dev"]).json()
    assert shown["internet_access"] is True and any("NAT gateway" in r for r in shown["cloud"]["resources"])

    # A second app of the account shares it (the network is found by tag, nothing is made twice).
    second = make_app(
        db,
        team["project"],
        "Worker",
        target="aws_app",
        cloud_connection_id=conn.id,
        database_access=True,
        cloud_state={"internet_access": True},
    )
    assert deploy(db, second).status == "live"
    assert cloud_deploy.nat_users(db, conn.id, vpc, first.id) == 1
    # Deleting it keeps the NAT gateway: the first app still goes through it.
    aws.calls.clear()
    resp = client.delete(f"{apps}/{second.id}", headers=team["admin"])
    jobs.run_queued()
    assert db.get(Job, resp.json()["teardown_job_id"]).status == "succeeded"
    assert aws.names() == ["delete_service", "delete_repository", "github_roles"]  # the sweep looks, finds nothing

    # The first app opts out: it is republished at once (G1), which moves the service back to the plain
    # connector and, as the last user, queues the removal (connector, NAT gateway + IP, route table, subnets -
    # after the service left).
    aws.calls.clear()
    off = client.patch(url, json={"internet_access": False}, headers=team["admin"]).json()
    assert off["internet_access"] is False and off["env_deployment_id"]
    jobs.run_queued()
    db.expire_all()
    dep = db.get(Deployment, off["env_deployment_id"])
    assert dep.status == "live", dep.error
    assert aws.args("update_service")[0][5] == CONNECTOR and "ensure_nat_network" not in aws.names()
    assert "removing it" in dep.log
    removal = ["delete_vpc_connector", "delete_nat_gateway", "delete_nat_routes", "delete_nat_subnets"]
    assert aws.names()[-5:] == removal + ["github_roles"]
    assert aws.args("delete_vpc_connector") == [(f"deployer-nat-{vpc}",)] and aws.args("delete_nat_gateway") == [(vpc,)]
    db.expire_all()
    assert not db.get(App, app["id"]).cloud_state.get("nat_vpc")
    teardown = db.scalars(select(Job).where(Job.type == "app.cloud_teardown").order_by(Job.created_at.desc())).first()
    assert teardown.status == "succeeded" and teardown.params["state"] == {"nat_vpc": vpc, "nat_last": True}

    # Deleting the last user removes it too (after the service, which holds the connector until it is gone).
    on = client.patch(url, json={"internet_access": True, "confirm_billing": True}, headers=team["admin"]).json()
    jobs.run_queued()  # the republish adds the NAT gateway again
    db.expire_all()
    assert db.get(Deployment, on["env_deployment_id"]).status == "live"
    assert db.get(App, app["id"]).cloud_state["nat_vpc"] == vpc
    aws.calls.clear()
    resp = client.delete(url, headers=team["admin"])
    jobs.run_queued()
    job = db.get(Job, resp.json()["teardown_job_id"])
    assert job.status == "succeeded", job.error
    assert aws.names() == [
        "delete_service",
        "delete_repository",
        "delete_vpc_connector",
        "delete_nat_gateway",
        "delete_nat_routes",
        "delete_nat_subnets",
        "github_roles",
    ]


def test_internet_access_without_a_vpc_database_or_off_the_target_is_dropped(client, db, docker, team, aws):
    conn = connection(db)
    app = make_app(
        db,
        team["project"],
        "Api",
        target="aws_app",
        cloud_connection_id=conn.id,
        database_access=True,
        cloud_state={"internet_access": True},
    )
    dep = deploy(db, app)  # no RDS database: default egress, no NAT gateway
    assert dep.status == "live" and "ensure_nat_network" not in aws.names() and "no NAT gateway" in dep.log
    url = f"{base(team)}/apps/{app.id}"
    off = client.patch(url, json={"database_access": False}, headers=team["admin"]).json()
    assert off["internet_access"] is False  # it depended on database access
    jobs.run_queued()  # the republish (G1) that the changed database access queued
    moved = client.patch(url, json={"target": "local"}, headers=team["admin"]).json()
    assert moved["internet_access"] is False and moved["target"] == "local"


def test_mcp_set_app_internet_access(client, db, team, aws):
    conn = connection(db)
    app = make_app(db, team["project"], "Api", target="aws_app", cloud_connection_id=conn.id, database_access=True)

    def call(tool, auth, **arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        out = client.post(f"{base(team)}/mcp", json=body, headers=auth).json()["result"]
        return out["isError"], json.loads(out["content"][0]["text"])

    err, out = call("set_app_internet_access", team["admin"], app_id=app.id, enabled=True)
    assert err and out["error"]["code"] == "billing_not_confirmed"
    err, out = call("set_app_internet_access", team["admin"], app_id=app.id, enabled=True, confirm_billing=True)
    assert not err and out["internet_access"] is True and "cloud" in out and "env_keys" not in out
    assert out["env_deployment_id"] is None  # not deployed yet: the switch applies on the next deploy
    err, out = call("set_app_internet_access", team["admin"], app_id=app.id, enabled=False)
    assert not err and out["internet_access"] is False


def test_nat_helpers():
    from app.services.cloud_aws import _public_subnet, free_blocks

    used = ["172.31.0.0/20", "172.31.16.0/20", "172.31.32.0/24"]
    assert free_blocks("172.31.0.0/16", used, 2) == ["172.31.33.0/24", "172.31.34.0/24"]
    with pytest.raises(CloudError, match="No room"):
        free_blocks("10.0.0.0/24", ["10.0.0.0/24"], 1)
    with pytest.raises(CloudError, match="No room"):
        free_blocks("10.0.0.0/28", [], 1)  # smaller than one block
    igw = {"DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-1", "State": "active"}
    local = {"DestinationCidrBlock": "172.31.0.0/16", "GatewayId": "local", "State": "active"}
    main = {"RouteTableId": "rtb-main", "Routes": [local, igw], "Associations": [{"Main": True}]}
    private = {"RouteTableId": "rtb-p", "Routes": [local], "Associations": [{"Main": False, "SubnetId": "subnet-p"}]}
    subnets = [{"SubnetId": "subnet-p"}, {"SubnetId": "subnet-a"}]
    assert _public_subnet(subnets, [main, private]) == "subnet-a"  # the main table's internet route applies to it
    assert _public_subnet(subnets, [{**main, "Routes": [local]}, private]) is None


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
    statements = {s["Sid"]: s for s in cloud.aws_statements()}
    assert "rds:CreateDBInstance" in statements["Databases"]["Action"]
    assert "arn:aws:rds:*:*:db:deployer-*" in statements["Databases"]["Resource"]
    rules = statements["DatabaseFirewallRules"]
    assert rules["Condition"] == {"StringEquals": {"aws:ResourceTag/managed-by": "deployer"}}
    assert statements["DatabaseFirewallTag"]["Condition"]["StringEquals"]["ec2:CreateAction"] == "CreateSecurityGroup"
    assert "apprunner:CreateVpcConnector" in statements["AppRunner"]["Action"]
    # docs/CLOUD.md "C2-6": the NAT network is created (and tagged only then); changed and deleted by tag.
    assert statements["AppRunnerVpcConnectorDelete"]["Action"] == "apprunner:DeleteVpcConnector"
    assert statements["AppRunnerVpcConnectorDelete"]["Resource"] == "arn:aws:apprunner:*:*:vpcconnector/deployer-nat-*"
    assert {"ec2:DescribeNatGateways", "ec2:DescribeAddresses"} == set(statements["InternetRead"]["Action"])
    assert "Condition" not in statements["InternetCreate"] and "*" not in statements["InternetCreate"]["Resource"]
    assert statements["InternetTag"]["Condition"]["StringEquals"]["ec2:CreateAction"] == [
        "CreateSubnet",
        "AllocateAddress",
        "CreateNatGateway",
        "CreateRouteTable",
    ]
    change = statements["InternetChange"]
    assert {"ec2:DeleteNatGateway", "ec2:ReleaseAddress", "ec2:DeleteSubnet", "ec2:DeleteRouteTable"} <= set(
        change["Action"]
    )
    assert change["Condition"] == {"StringEquals": {"aws:ResourceTag/managed-by": "deployer"}}


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
        # Missing (only an inactive one): created in the VPC's own subnets, not the private ones Deployer
        # added for the NAT gateway (tagged).
        ar.add_response("list_vpc_connectors", {"VpcConnectors": [connector("deployer-vpc-1", "INACTIVE")]}, {})
        ec2.add_response(
            "describe_subnets",
            {"Subnets": [{"SubnetId": "subnet-a"}, {"SubnetId": "subnet-b"}, {"SubnetId": "subnet-p", "Tags": [TAG]}]},
        )
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


def test_nat_network_runs_against_the_real_botocore_models(monkeypatch):
    """docs/CLOUD.md "C2-6": every EC2 / App Runner call of the NAT gateway network against botocore's models
    (Stubber validates request parameters and responses): created once, found by tag the second time, waited
    for, and removed in order with the retries a connector in use / a subnet still held need."""
    from botocore.stub import Stubber

    from app.services import cloud_aws
    from app.services.cloud_aws import TAG, AwsClient, nat_name

    monkeypatch.setattr(cloud_aws, "POLL_S", 0)
    aws = AwsClient({"region": "eu-west-1", "access_key_id": "test", "secret_access_key": "test"})
    clients = {s: aws._session.client(s, region_name="eu-west-1") for s in ("ec2", "apprunner")}
    aws._c = lambda service, region=None: clients[service]
    vpc = "vpc-1"
    tags = [TAG, {"Key": "Name", "Value": nat_name(vpc)}]
    by_name = {"Name": "tag:Name", "Values": [nat_name(vpc)]}
    in_vpc = {"Name": "vpc-id", "Values": [vpc]}

    def subnet(sid, zone, cidr, ours=False):
        out = {"SubnetId": sid, "AvailabilityZone": zone, "CidrBlock": cidr}
        return {**out, "Tags": tags} if ours else out

    def tag_spec(kind):
        return [{"ResourceType": kind, "Tags": tags}]

    theirs = [subnet("subnet-a", "eu-west-1a", "172.31.0.0/20"), subnet("subnet-b", "eu-west-1b", "172.31.16.0/20")]
    ours = [
        subnet("subnet-p1", "eu-west-1a", "172.31.32.0/24", True),
        subnet("subnet-p2", "eu-west-1b", "172.31.33.0/24", True),
    ]
    igw = {"DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-1", "State": "active"}
    main = {"RouteTableId": "rtb-main", "Routes": [igw], "Associations": [{"Main": True, "RouteTableId": "rtb-main"}]}
    private = {
        "RouteTableId": "rtb-p",
        "Tags": tags,
        "Routes": [{"DestinationCidrBlock": "0.0.0.0/0", "NatGatewayId": "nat-1", "State": "active"}],
        "Associations": [
            {"Main": False, "SubnetId": "subnet-p1", "RouteTableAssociationId": "rtbassoc-1"},
            {"Main": False, "SubnetId": "subnet-p2", "RouteTableAssociationId": "rtbassoc-2"},
        ],
    }
    nat = {"NatGatewayId": "nat-1", "State": "available", "VpcId": vpc}
    address = {"AllocationId": "eipalloc-1", "PublicIp": NAT_IP}
    connector = {"VpcConnectorName": nat_name(vpc), "VpcConnectorArn": "arn:c", "Status": "ACTIVE"}

    with Stubber(clients["ec2"]) as ec2, Stubber(clients["apprunner"]) as ar:
        # First time: two private subnets (one per AZ the VPC has a subnet in, in free /24 blocks), an Elastic
        # IP, the NAT gateway in a public subnet, a route table 0.0.0.0/0 -> NAT associated with both.
        ec2.add_response("describe_subnets", {"Subnets": theirs}, {"Filters": [in_vpc]})
        ec2.add_response("describe_route_tables", {"RouteTables": [main]}, {"Filters": [in_vpc]})
        ec2.add_response("describe_nat_gateways", {"NatGateways": []}, {"Filter": [in_vpc, by_name]})
        ec2.add_response("describe_vpcs", {"Vpcs": [{"VpcId": vpc, "CidrBlock": "172.31.0.0/16"}]}, {"VpcIds": [vpc]})
        for s in ours:
            expected = {k: s[k] for k in ("AvailabilityZone", "CidrBlock")}
            ec2.add_response(
                "create_subnet", {"Subnet": s}, {**expected, "VpcId": vpc, "TagSpecifications": tag_spec("subnet")}
            )
        ec2.add_response("describe_addresses", {"Addresses": []}, {"Filters": [by_name]})
        ec2.add_response("allocate_address", address, {"Domain": "vpc", "TagSpecifications": tag_spec("elastic-ip")})
        ec2.add_response(
            "create_nat_gateway",
            {"NatGateway": {**nat, "State": "pending"}},
            {
                "SubnetId": "subnet-a",
                "AllocationId": "eipalloc-1",
                "ConnectivityType": "public",
                "TagSpecifications": tag_spec("natgateway"),
            },
        )
        ec2.add_response(
            "create_route_table",
            {"RouteTable": {"RouteTableId": "rtb-p", "Tags": tags}},
            {"VpcId": vpc, "TagSpecifications": tag_spec("route-table")},
        )
        ec2.add_response(
            "create_route",
            {"Return": True},
            {"RouteTableId": "rtb-p", "DestinationCidrBlock": "0.0.0.0/0", "NatGatewayId": "nat-1"},
        )
        for i, s in enumerate(ours):
            ec2.add_response(
                "associate_route_table",
                {"AssociationId": f"rtbassoc-{i + 1}"},
                {"RouteTableId": "rtb-p", "SubnetId": s["SubnetId"]},
            )
        made = aws.ensure_nat_network(vpc)
        assert made == {"subnet_ids": ["subnet-p1", "subnet-p2"], "nat_id": "nat-1", "public_ip": NAT_IP}
        # Second time: everything is found by tag, nothing is created.
        ec2.add_response("describe_subnets", {"Subnets": theirs + ours})
        ec2.add_response("describe_route_tables", {"RouteTables": [main, private]})
        ec2.add_response("describe_nat_gateways", {"NatGateways": [nat]})
        ec2.add_response("describe_addresses", {"Addresses": [address]})
        assert aws.ensure_nat_network(vpc)["nat_id"] == "nat-1"
        # No public subnet (no internet gateway route): a plain error before anything is made (a VPC with
        # nothing of Deployer's in it yet: no subnet or address gets created).
        ec2.add_response("describe_subnets", {"Subnets": theirs})
        ec2.add_response("describe_route_tables", {"RouteTables": [{**main, "Routes": []}]})
        ec2.add_response("describe_nat_gateways", {"NatGateways": []})
        with pytest.raises(CloudError, match="no public subnet"):
            aws.ensure_nat_network(vpc)

        pending = {"NatGateways": [{**nat, "State": "pending"}]}
        ec2.add_response("describe_nat_gateways", pending, {"NatGatewayIds": ["nat-1"]})
        assert aws.nat_gateway_state("nat-1") == ("pending", None)
        failed = {**nat, "State": "failed", "FailureMessage": "Elastic IP address could not be associated"}
        ec2.add_response("describe_nat_gateways", {"NatGateways": [failed]})
        assert aws.nat_gateway_state("nat-1") == ("failed", "Elastic IP address could not be associated")

        # The connector on the private subnets.
        ec2.add_response("create_security_group", {"GroupId": "sg-1"})
        ar.add_response("list_vpc_connectors", {"VpcConnectors": []}, {})
        ar.add_response(
            "create_vpc_connector",
            {"VpcConnector": connector},
            {
                "VpcConnectorName": nat_name(vpc),
                "Subnets": ["subnet-p1", "subnet-p2"],
                "SecurityGroups": ["sg-1"],
                "Tags": [TAG],
            },
        )
        assert aws.ensure_vpc_connector(vpc, ["subnet-p1", "subnet-p2"]) == {"arn": "arn:c", "group_id": "sg-1"}

        # Removal: the connector (retried while the deleted service still holds it), the NAT gateway (waited
        # for) and its address, the route table (associations first), the subnets (retried while held).
        ar.add_response("list_vpc_connectors", {"VpcConnectors": [connector]}, {})
        in_use = {"VpcConnectorArn": "arn:c"}
        ar.add_client_error("delete_vpc_connector", "InvalidRequestException", "in use", expected_params=in_use)
        ar.add_response("delete_vpc_connector", {"VpcConnector": connector}, in_use)
        aws.delete_vpc_connector(nat_name(vpc))
        ec2.add_response("describe_nat_gateways", {"NatGateways": [nat]}, {"Filter": [in_vpc, by_name]})
        ec2.add_response("delete_nat_gateway", {"NatGatewayId": "nat-1"}, {"NatGatewayId": "nat-1"})
        for state in ("deleting", "deleted"):
            ec2.add_response(
                "describe_nat_gateways", {"NatGateways": [{**nat, "State": state}]}, {"NatGatewayIds": ["nat-1"]}
            )
        ec2.add_response("describe_addresses", {"Addresses": [address]}, {"Filters": [by_name]})
        ec2.add_response("release_address", {}, {"AllocationId": "eipalloc-1"})
        aws.delete_nat_gateway(vpc)
        ec2.add_response("describe_route_tables", {"RouteTables": [private]}, {"Filters": [in_vpc, by_name]})
        for i in (1, 2):
            ec2.add_response("disassociate_route_table", {}, {"AssociationId": f"rtbassoc-{i}"})
        ec2.add_response("delete_route_table", {}, {"RouteTableId": "rtb-p"})
        aws.delete_nat_routes(vpc)
        ec2.add_response("describe_subnets", {"Subnets": ours}, {"Filters": [in_vpc, by_name]})
        held = {"SubnetId": "subnet-p1"}
        ec2.add_client_error("delete_subnet", "DependencyViolation", "has dependencies", expected_params=held)
        ec2.add_response("delete_subnet", {}, held)
        ec2.add_response("delete_subnet", {}, {"SubnetId": "subnet-p2"})
        aws.delete_nat_subnets(vpc)
        ar.assert_no_pending_responses()
        ec2.assert_no_pending_responses()
