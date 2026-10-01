"""Databases in the user's own cloud account (docs/CLOUD.md "C2 - cloud databases").

A cloud database is an ordinary `external` data source (so the SQL browser, query console, schema and
DDL export work unchanged) with `cloud_connection_id` and `cloud_state` set:

- **connected**: an RDS / Aurora instance or cluster the user already has. Deployer only stores the
  endpoint and the user's database login; it never changes that instance or its firewall.
- **created**: a small RDS instance Deployer created (job `data_source.cloud_create`): default VPC,
  publicly reachable endpoint behind a security group `deployer-db-<id8>` that only lets in this PC's
  current public IP (followed every few minutes by `refresh_pc_ips`) and the App Runner VPC connector's
  group, TLS required, automated backups, deletion protection, encrypted storage, a random master
  password kept with `encrypt_json` in the source's config. Deleting it (job `data_source.cloud_delete`)
  switches deletion protection off and deletes with a final snapshot, then removes the group.

DynamoDB ("C2-2"): an `external` source with engine `dynamodb` holding one or more tables
(`cloud_state.tables`); data operations are in services/dynamo.py. **Created**: one on-demand table
`deployer-<name>-<id8>` (job `data_source.cloud_create`: CreateTable, wait for ACTIVE), deletion protection
on; deleting switches it off, takes a final on-demand backup and deletes the table. **Connected**: tables the
user already has, only read and written, never deleted.

Cloud Firestore ("C2-3"): an `external` source with engine `firestore` on a Firebase connection, one
existing Firestore database of that project (`cloud_state.database`), only ever connected - Deployer never
creates or deletes one. Data operations are in services/firestore.py.

Firebase Realtime Database ("C2-4"): an `external` source with engine `firebase_rtdb` on a Firebase connection,
one database instance of that project (`cloud_state.instance` / `.url`). Connected, or - when the project has
none yet - the project's default instance is created first (billable once used, so confirmed). Deployer never
deletes one. Data operations are in services/rtdb.py.

Apps on `aws_app` with database access get `DEPLOYER_DB_<NAME>_*` for the project's databases on the
same AWS connection through `cloud_deploy.cloud_env`, and reach them through the VPC connector (RDS) or
their App Runner instance role, scoped to the tables' ARNs (DynamoDB). Apps on `firebase_app` get the
project's Firestore and Realtime Databases on the same Firebase connection and reach them as their service
account.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.crypto import decrypt_json, encrypt_json
from app.errors import ApiError, CloudError, conflict
from app.models import App, CloudConnection, DataSource, Job, utcnow
from app.services import cloud, cloud_aws, cloud_gcp, connections, dynamo, firestore, jobs, rtdb

log = logging.getLogger(__name__)

POLL_S = 20.0  # tests set 0
CREATE_TIMEOUT_S = 45 * 60
DELETE_TIMEOUT_S = 45 * 60
GROUP_RELEASE_S = 10 * 60
IP_REFRESH_EVERY_S = 5 * 60
MASTER_USER = "deployer"

# Deployer engine -> RDS engine for new instances; RDS / Aurora engine -> Deployer engine for connecting.
CREATE_ENGINES = {"mysql": "mysql", "mariadb": "mariadb", "postgresql": "postgres"}
RDS_ENGINES = {
    "mysql": "mysql",
    "aurora-mysql": "mysql",
    "mariadb": "mariadb",
    "postgres": "postgresql",
    "aurora-postgresql": "postgresql",
}
INSTANCE_CLASSES = {
    "db.t4g.micro": "Smallest: 2 shared vCPUs, 1 GB memory. Fine for a small site. About US$12/month.",
    "db.t4g.small": "Small: 2 shared vCPUs, 2 GB memory. About US$24/month.",
    "db.t4g.medium": "Medium: 2 shared vCPUs, 4 GB memory. About US$48/month.",
}
DEFAULT_CLASS = "db.t4g.micro"
STORAGE_GB = 20
BACKUP_DAYS = 7

# The "Add database" dialog's four places, also returned to MCP clients (plain language on purpose).
LOCATIONS = [
    {
        "id": "local",
        "label": "On this PC",
        "what": "Deployer runs a new database on this PC (or one of your host PCs) and backs it up automatically.",
        "when_pc_off": "Apps and people can only reach it while this PC is on.",
        "cost": "Free (your electricity and internet).",
    },
    {
        "id": "external",
        "label": "On another PC or server",
        "what": "Connect a database that already runs somewhere else: another computer, a hosting company, "
        "MongoDB Atlas. Deployer only connects to it; that server keeps it running.",
        "when_pc_off": "It keeps running (it is not on this PC), but this dashboard needs the PC on.",
        "cost": "Whatever that server or company charges.",
    },
    {
        "id": "aws",
        "label": "In your AWS account",
        "what": "Amazon runs the database in your own AWS account: a SQL database (RDS: MySQL, MariaDB or "
        "PostgreSQL) or a DynamoDB table (NoSQL). Create a new one here or connect one you already have.",
        "when_pc_off": "Stays up when this PC is off, so cloud apps keep working.",
        "cost": "AWS bills you directly: the smallest new SQL database is roughly US$15-20/month (less on the free "
        "tier); a DynamoDB table costs per read, write and GB stored, often cents for a small app.",
    },
    {
        "id": "firebase",
        "label": "In your Firebase project",
        "what": "Google runs the database in your Firebase project: its Cloud Firestore database or its "
        "Realtime Database (both NoSQL, the databases Firebase apps use).",
        "when_pc_off": "Stays up when this PC is off, so cloud apps keep working.",
        "cost": "Free quota (Firestore: 50,000 reads and 20,000 writes a day; Realtime Database: 1 GB stored and "
        "10 GB downloaded a month), then billed by Google for what you use (Blaze plan).",
        "only": "nosql",
        "note": "NoSQL only: Cloud Firestore or Realtime Database.",
    },
]
COST_NOTE = (
    "Creates a database in your AWS account that AWS bills to you while it exists: the instance per hour "
    f"(db.t4g.micro is about US$12/month), {STORAGE_GB} GB of storage (about US$2.30/month), its public IPv4 "
    f"address (about US$3.60/month) and backup storage beyond the free amount ({BACKUP_DAYS} days kept). "
    "New AWS accounts' free tier can cover the smallest size. Deleting it keeps a final snapshot, billed for "
    "storage until you delete it in the AWS console."
)
NETWORK_NOTE = (
    "How it is reached: the database gets an internet address, but its firewall (security group) only lets "
    "in this PC's current public IP (Deployer updates the rule when your IP changes) and your App Runner apps "
    "(through a private network link, a VPC connector). Connections must use TLS (encryption). An App Runner "
    "app linked to a database sends all its outgoing traffic through your VPC, which has no internet route by "
    "default: if the app also calls other internet services, add a NAT gateway in the VPC console (about "
    "US$32/month)."
)

DYNAMODB_WHAT = (
    "DynamoDB is Amazon's NoSQL database: you store items (JSON-like records) in a table and find them by a key "
    "you choose, such as a user id. There is no server to keep running and nothing to size. Your app talks to "
    "it with the AWS SDK (not SQL)."
)
DYNAMODB_KEYS = (
    "Every item needs the partition key (for example id or userId). Add a sort key (for example createdAt) when "
    "one partition holds many items you want in order, like a user's orders. Keys cannot be changed later."
)
DYNAMODB_COST_NOTE = (
    "Creates a DynamoDB table in your AWS account that AWS bills to you, on demand: about US$0.63 per million "
    "writes and US$0.13 per million reads, plus about US$0.25 per GB stored per month (US region prices; the "
    "first 25 GB of storage are free every month). An idle table costs only its storage. On-demand backups cost "
    "about US$0.10 per GB per month until you delete them; deleting the table here keeps a final backup."
)
FIRESTORE_WHAT = (
    "Cloud Firestore is Firebase's NoSQL database: documents (JSON-like records) grouped in collections, such as "
    "users/ann, and a document can hold its own collections (users/ann/orders). Google runs it for you - nothing "
    "to size or keep running. Apps use it with the Firebase or Google Cloud SDK (not SQL)."
)
FIRESTORE_CONNECT = (
    "Pick the database: every Firebase project can have one called (default), made in the Firebase console under "
    "Build -> Firestore Database -> Create database (choose production mode and a location near your users). "
    "Deployer only connects: it never creates or deletes a Firestore database, and removing it here keeps the data."
)
FIRESTORE_COST_NOTE = (
    "Connecting is free. Google bills reads, writes and storage to your Firebase project, including what you do in "
    "this dashboard (each page of documents is a few reads): the free quota is 50,000 reads and 20,000 writes a "
    "day and 1 GB stored; beyond it, about US$0.06 per 100,000 reads and US$0.18 per 100,000 writes (Blaze plan)."
)
FIRESTORE_NETWORK = (
    "No firewall or password: Deployer reaches it with your Firebase connection's service account, and Firebase "
    "full apps (Cloud Run) with Database access sign in as their own service account. Give that account (the "
    "project's default compute service account, PROJECT_NUMBER-compute@developer.gserviceaccount.com) the Cloud "
    "Datastore User role in the Google Cloud console -> IAM, unless it already has Editor."
)
# docs/CLOUD.md "C2-4": the two Firebase databases, one plain sentence each on how they differ.
FIRESTORE_SHORT = (
    "Cloud Firestore keeps separate documents in collections and can search them by several fields at once - "
    "the usual choice for a new app."
)
RTDB_SHORT = (
    "Realtime Database keeps everything in one big JSON tree that apps read and write by path and that sends "
    "every change to open apps instantly - good for small, fast-changing data like chat or who is online."
)
RTDB_WHAT = (
    "The Realtime Database is Firebase's original database: one JSON tree (nested data, like folders of values) "
    "where every piece has a path such as users/ann/name. Apps listening to a path get each change at once. "
    "Google runs it for you - nothing to size. Apps use the Firebase SDK (not SQL); queries sort and filter on "
    "one child at a time."
)
RTDB_CONNECT = (
    "Pick the database: most Firebase projects have one Realtime Database, the default one (<project>-default-rtdb). "
    "If yours has none yet, Deployer can create it here - pick a location near your users (it cannot move later). "
    "Removing it here only forgets it: the data stays in Firebase, and Deployer never deletes a Realtime Database."
)
RTDB_COST_NOTE = (
    "Creating the database costs nothing by itself. The free quota covers 1 GB stored and 10 GB downloaded a month "
    "(and 100 apps connected at once); beyond it, on the Blaze plan, Google bills about US$5 per GB stored and "
    "US$1 per GB downloaded each month - including what this dashboard reads."
)
RTDB_NETWORK = (
    "No firewall or password: Deployer reaches it with your Firebase connection's service account, which - like "
    "Firebase's Admin SDK - is not limited by the database's security rules. Firebase full apps (Cloud Run) with "
    "Database access sign in as their own service account: give it (the project's default compute service "
    "account, PROJECT_NUMBER-compute@developer.gserviceaccount.com) the Firebase Realtime Database Admin role in "
    "the Google Cloud console -> IAM, unless it already has Editor. Your website's visitors reach the database "
    "only as the security rules you set in the Firebase console allow."
)
DYNAMODB_NETWORK = (
    "No firewall or password: Deployer reaches it with your AWS connection's key, and App Runner apps with "
    "Database access through an IAM role that may use exactly these tables."
)


# --- names, output -------------------------------------------------------------------------------


def _slug(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def instance_id(ds: DataSource) -> str:
    """`deployer-<name>-<id8>`: RDS identifiers are letters, digits and single hyphens, <= 63 chars."""
    slug = _slug(ds.name)[:30].strip("-") or "db"
    return f"deployer-{slug}-{ds.id[:8]}"


def db_name(name: str) -> str:
    """The first database's name: letters and digits, starting with a letter (MySQL and PostgreSQL rules)."""
    clean = re.sub(r"[^A-Za-z0-9]", "", name).lower()[:30]
    return clean if clean[:1].isalpha() else f"app{clean}"[:30]


