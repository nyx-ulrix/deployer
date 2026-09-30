"""Fixtures shared by several test modules, registered for every test by `pytest_plugins` in conftest.py.

- `docker`         – FakeDockerCli installed as the app runner's docker; Caddy/build dirs in tmp_path.
- `state_dir`      – tmp_path as the tunnel_state dir (remote access); `fake_cf` – a FakeCloudflare API.
- `providers`      – fake Google/GitHub OAuth endpoints with both providers configured.
- `sqlite_engine`  – a scratch SQLite engine with an `items` table (7 rows).
- `fake_mongosh`   – query_console runs a fake mongosh (FAKE_MONGOSH) instead of the real shell.
- `project_setup`  – project "Shop" with owner/dev/viewer headers and the data-sources base URL.
- `make_source(project, kind="sql", *, config=None, **fields)` – inserts a committed DataSource; the one
                     DataSource factory (plain-function form: `add_source(db, project, ...)`).
"""

import functools
import sys
import textwrap

import pytest
from sqlalchemy import create_engine

from app.config import get_settings
from app.crypto import encrypt_json
from app.models import DataSource
from app.services import app_runner, oauth, query_console
from app.services import cloudflare as cf
from app.services import remote_access as ra
from app.services.oauth import OAuthFlowError
from tests.apps_support import FakeDockerCli
from tests.test_cloudflare_client import FakeCloudflare


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'console.db').as_posix()}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE items "
            "(id INTEGER PRIMARY KEY, name VARCHAR(50), price NUMERIC(10,2), blob BLOB, seen DATETIME)"
        )
        for i in range(1, 8):
            conn.exec_driver_sql("INSERT INTO items (id, name) VALUES (?, ?)", (i, f"item {i}"))
    yield engine
    engine.dispose()


FAKE_MONGOSH = textwrap.dedent(
    r'''
    """A stand-in for mongosh: speaks the wrapper protocol of app/services/query_console.py."""
    import json, os, sys, time

    env = os.environ
    marker = env.get("DEPLOYER_QUERY_MARKER", "")
    uri = env.get("DEPLOYER_QUERY_URI", "")
    with open(env["DEPLOYER_QUERY_FILE"], encoding="utf-8") as fh:
        code = fh.read()
    out = sys.stdout.buffer


    def emit(obj):
        out.write((marker + json.dumps(obj) + "\n").encode("utf-8"))
        out.flush()


    if "unreachable" in uri:
        emit({"phase": "connect", "error": {"name": "MongoNetworkError", "message": "getaddrinfo ENOTFOUND unreachable",
                                            "code": None, "codeName": None}})
        sys.exit(0)
    if code.startswith("sleep"):
        time.sleep(30)
    if code.startswith("flood"):
        chunk = b"x" * 65536
        for _ in range(200):
            out.write(chunk)
        out.flush()
        emit({"phase": "done", "value": 1})
        sys.exit(0)
    if code.startswith("throw"):
        emit({"phase": "error", "error": {"name": "SyntaxError", "message": "Unexpected token (1:15)",
                                          "code": "BABEL_PARSE_ERROR", "codeName": None}})
        sys.exit(0)
    if code.startswith("servererror"):
        emit({"phase": "error", "error": {"name": "MongoServerError", "message": "unknown top level operator: $bad",
                                          "code": 2, "codeName": "BadValue"}})
        sys.exit(0)
    if code.startswith("print"):
        out.write(b"hello\n42\n")
        out.flush()
        sys.stderr.write("DeprecationWarning: something\n")
        sys.stderr.flush()
        emit({"phase": "done", "value": {"n": 7}})
        sys.exit(0)
    if code.startswith("secret"):
        out.write(("connected to " + uri + "\n").encode("utf-8"))
        emit({"phase": "done", "value": {"uri": uri}})
        sys.exit(0)
    if code.startswith("argv"):
        emit({"phase": "done", "value": {"argv": sys.argv, "env": dict(env), "cwd": os.getcwd()}})
        sys.exit(0)
    if code.startswith("crash"):
        sys.stderr.write("boom\n")
        sys.exit(2)
    if code.startswith("scalar"):
        emit({"phase": "done", "value": "str"})
        sys.exit(0)
    if code.startswith("nothing"):
        emit({"phase": "done", "value": None})
        sys.exit(0)
    batch = int(env.get("DEPLOYER_QUERY_BATCH", "0"))
    if code.startswith("exact"):
        batch -= 1
    emit({"phase": "done", "value": [{"_id": {"$oid": "%024x" % i}, "n": i} for i in range(batch)]})
    '''
)


