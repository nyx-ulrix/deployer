"""Cloud databases phase C2-1 (docs/CLOUD.md): AWS RDS created or connected as data sources, the
firewall that follows this PC's IP, delete with a final snapshot, App Runner apps getting the database
through cloud_deploy.cloud_env + a VPC connector, MCP tools and migration 0013. AWS is faked; nothing
here reaches a real cloud."""

import json
import sqlite3

import pytest
from alembic import command

from app.crypto import decrypt_json
from app.errors import CloudError
from app.models import App, AuditLog, DataSource, Job
from app.services import cloud, cloud_db, cloud_deploy, connections, jobs
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
        ensure_access_role="arn:aws:iam::123456789012:role/deployer-apprunner-ecr-access",
        create_service={"arn": "arn:svc", "url": "https://abc.eu-west-1.awsapprunner.com", "operation_id": "op1"},
        operation="SUCCEEDED",
        delete_db_instance=True,
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


def test_project_delete_never_orphans_a_created_database(client, db, team, aws):
    create(client, team, connection(db))
    jobs.run_queued()
    project = team["project"]
    resp = client.delete(f"/v1/projects/{project.id}?confirm={project.slug}", headers=team["owner"])
    assert resp.status_code == 409 and "database Shop DB" in resp.json()["error"]["message"]


def test_delete_reports_what_is_left(client, db, team, aws):
    source = create(client, team, connection(db)).json()["data_source"]
    jobs.run_queued()
    aws.fail["delete_db_instance"] = "AWS AccessDenied: not allowed"
    resp = client.delete(f"{base(team)}/data-sources/{source['id']}", headers=team["admin"])
    jobs.run_queued()
    job = db.get(Job, resp.json()["job"]["id"])
    assert job.status == "failed" and "AccessDenied" in job.error and "RDS instance" in job.error


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
    body |= {"cloud_connection_id": conn.id, "database_access": True}
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


def test_mcp_cloud_database_tools(client, db, team, aws):
    key = client.post(f"{base(team)}/api-keys", json={"name": "k", "role": "service"}, headers=team["admin"])
    headers = {"Authorization": f"Bearer {key.json()['secret']}"}
    conn = connection(db)

    def call(tool, **arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        out = client.post(f"{base(team)}/mcp", json=body, headers=headers).json()["result"]
        return out["isError"], json.loads(out["content"][0]["text"])

    _, options = call("cloud_database_options")
    assert [loc["id"] for loc in options["locations"]] == ["local", "external", "aws", "firebase"]
    assert options["aws"]["default_instance_class"] == "db.t4g.micro" and "NAT" in options["aws"]["network"]
    err, out = call(
        "create_cloud_database", connection_id=conn.id, name="Shop DB", engine="mysql", confirm_billing=False
    )
    assert err and out["error"]["code"] == "billing_not_confirmed"
    err, out = call(
        "create_cloud_database", connection_id=conn.id, name="Shop DB", engine="mysql", confirm_billing=True
    )
    assert not err and out["data_source"]["status"] == "creating"
    _, listed = call("list_cloud_databases", connection_id=conn.id)
    assert listed["pc_ip"] == PC_IP
    _, sources = call("list_data_sources")
    assert sources[0]["cloud"] == {
        "provider": "aws",
        "service": "rds",
        "created": True,
        "resource_id": out["data_source"]["cloud"]["resource_id"],
        "region": "eu-west-1",
    }


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