def is_created(ds: DataSource) -> bool:
    return bool((ds.cloud_state or {}).get("created"))


def resources(state: dict | None) -> list[str]:
    """What Deployer created in the cloud account for this source (the delete dialog lists it)."""
    s = state or {}
    if not s.get("created"):
        return []
    out = [f"DynamoDB table {t} (deleted after a final backup)" for t in s.get("tables") or []]
    if s.get("instance_id"):
        out.append(f"RDS instance {s['instance_id']} (deleted after a final snapshot)")
    if s.get("group_id"):
        out.append(f"Security group {s['group_id']} (its firewall)")
    return out


def cloud_out(ds: DataSource, db: Session | None = None) -> dict | None:
    """The `cloud` field of a data source: where it lives, what Deployer created; never secrets."""
    if not ds.cloud_connection_id and not ds.cloud_state:
        return None
    s = ds.cloud_state or {}
    conn = db.get(CloudConnection, ds.cloud_connection_id) if db is not None and ds.cloud_connection_id else None
    return {
        "provider": s.get("provider", "aws"),
        "connection_id": ds.cloud_connection_id,
        "connection_name": conn.name if conn else None,
        "service": s.get("service", "rds"),
        "created": bool(s.get("created")),
        "resource_id": s.get("instance_id")
        or s.get("cluster_id")
        or next(iter(s.get("tables") or []), None)
        or s.get("database")
        or s.get("instance"),
        "resource_kind": {"dynamodb": "table", "firestore": "database", "rtdb": "database"}.get(s.get("service"))
        or ("cluster" if s.get("cluster_id") else "instance"),
        "tables": s.get("tables"),
        "project_id": s.get("project_id"),
        "url": s.get("url"),  # Realtime Database
        "region": s.get("region") or s.get("location"),
        "instance_class": s.get("instance_class"),
        "allowed_ip": s.get("allowed_ip"),
        "job_id": s.get("job_id"),
        "resources": resources(s),
        "when_pc_off": "Stays up when this PC is off.",
    }