@pytest.fixture
def fake_mongosh(tmp_path, monkeypatch):
    script = tmp_path / "fake_mongosh.py"
    script.write_text(FAKE_MONGOSH, encoding="utf-8")
    monkeypatch.setattr(query_console, "mongosh_command", lambda: [sys.executable, str(script)])
    return script


def mongo_config() -> dict:
    # Built at runtime so no connection string with a password appears in the source (gitleaks).
    return {"uri": "mongodb://" + "app:s3cret-pw" + "@mongo.example:27017/app?authSource=app", "database": "app"}


def sql_config() -> dict:
    return {"host": "db.example", "port": 3306, "username": "app", "password": "pw-" + "x" * 8, "database": "app"}


def add_source(db, project, kind="sql", *, config=None, **fields) -> DataSource:
    """Insert and commit a DataSource: an external mariadb/mongodb source named main-<kind> with status ok and a
    dummy connection config, unless `config` / `fields` (any DataSource column) say otherwise."""
    if config is None:
        config = sql_config() if kind == "sql" else mongo_config()
    values = {
        "name": f"main-{kind}",
        "engine": "mariadb" if kind == "sql" else "mongodb",
        "mode": "external",
        "database_name": "app",
        "status": "ok",
        **fields,
    }
    ds = DataSource(project_id=project.id, kind=kind, config_encrypted=encrypt_json(config), **values)
    db.add(ds)
    db.commit()
    return ds


@pytest.fixture
def make_source(db):
    return functools.partial(add_source, db)


@pytest.fixture
def project_setup(make_user, make_project, auth_headers):
    owner = make_user()
    dev, viewer = make_user(), make_user()
    project = make_project(owner, "Shop", members={dev: "developer", viewer: "viewer"})
    return {
        "project": project,
        "owner": auth_headers(owner),
        "dev": auth_headers(dev),
        "viewer": auth_headers(viewer),
        "base": f"/v1/projects/{project.id}/data-sources",
    }


@pytest.fixture
def docker(tmp_path, monkeypatch):
    fake = FakeDockerCli()
    app_runner.set_docker(fake)
    monkeypatch.setattr(get_settings(), "caddy_apps_dir", str(tmp_path / "apps"))
    monkeypatch.setattr(get_settings(), "app_build_dir", str(tmp_path))
    yield fake
    app_runner.set_docker(None)


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "tunnel_state_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "deployer_http_port", 0)
    monkeypatch.setattr(ra, "_last_write_error", None)
    return tmp_path


@pytest.fixture
def fake_cf(state_dir):
    fake = FakeCloudflare()
    cf.set_transport(fake.transport())
    yield fake
    cf.set_transport(None)


class FakeProviders:
    def __init__(self):
        self.github_user = {"id": 42, "login": "octo", "name": "Octo Cat", "avatar_url": "https://avatars/octo.png"}
        self.github_emails = [
            {"email": "other@example.com", "primary": False, "verified": True},
            {"email": "Octo@Example.com", "primary": True, "verified": True},
        ]
        self.google_info = {
            "sub": "g-123",
            "email": "gina@example.com",
            "email_verified": True,
            "name": "Gina",
            "picture": "https://pics/gina.png",
        }
        self.token_requests: list[tuple[str, dict]] = []

    def post_form(self, url, data):
        self.token_requests.append((url, data))
        if data["code"] == "bad-code":
            raise OAuthFlowError("oauth_failed")
        return {"access_token": "provider-token", "token_type": "bearer"}

    def get_json(self, url, access_token):
        assert access_token == "provider-token"
        return {
            oauth.GITHUB_USER_URL: self.github_user,
            oauth.GITHUB_EMAILS_URL: self.github_emails,
            oauth.GOOGLE_USERINFO_URL: self.google_info,
        }[url]


@pytest.fixture
def providers(monkeypatch, set_setting):
    fake = FakeProviders()
    monkeypatch.setattr(oauth, "_http_post_form", fake.post_form)
    monkeypatch.setattr(oauth, "_http_get_json", fake.get_json)
    for p in ("google", "github"):
        set_setting(f"{p}_client_id", f"{p}-client")
        set_setting(f"{p}_client_secret", f"{p}-secret")
    return fake