def options() -> dict:
    return {
        "locations": LOCATIONS,
        "aws": {
            "engines": list(CREATE_ENGINES),
            "instance_classes": [{"id": k, "description": v} for k, v in INSTANCE_CLASSES.items()],
            "default_instance_class": DEFAULT_CLASS,
            "storage_gb": STORAGE_GB,
            "backup_days": BACKUP_DAYS,
            "cost": COST_NOTE,
            "network": NETWORK_NOTE,
        },
        "firestore": {
            "short": FIRESTORE_SHORT,
            "what": FIRESTORE_WHAT,
            "connect": FIRESTORE_CONNECT,
            "cost": FIRESTORE_COST_NOTE,
            "network": FIRESTORE_NETWORK,
        },
        "rtdb": {
            "short": RTDB_SHORT,
            "what": RTDB_WHAT,
            "connect": RTDB_CONNECT,
            "cost": RTDB_COST_NOTE,
            "network": RTDB_NETWORK,
            "locations": [{"id": k, "label": v} for k, v in rtdb.LOCATIONS.items()],
        },
        "dynamodb": {
            "what": DYNAMODB_WHAT,
            "keys": DYNAMODB_KEYS,
            "key_types": [{"id": k, "label": v} for k, v in dynamo.KEY_TYPES.items()],
            "cost": DYNAMODB_COST_NOTE,
            "network": DYNAMODB_NETWORK,
        },
    }


def _connection(
    db: Session, project_id: str, connection_id: str, provider: str | None = "aws"
) -> tuple[CloudConnection, dict]:
    """A connection this project may use (of `provider`, when given), else 422."""
    conn = db.get(CloudConnection, connection_id) if connection_id else None
    if conn is None or conn.project_id not in (None, project_id) or provider not in (None, conn.provider):
        what = {"aws": "an AWS account", "firebase": "a Firebase project"}.get(provider or "", "a cloud account")
        raise ApiError(422, "validation_error", f"Pick {what} this project may use", {"field": "connection_id"})
    return conn, cloud.config_of(conn)


def _cloud_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except CloudError as exc:
        raise ApiError(502, "cloud_error", exc.message) from None


# --- connect an existing instance ----------------------------------------------------------------


def list_resources(db: Session, project_id: str, connection_id: str) -> dict:
    """RDS / Aurora databases and DynamoDB tables of an AWS connection's region, with whether Deployer can
    connect to each - or a Firebase connection's Firestore databases (`firestore`) and Realtime Databases
    (`rtdb`)."""
    conn, config = _connection(db, project_id, connection_id, provider=None)
    if conn.provider == "firebase":
        return _firebase_listing(config)
    aws = cloud_aws.client(config)
    found = _cloud_call(aws.db_resources)
    try:
        pc_ip = aws.public_ip()
    except CloudError:
        pc_ip = None
    out = []
    for r in found:
        engine = RDS_ENGINES.get(r["engine"])
        problem = None
        if engine is None:
            problem = f"{r['engine']} is not supported (MySQL, MariaDB, PostgreSQL and their Aurora versions are)"
        elif not r["public"]:
            problem = "Not publicly accessible: this PC cannot reach it (turn on Public access in the RDS console)"
        out.append({**r, "deployer_engine": engine, "region": config["region"], "problem": problem})
    tables, tables_problem = [], None
    try:
        tables = list_tables(aws)
    except CloudError as exc:  # e.g. a policy pasted before DynamoDB support: RDS still listed
        tables_problem = exc.message
    return {
        "region": config["region"],
        "pc_ip": pc_ip,
        "databases": out,
        "tables": tables,
        "tables_problem": tables_problem,
    }


def _firebase_listing(config: dict) -> dict:
    gcp = cloud_gcp.client(config)
    found, problem = [], None
    try:
        found = firestore.list_databases(gcp)
    except CloudError as exc:  # e.g. the role predates Firestore support: the dialog still takes a typed id
        problem = exc.message
    instances, rtdb_problem = [], None
    try:
        instances = rtdb.instances(gcp)
    except CloudError as exc:  # e.g. no Realtime Database role yet: the dialog says which one
        rtdb_problem = exc.message
    return {
        "provider": "firebase",
        "project_id": config.get("project_id"),
        "region": config.get("region"),
        "pc_ip": None,
        "databases": [],
        "tables": [],
        "tables_problem": None,
        "firestore": found,
        "firestore_problem": problem,
        "rtdb": instances,
        "rtdb_problem": rtdb_problem,
    }


def list_tables(aws, limit: int = 1000) -> list[str]:
    names, start = [], None
    while len(names) < limit:
        page = aws.ddb("ListTables", **({"ExclusiveStartTableName": start} if start else {}))
        names += page.get("TableNames") or []
        start = page.get("LastEvaluatedTableName")
        if not start:
            break
    return names


def connect(
    db: Session,
    project_id: str,
    *,
    connection_id: str,
    name: str,
    resource_id: str,
    username: str,
    password: str,
    database: str | None,
) -> DataSource:
    """A data source for an existing RDS / Aurora database (the caller checks the name and commits)."""
    conn, config = _connection(db, project_id, connection_id)
    aws = cloud_aws.client(config)
    found = next((r for r in _cloud_call(aws.db_resources) if r["id"] == resource_id), None)
    if found is None:
        raise ApiError(422, "validation_error", "That database was not found in this AWS account and region")
    engine = RDS_ENGINES.get(found["engine"])
    if engine is None or not found.get("host"):
        raise ApiError(422, "validation_error", f"Deployer cannot connect to a {found['engine']} database")
    source_config = {
        "host": found["host"],
        "port": int(found["port"] or connections.DEFAULT_PORTS[engine]),
        "username": username.strip(),
        "password": password,
        "database": (database or found.get("database") or ("postgres" if engine == "postgresql" else "")).strip(),
        "tls": True,
        "tls_verify": False,
    }
    if not source_config["username"] or not source_config["database"]:
        raise ApiError(422, "validation_error", "Enter the database user and the database name")
    ok, message, version = connections.try_config("sql", engine, source_config)
    if not ok:
        try:
            ip = aws.public_ip()
            message += (
                f" - The database must be publicly accessible and its security group must allow port "
                f"{source_config['port']} from this PC's public IP {ip}."
            )
        except CloudError:
            pass
        raise ApiError(400, "connection_failed", message)
    key = "cluster_id" if found["kind"] == "cluster" else "instance_id"
    ds = DataSource(
        project_id=project_id,
        name=name,
        kind="sql",
        engine=engine,
        mode="external",
        database_name=source_config["database"],
        config_encrypted=encrypt_json(source_config),
        status="ok",
        status_message=f"Connected (server {version})" if version else "Connected",
        last_checked_at=utcnow(),
        cloud_connection_id=conn.id,
        cloud_state={
            "provider": "aws",
            "service": "rds",
            "created": False,
            key: resource_id,
            "region": config["region"],
            "vpc_id": found.get("vpc_id"),
            "group_ids": found.get("security_groups") or [],
            "port": source_config["port"],
        },
    )
    db.add(ds)
    db.flush()
    return ds


def connect_tables(db: Session, project_id: str, *, connection_id: str, name: str, tables: list[str]) -> DataSource:
    """A DynamoDB source for tables the user already has (the caller checks the name and commits). Deployer
    only reads and writes their items; removing the source never deletes a table."""
    conn, config = _connection(db, project_id, connection_id)
    tables = list(dict.fromkeys(t.strip() for t in tables if t and t.strip()))
    if not tables:
        raise ApiError(422, "validation_error", "Pick at least one table", {"field": "tables"})
    aws = cloud_aws.client(config)
    for t in tables:
        try:
            aws.ddb("DescribeTable", TableName=t)
        except CloudError as exc:
            raise ApiError(400, "connection_failed", f"Table {t}: {exc.message}") from None
    noun = "table" if len(tables) == 1 else "tables"
    ds = DataSource(
        project_id=project_id,
        name=name,
        kind="nosql",
        engine=dynamo.ENGINE,
        mode="external",
        database_name=tables[0][:128],
        config_encrypted=encrypt_json({}),  # no secret of its own: the AWS connection's key is used
        status="ok",
        status_message=f"Connected ({len(tables)} {noun})",
        last_checked_at=utcnow(),
        cloud_connection_id=conn.id,
        cloud_state={
            "provider": "aws",
            "service": "dynamodb",
            "created": False,
            "tables": tables,
            "region": config["region"],
        },
    )
    db.add(ds)
    db.flush()
    return ds


def connect_firestore(db: Session, project_id: str, *, connection_id: str, name: str, database: str) -> DataSource:
    """A Firestore source for an existing database of the Firebase project (the caller checks the name and
    commits). Deployer never creates or deletes the database itself."""
    conn, config = _connection(db, project_id, connection_id, provider="firebase")
    database = (database or firestore.DEFAULT_DATABASE).strip()
    if not firestore.DATABASE_ID.match(database):
        raise ApiError(
            422,
            "validation_error",
            "That is not a Firestore database id: (default), or lowercase letters, digits and hyphens",
            {"field": "database"},
        )
    try:
        info = firestore.describe(cloud_gcp.client(config), database)
    except ApiError as exc:
        hint = (
            " - no Firestore database with that id: create it in the Firebase console (Build -> Firestore "
            "Database) first."
            if exc.code == "not_found"
            else ""
        )
        raise ApiError(400, "connection_failed", f"Database {database}: {exc.message}{hint}") from None
    problem = firestore.database_problem(info)
    if problem:
        raise ApiError(400, "connection_failed", problem)
    ds = DataSource(
        project_id=project_id,
        name=name,
        kind="nosql",
        engine=firestore.ENGINE,
        mode="external",
        database_name=database,
        config_encrypted=encrypt_json({}),  # no secret of its own: the Firebase connection's key is used
        status="ok",
        status_message=f"Connected ({info.get('locationId') or 'Firestore'})",
        last_checked_at=utcnow(),
        cloud_connection_id=conn.id,
        cloud_state={
            "provider": "firebase",
            "service": "firestore",
            "created": False,
            "database": database,
            "project_id": config.get("project_id"),
            "location": info.get("locationId"),
        },
    )
    db.add(ds)
    db.flush()
    return ds


def _rtdb_source(project_id: str, conn: CloudConnection, config: dict, name: str, inst: dict) -> DataSource:
    """The (unsaved) source of a Realtime Database instance from `rtdb.instances`."""
    return DataSource(
        project_id=project_id,
        name=name,
        kind="nosql",
        engine=rtdb.ENGINE,
        mode="external",
        database_name=inst["id"],
        config_encrypted=encrypt_json({}),  # no secret of its own: the Firebase connection's key is used
        status="ok",
        status_message=f"Connected ({inst.get('location') or 'Realtime Database'})",
        last_checked_at=utcnow(),
        cloud_connection_id=conn.id,
        cloud_state={
            "provider": "firebase",
            "service": "rtdb",
            "created": False,  # Deployer never deletes a Realtime Database, even one it created
            "instance": inst["id"],
            "url": inst["url"],
            "project_id": config.get("project_id"),
            "location": inst.get("location"),
        },
    )


def connect_rtdb(db: Session, project_id: str, *, connection_id: str, name: str, instance: str) -> DataSource:
    """A Realtime Database source for an instance of the Firebase project (the caller checks the name and
    commits). The instance must be in the project's listing, so its URL is Firebase's own."""
    conn, config = _connection(db, project_id, connection_id, provider="firebase")
    try:
        found = rtdb.instances(cloud_gcp.client(config))
    except CloudError as exc:
        raise ApiError(400, "connection_failed", f"Couldn't list the Realtime Databases: {exc.message}") from None
    inst = next((i for i in found if i["id"] == instance.strip()), None)
    if inst is None or not inst.get("url"):
        raise ApiError(
            400,
            "connection_failed",
            f"No Realtime Database {instance!r} in this Firebase project: pick one from the list, or create the "
            "default one",
        )
    if inst["problem"]:
        raise ApiError(400, "connection_failed", inst["problem"])
    ds = _rtdb_source(project_id, conn, config, name, inst)
    ok, message, _ = rtdb.check(ds)
    if not ok:
        raise ApiError(400, "connection_failed", message)
    db.add(ds)
    db.flush()
    return ds


def create_rtdb(db: Session, project_id: str, *, connection_id: str, name: str, location: str) -> DataSource:
    """Creates the Firebase project's default Realtime Database in `location` (or, when it already has one,
    connects that) and returns its source. Synchronous: Firebase answers with the ready database."""
    if location not in rtdb.LOCATIONS:
        raise ApiError(422, "validation_error", f"Pick one of: {', '.join(rtdb.LOCATIONS)}", {"field": "location"})
    conn, config = _connection(db, project_id, connection_id, provider="firebase")
    gcp = cloud_gcp.client(config)
    found = [i for i in _cloud_call(rtdb.instances, gcp) if i["type"] == "DEFAULT_DATABASE"]
    if not found:
        try:
            gcp.create_rtdb_instance(location, f"{config.get('project_id')}-default-rtdb")
        except CloudError as exc:
            if exc.status != 409:  # 409: made meanwhile (another click, the console) - connect it below
                raise ApiError(
                    502,
                    "cloud_error",
                    f"{exc.message} - the service account needs the Firebase Realtime Database Admin role and the "
                    "Firebase Realtime Database Management API turned on (Settings -> Cloud accounts).",
                ) from None
        found = [i for i in _cloud_call(rtdb.instances, gcp) if i["type"] == "DEFAULT_DATABASE"]
        if not found:
            raise ApiError(502, "cloud_error", "Firebase did not list the new database yet: try again in a minute")
    if found[0]["problem"] or not found[0].get("url"):  # e.g. the existing default database is disabled
        raise ApiError(400, "connection_failed", found[0]["problem"] or "Firebase gave no URL for this database")
    ds = _rtdb_source(project_id, conn, config, name, found[0])
    db.add(ds)
    db.flush()
    return ds


def create_table(
    db: Session,
    project_id: str,
    *,
    connection_id: str,
    name: str,
    partition_key: dict,
    sort_key: dict | None,
    user_id: str,
) -> tuple[DataSource, Job]:
    """A `creating` DynamoDB source and the job that creates its on-demand table (the caller commits and
    dispatches). Keys are `{name, type}` with type S (text), N (number) or B (binary)."""
    keys = [k for k in (partition_key, sort_key) if k]
    for k in keys:
        if not str(k.get("name") or "").strip() or k.get("type") not in dynamo.KEY_TYPES:
            raise ApiError(422, "validation_error", "Each key needs a name and a type (S, N or B)", {"field": "keys"})
    if sort_key and sort_key["name"].strip() == partition_key["name"].strip():
        raise ApiError(422, "validation_error", "The sort key must differ from the partition key", {"field": "keys"})
    conn, config = _connection(db, project_id, connection_id)
    ds = DataSource(
        project_id=project_id,
        name=name,
        kind="nosql",
        engine=dynamo.ENGINE,
        mode="external",
        database_name="",
        config_encrypted=encrypt_json({}),
        status="creating",
        status_message="Creating the table in your AWS account (usually under a minute)",
        cloud_connection_id=conn.id,
    )
    db.add(ds)
    db.flush()
    table = instance_id(ds)
    ds.database_name = table
    job = jobs.enqueue(
        db,
        type="data_source.cloud_create",
        params={"data_source_id": ds.id},
        project_id=project_id,
        data_source_id=ds.id,
        created_by_id=user_id,
    )
    ds.cloud_state = {
        "provider": "aws",
        "service": "dynamodb",
        "created": True,
        "tables": [table],
        "region": config["region"],
        "keys": [{"name": k["name"].strip(), "type": k["type"]} for k in keys],
        "job_id": job.id,
    }
    return ds, job


def _create_table_steps(ctx: jobs.JobContext, ds_id: str, config: dict, state: dict) -> dict:
    factory = ctx.session_factory
    aws = cloud_aws.client(config)
    table, keys = state["tables"][0], state["keys"]
    if not state.get("table_requested"):
        ctx.progress(0.2, f"Asking AWS for the table {table}", force=True)
        try:
            aws.ddb(
                "CreateTable",
                TableName=table,
                KeySchema=[
                    {"AttributeName": k["name"], "KeyType": t} for k, t in zip(keys, ("HASH", "RANGE"), strict=False)
                ],
                AttributeDefinitions=[{"AttributeName": k["name"], "AttributeType": k["type"]} for k in keys],
                BillingMode="PAY_PER_REQUEST",
                DeletionProtectionEnabled=True,
                Tags=[cloud_aws.TAG],
            )
        except CloudError as exc:
            if exc.code != "ResourceInUseException":  # an interrupted job already asked for it
                raise
        state = _save(factory, ds_id, table_requested=True) or state
    started = time.monotonic()
    while aws.ddb("DescribeTable", TableName=table)["Table"].get("TableStatus") != "ACTIVE":
        if time.monotonic() - started > CREATE_TIMEOUT_S:
            raise jobs.JobError("AWS did not finish creating the table in time")
        if _save(factory, ds_id) is None:
            return {"skipped": "data source removed"}
        ctx.check_cancelled()
        ctx.progress(0.5, "AWS is creating the table")
        time.sleep(POLL_S)
    with factory() as db:
        ds = db.get(DataSource, ds_id)
        if ds is None:
            return {"skipped": "data source removed"}
        ds.status, ds.status_message, ds.last_checked_at = "ok", "Connected (1 table)", utcnow()
        db.commit()
    return {"table": table}


# --- create a new instance -----------------------------------------------------------------------


def create(
    db: Session, project_id: str, *, connection_id: str, name: str, engine: str, instance_class: str, user_id: str
) -> tuple[DataSource, Job]:
    """A `creating` data source and the job that creates the instance (the caller commits and dispatches)."""
    if engine not in CREATE_ENGINES:
        raise ApiError(422, "validation_error", "Pick MySQL, MariaDB or PostgreSQL", {"field": "engine"})
    if instance_class not in INSTANCE_CLASSES:
        raise ApiError(422, "validation_error", "Pick one of the offered sizes", {"field": "instance_class"})
    conn, config = _connection(db, project_id, connection_id)
    port = connections.DEFAULT_PORTS[engine]
    database = db_name(name)
    ds = DataSource(
        project_id=project_id,
        name=name,
        kind="sql",
        engine=engine,
        mode="external",
        database_name=database,
        # The master password exists (encrypted) before the instance does; the job fills in the host.
        config_encrypted=encrypt_json(
            {
                "host": "",
                "port": port,
                "username": MASTER_USER,
                "password": secrets.token_urlsafe(24),
                "database": database,
                "tls": True,
                "tls_verify": False,
            }
        ),
        status="creating",
        status_message="Creating the database in your AWS account (usually 5-15 minutes)",
        cloud_connection_id=conn.id,
    )
    db.add(ds)
    db.flush()
    job = jobs.enqueue(
        db,
        type="data_source.cloud_create",
        params={"data_source_id": ds.id},
        project_id=project_id,
        data_source_id=ds.id,
        created_by_id=user_id,
    )
    ds.cloud_state = {
        "provider": "aws",
        "service": "rds",
        "created": True,
        "instance_id": instance_id(ds),
        "region": config["region"],
        "instance_class": instance_class,
        "storage_gb": STORAGE_GB,
        "port": port,
        "job_id": job.id,
    }
    return ds, job


def _save(factory: jobs.SessionFactory, ds_id: str, **values) -> dict | None:
    """Merges `values` into the source's cloud_state the moment a resource exists. None once deleted."""
    with factory() as db:
        ds = db.get(DataSource, ds_id)
        if ds is None:
            return None
        state = {**(ds.cloud_state or {}), **values}
        ds.cloud_state = state
        db.commit()
        return state


def _require_tls(engine: str, config: dict) -> None:
    """MySQL / MariaDB: the master user must use TLS. RDS for PostgreSQL 15+ already forces it
    (rds.force_ssl defaults to 1) and new instances get the newest version."""
    if engine == "postgresql":
        return
    sql_engine = connections.build_sql_engine(engine, config, pooled=False, io_timeout=30)
    try:
        with sql_engine.begin() as c:
            c.execute(text(f"ALTER USER '{MASTER_USER}'@'%' REQUIRE SSL"))
    finally:
        sql_engine.dispose()


def _fail(factory: jobs.SessionFactory, ds_id: str, message: str) -> None:
    with factory() as db:
        ds = db.get(DataSource, ds_id)
        if ds is not None:
            ds.status, ds.status_message, ds.last_checked_at = "error", message[:2000], utcnow()
            db.commit()


@jobs.job_handler("data_source.cloud_create")
def _job_create(ctx: jobs.JobContext) -> dict:
    ds_id = str(ctx.params["data_source_id"])
    try:
        return _create_steps(ctx, ds_id)
    except CloudError as exc:
        _fail(ctx.session_factory, ds_id, exc.message)
        raise jobs.JobError(exc.message) from None
    except jobs.JobCancelled:
        _fail(ctx.session_factory, ds_id, "Cancelled; remove it to delete what was created in AWS")
        raise
    except Exception as exc:  # never leave the source `creating`: Remove cleans up what exists
        message = str(exc) if isinstance(exc, jobs.JobError) else f"Could not create it ({type(exc).__name__})"
        _fail(ctx.session_factory, ds_id, message)
        raise


def _create_steps(ctx: jobs.JobContext, ds_id: str) -> dict:
    factory = ctx.session_factory
    with factory() as db:
        ds = db.get(DataSource, ds_id)
        if ds is None:
            return {"skipped": "data source removed"}
        conn = db.get(CloudConnection, ds.cloud_connection_id) if ds.cloud_connection_id else None
        if conn is None:
            raise jobs.JobError("The AWS connection was removed")
        config, state = cloud.config_of(conn), dict(ds.cloud_state or {})
        source_config = decrypt_json(ds.config_encrypted)
        engine = ds.engine
    if state.get("service") == "dynamodb":
        return _create_table_steps(ctx, ds_id, config, state)
    aws = cloud_aws.client(config)
    port = int(state["port"])
    if not state.get("vpc_id"):
        ctx.progress(0.05, "Finding the default network (VPC)", force=True)
        vpc = aws.default_vpc()
        if not vpc:
            raise jobs.JobError(
                f"The {config['region']} region of this AWS account has no default VPC. Create one in the VPC "
                "console (Your VPCs -> Actions -> Create default VPC), then add the database again."
            )
        state = _save(factory, ds_id, vpc_id=vpc) or state
    if not state.get("group_id"):
        ctx.progress(0.1, "Creating the database's firewall (security group)", force=True)
        # AWS allows few characters in descriptions: the id, not the user's name for it.
        group = aws.ensure_security_group(
            f"deployer-db-{ds_id[:8]}", state["vpc_id"], f"Deployer database {ds_id[:8]} - this PC and App Runner"
        )
        state = _save(factory, ds_id, group_id=group) or state
    ip = aws.public_ip()
    if state.get("allowed_ip") != ip:
        ctx.progress(0.15, "Letting this PC's public IP through the firewall", force=True)
        aws.allow_ingress(state["group_id"], port, cidr=f"{ip}/32")
        if state.get("allowed_ip"):  # a retried job on a PC whose IP changed meanwhile
            aws.revoke_ingress(state["group_id"], port, cidr=f"{state['allowed_ip']}/32")
        state = _save(factory, ds_id, allowed_ip=ip) or state
    if not state.get("instance_requested"):
        ctx.progress(0.2, "Asking AWS for the database", force=True)
        aws.create_db_instance(
            {
                "DBInstanceIdentifier": state["instance_id"],
                "Engine": CREATE_ENGINES[engine],
                "DBInstanceClass": state["instance_class"],
                "AllocatedStorage": STORAGE_GB,
                "StorageType": "gp3",
                "StorageEncrypted": True,
                "MasterUsername": MASTER_USER,
                "MasterUserPassword": source_config["password"],
                "DBName": source_config["database"],
                "Port": port,
                "VpcSecurityGroupIds": [state["group_id"]],
                "PubliclyAccessible": True,
                "MultiAZ": False,
                "BackupRetentionPeriod": BACKUP_DAYS,
                "DeletionProtection": True,
                "CopyTagsToSnapshot": True,
                "AutoMinorVersionUpgrade": True,
            }
        )
        state = _save(factory, ds_id, instance_requested=True) or state
    started = time.monotonic()
    while True:
        info = aws.db_instance(state["instance_id"])
        status = (info or {}).get("status") or "creating"
        if info and status == "available" and info.get("host"):
            break
        if status in ("failed", "incompatible-parameters", "incompatible-network", "storage-full"):
            raise jobs.JobError(f"AWS could not create the database (status: {status})")
        if time.monotonic() - started > CREATE_TIMEOUT_S:
            raise jobs.JobError(f"AWS did not finish creating the database within {CREATE_TIMEOUT_S // 60} minutes")
        if _save(factory, ds_id) is None:
            return {"skipped": "data source removed"}
        ctx.check_cancelled()
        elapsed = int(time.monotonic() - started)
        ctx.progress(
            min(0.25 + elapsed / 1200 * 0.6, 0.85), f"AWS is creating the database: {status} ({elapsed // 60} min)"
        )
        time.sleep(POLL_S)
    ctx.progress(0.9, "Requiring TLS and checking the connection", force=True)
    source_config.update(host=info["host"], port=int(info.get("port") or port))
    tls_required = True
    try:
        _require_tls(engine, source_config)
    except Exception as exc:  # noqa: BLE001 - the connection test below says what is wrong
        tls_required = False
        log.warning("could not require TLS on %s: %s", state["instance_id"], type(exc).__name__)
    ok, message, version = connections.try_config("sql", engine, source_config)
    with factory() as db:
        ds = db.get(DataSource, ds_id)
        if ds is None:
            return {"skipped": "data source removed"}
        ds.config_encrypted = encrypt_json(source_config)
        ds.status = "ok" if ok else "error"
        ds.status_message = (f"Connected (server {version})" if version else "Connected") if ok else message
        ds.last_checked_at = utcnow()
        db.commit()
    connections.invalidate(ds_id)
    return {"instance_id": state["instance_id"], "host": info["host"], "connected": ok, "tls_required": tls_required}


# --- delete --------------------------------------------------------------------------------------


def enqueue_delete(db: Session, ds: DataSource, user_id: str | None) -> Job | None:
    """Queues `data_source.cloud_delete` for a database Deployer created (None for connected ones, which
    are only forgotten). The job carries everything it needs: the row is deleted right away."""
    if not is_created(ds):
        return None
    if ds.status == "creating" and jobs.active_job(db, "data_source.cloud_create", data_source_id=ds.id):
        raise conflict("cloud_database_creating", "Wait until AWS has finished creating it, then remove it")
    return jobs.enqueue(
        db,
        type="data_source.cloud_delete",
        params={"connection_id": ds.cloud_connection_id, "state": dict(ds.cloud_state or {}), "name": ds.name},
        project_id=ds.project_id,
        created_by_id=user_id,
    )


def final_snapshot_id(instance: str) -> str:
    return f"{instance}-final-{datetime.now(UTC):%Y%m%d%H%M}"[:255]


@jobs.job_handler("data_source.cloud_delete")
def _job_delete(ctx: jobs.JobContext) -> dict:
    p = ctx.params
    s = p.get("state") or {}
    with ctx.session_factory() as db:
        conn = db.get(CloudConnection, p.get("connection_id")) if p.get("connection_id") else None
        config = cloud.config_of(conn) if conn else None
    if config is None:
        raise jobs.JobError("The AWS connection was removed; delete these by hand: " + "; ".join(resources(s)))
    aws = cloud_aws.client(config)
    if s.get("service") == "dynamodb":
        return _delete_tables(ctx, aws, s)
    removed, snapshot = [], None
    try:
        if s.get("instance_id"):
            snapshot = final_snapshot_id(s["instance_id"])
            started = time.monotonic()
            while True:  # an instance still being modified or backed up refuses deletion for a while
                try:
                    ctx.progress(0.1, "Taking a final snapshot and deleting the database", force=True)
                    if not aws.delete_db_instance(s["instance_id"], snapshot):
                        snapshot = None
                    break
                except CloudError as exc:
                    if exc.code != "InvalidDBInstanceState" or time.monotonic() - started > DELETE_TIMEOUT_S:
                        raise
                    time.sleep(POLL_S)
            while aws.db_instance(s["instance_id"]) is not None:
                if time.monotonic() - started > DELETE_TIMEOUT_S:
                    raise jobs.JobError("AWS is still deleting the database; remove its security group later")
                ctx.progress(0.5, "AWS is deleting the database (after its final snapshot)")
                time.sleep(POLL_S)
            removed.append(f"RDS instance {s['instance_id']}")
        if s.get("group_id"):
            ctx.progress(0.9, "Removing the firewall (security group)", force=True)
            started = time.monotonic()
            while True:  # the deleted instance's network interface holds the group for a few minutes
                try:
                    aws.delete_security_group(s["group_id"])
                    break
                except CloudError as exc:
                    if exc.code != "DependencyViolation" or time.monotonic() - started > GROUP_RELEASE_S:
                        raise
                    time.sleep(POLL_S)
            removed.append(f"Security group {s['group_id']}")
    except CloudError as exc:
        left = [r for r in resources(s) if not any(r.startswith(x) for x in removed)]
        raise jobs.JobError(f"{exc.message} - still in AWS: " + "; ".join(left)) from None
    return {"removed": removed, "final_snapshot": snapshot}


def _backup_status(aws, arn: str) -> str:
    return aws.ddb("DescribeBackup", BackupArn=arn)["BackupDescription"]["BackupDetails"]["BackupStatus"]


def _delete_tables(ctx: jobs.JobContext, aws, s: dict) -> dict:
    """Deletion protection off -> a final on-demand backup (kept, billed for storage until the user deletes
    it) -> waits until it is available -> DeleteTable."""
    removed, backups = [], []
    try:
        for table in s.get("tables") or []:
            ctx.progress(0.1, f"Taking a final backup of {table}", force=True)
            try:
                desc = aws.ddb("DescribeTable", TableName=table)["Table"]
            except CloudError as exc:
                if exc.code != "ResourceNotFoundException":
                    raise
                removed.append(f"DynamoDB table {table}")  # already gone
                continue
            if desc.get("DeletionProtectionEnabled"):  # a retried job already switched it off
                aws.ddb("UpdateTable", TableName=table, DeletionProtectionEnabled=False)
            name = f"{table}-final-{datetime.now(UTC):%Y%m%d%H%M}"
            arn = aws.ddb("CreateBackup", TableName=table, BackupName=name)["BackupDetails"]["BackupArn"]
            started = time.monotonic()
            while _backup_status(aws, arn) != "AVAILABLE":
                if time.monotonic() - started > DELETE_TIMEOUT_S:
                    raise jobs.JobError(f"The final backup of {table} did not finish; the table was not deleted")
                time.sleep(POLL_S)
            backups.append(arn)
            ctx.progress(0.6, f"Deleting the table {table}", force=True)
            aws.ddb("DeleteTable", TableName=table)
            removed.append(f"DynamoDB table {table}")
    except CloudError as exc:
        left = [r for r in resources(s) if not any(r.startswith(x) for x in removed)]
        raise jobs.JobError(f"{exc.message} - still in AWS: " + "; ".join(left)) from None
    return {"removed": removed, "final_backups": backups}


# --- this PC's IP --------------------------------------------------------------------------------


def refresh_ip(db: Session, ds: DataSource, *, aws=None, ip: str | None = None) -> bool:
    """Points the firewall of a database Deployer created at this PC's current public IP (old one
    revoked). Returns True when the rule changed. Caller commits."""
    s = dict(ds.cloud_state or {})
    if not (s.get("created") and s.get("group_id")) or ds.status == "creating":
        return False
    if aws is None:
        conn = db.get(CloudConnection, ds.cloud_connection_id) if ds.cloud_connection_id else None
        if conn is None:
            return False
        aws = cloud_aws.client(cloud.config_of(conn))
    ip = ip or aws.public_ip()
    if s.get("allowed_ip") == ip:
        return False
    port = int(s.get("port") or connections.DEFAULT_PORTS[ds.engine])
    aws.allow_ingress(s["group_id"], port, cidr=f"{ip}/32")
    if s.get("allowed_ip"):
        aws.revoke_ingress(s["group_id"], port, cidr=f"{s['allowed_ip']}/32")
    ds.cloud_state = {**s, "allowed_ip": ip}
    connections.invalidate(ds.id)
    return True


_last_refresh = float("-inf")


def refresh_pc_ips(factory: jobs.SessionFactory, *, force: bool = False) -> int:
    """Scheduler tick: every IP_REFRESH_EVERY_S, follow this PC's public IP on every created database."""
    global _last_refresh
    if not force and time.monotonic() - _last_refresh < IP_REFRESH_EVERY_S:
        return 0
    _last_refresh = time.monotonic()
    changed, ip_by_conn = 0, {}
    with factory() as db:
        sources = db.scalars(
            select(DataSource).where(DataSource.cloud_connection_id.is_not(None), DataSource.deleted_at.is_(None))
        )
        for ds in sources:
            if not is_created(ds) or not (ds.cloud_state or {}).get("group_id"):  # DynamoDB has no firewall
                continue
            try:
                conn = db.get(CloudConnection, ds.cloud_connection_id)
                aws = cloud_aws.client(cloud.config_of(conn))
                ip = ip_by_conn.get(conn.id) or aws.public_ip()
                ip_by_conn[conn.id] = ip
                if refresh_ip(db, ds, aws=aws, ip=ip):
                    changed += 1
                    db.commit()
            except CloudError as exc:
                log.warning("could not update the firewall of %s: %s", ds.id, exc.message)
    return changed


# --- apps ----------------------------------------------------------------------------------------


def app_databases(db: Session, app: App) -> tuple[list[dict], list[str]]:
    """The project's cloud databases an `aws_app` / `firebase_app` with database access gets (same cloud
    connection, so the same account and region / Firebase project), as `{name, engine, config, database_name,
    state}`, plus log notes."""
    if app.target not in cloud.DATABASE_TARGETS or not app.database_access:
        return [], []
    out, notes = [], []
    sources = db.scalars(
        select(DataSource)
        .where(
            DataSource.project_id == app.project_id,
            DataSource.cloud_connection_id.is_not(None),
            DataSource.deleted_at.is_(None),
        )
        .order_by(DataSource.name)
    )
    for ds in sources:
        if ds.cloud_connection_id != app.cloud_connection_id:
            notes.append(f"Database '{ds.name}' is in another cloud account: not given to this app")
        elif ds.status == "creating":
            notes.append(f"Database '{ds.name}' is still being created: deploy again once it is ready")
        else:
            state = dict(ds.cloud_state or {})
            # DynamoDB / Firestore / Realtime Database: no credentials; the app's own cloud identity is allowed in.
            config = (
                {"region": state.get("region"), "tables": state.get("tables") or []}
                if ds.engine == dynamo.ENGINE
                else {"project_id": state.get("project_id"), "database": firestore.database_of(ds)}
                if ds.engine == firestore.ENGINE
                else {"project_id": state.get("project_id"), "database": state.get("instance"), "url": rtdb.url_of(ds)}
                if ds.engine == rtdb.ENGINE
                else connections.load_config(ds)
            )
            out.append(
                {
                    "name": ds.name,
                    "kind": ds.kind,
                    "engine": ds.engine,
                    "config": config,
                    "database_name": ds.database_name,
                    "state": state,
                }
            )
    return out, notes
