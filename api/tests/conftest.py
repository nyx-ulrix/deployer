"""Shared pytest fixtures for the Deployer API.

Environment (set here, before any `app` import):
- SQLite file database via `DATABASE_URL_OVERRIDE` (set `DEPLOYER_TEST_DATABASE_URL` to use another
  database, e.g. a throwaway MariaDB). Tables are created once per session and emptied before every
  test; SQLite foreign keys are enforced (like InnoDB).
- `JWT_SECRET` / `MASTER_KEY` freshly generated; `PUBLIC_URL=http://localhost:8080`; OAuth apps unset;
  `ALLOW_SIGNUP=false`; `MANAGED_MONGODB_ENABLED=false`.
- Redis is fakeredis (`app.redis_client.set_redis`), flushed before every test.
- Password hashing uses cheap argon2id parameters.

Fixtures:
- `client`               – `fastapi.testclient.TestClient` for the app (base URL http://testserver; call `/v1/...`).
- `db`                   – a SQLAlchemy `Session` on the test database. It is separate from the
                           request sessions: call `db.expire_all()` before re-reading rows changed by the API.
- `fake_redis`           – the fakeredis client in use.
- `make_user(email=None, password=DEFAULT_PASSWORD, *, owner=False, display_name=None, active=True)`
                         – inserts a committed `User` (email auto-generated when None).
- `owner`                – the instance owner user (`owner@example.com`, DEFAULT_PASSWORD).
- `auth_headers(user)`   – `{"Authorization": "Bearer <access token>"}` for a user.
- `owner_headers`        – `auth_headers(owner)`.
- `login(email, password=DEFAULT_PASSWORD)` – POSTs /v1/auth/login with `client`, asserts 200 and
                           returns the JSON AuthResponse (the refresh cookie lands in `client.cookies`).
- `make_project(owner, name="Test Project", *, members=None)` – inserts a committed `Project` with
                           `owner` as owner member; `members` is `{User: role}`.
- `set_setting(key, value)` – stores an instance setting (see services.instance_settings.KNOWN_KEYS).
- `fake_provisioning`    – replaces `app.services.provisioning` with a fake whose
                           `provision_managed_source` inserts a DataSource row and records calls in
                           `.calls`; set `.fail_kind = "sql" | "nosql"` to make that kind raise ApiError.
"""

import base64
import os
import secrets
import sys
import tempfile
import types
from pathlib import Path

import pytest

_tmpdir = Path(tempfile.mkdtemp(prefix="deployer-tests-"))
os.environ["DATABASE_URL_OVERRIDE"] = os.environ.get("DEPLOYER_TEST_DATABASE_URL") or (
    f"sqlite:///{(_tmpdir / 'test.db').as_posix()}"
)
os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
os.environ["MASTER_KEY"] = base64.b64encode(os.urandom(32)).decode()
os.environ["PUBLIC_URL"] = "http://localhost:8080"
os.environ["REDIS_URL"] = "redis://localhost:1/0"
os.environ["MANAGED_MONGODB_ENABLED"] = "false"
os.environ["ALLOW_SIGNUP"] = "false"
for _key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"):
    os.environ[_key] = ""

import fakeredis  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from app import redis_client  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, get_engine, get_sessionmaker  # noqa: E402
from app.services import passwords  # noqa: E402

get_settings.cache_clear()
get_engine.cache_clear()
get_sessionmaker.cache_clear()

import app.models  # noqa: E402,F401  (register tables)
from app.models import Project, ProjectMember, User  # noqa: E402

DEFAULT_PASSWORD = "correct-horse-battery"

passwords.hasher = PasswordHasher(time_cost=1, memory_cost=512, parallelism=1)


@event.listens_for(Engine, "connect")
def _sqlite_fk_pragma(dbapi_connection, _record):
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    engine = get_engine()
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(scope="session")
def fake_redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    redis_client.set_redis(client)
    return client


@pytest.fixture(autouse=True)
def _clean_state(_schema, fake_redis):
    engine = get_engine()
    with engine.begin() as conn:
        if engine.dialect.name == "mysql":
            conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        if engine.dialect.name == "mysql":
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    fake_redis.flushall()
    redis_client.set_redis(fake_redis)
    yield


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def factory(
        email: str | None = None,
        password: str | None = DEFAULT_PASSWORD,
        *,
        owner: bool = False,
        display_name: str | None = None,
        active: bool = True,
    ) -> User:
        counter["n"] += 1
        user = User(
            email=(email or f"user{counter['n']}-{secrets.token_hex(3)}@example.com").lower(),
            display_name=display_name,
            password_hash=passwords.hash_password(password) if password else None,
            is_instance_owner=owner,
            is_active=active,
        )
        db.add(user)
        db.commit()
        return user

    return factory


@pytest.fixture
def owner(make_user) -> User:
    return make_user("owner@example.com", owner=True, display_name="Owner")


@pytest.fixture
def auth_headers():
    from app.services.tokens import create_access_token

    def factory(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user)}"}

    return factory


@pytest.fixture
def owner_headers(owner, auth_headers) -> dict[str, str]:
    return auth_headers(owner)


@pytest.fixture
def login(client):
    def factory(email: str, password: str = DEFAULT_PASSWORD) -> dict:
        resp = client.post("/v1/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        return resp.json()

    return factory


@pytest.fixture
def make_project(db):
    def factory(owner: User, name: str = "Test Project", *, members: dict[User, str] | None = None) -> Project:
        from app.services.slugs import unique_slug

        project = Project(name=name, slug=unique_slug(db, name), owner_id=owner.id)
        db.add(project)
        db.flush()
        db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
        for user, role in (members or {}).items():
            db.add(ProjectMember(project_id=project.id, user_id=user.id, role=role))
        db.commit()
        return project

    return factory


@pytest.fixture
def set_setting(db):
    from app.services.instance_settings import set_value

    def factory(key: str, value) -> None:
        set_value(db, key, value)
        db.commit()

    return factory


@pytest.fixture
def fake_provisioning(monkeypatch):
    from app.crypto import encrypt_json
    from app.errors import ApiError
    from app.models import DataSource

    module = types.ModuleType("app.services.provisioning")
    module.calls = []
    module.dropped = []
    module.fail_kind = None

    def provision_managed_source(db, project, kind, name):
        module.calls.append((project.id, kind, name))
        if module.fail_kind == kind:
            raise ApiError(503, "provisioning_failed", f"Could not provision {kind}")
        return DataSource(
            project_id=project.id,
            name=name,
            kind=kind,
            engine="mariadb" if kind == "sql" else "mongodb",
            mode="managed",
            database_name=f"p_{project.slug.replace('-', '_')}",
            config_encrypted=encrypt_json({}),
        )

    def drop_managed_source(db, data_source):
        module.dropped.append((data_source.project_id, data_source.kind, data_source.name))

    module.provision_managed_source = provision_managed_source
    module.drop_managed_source = drop_managed_source
    monkeypatch.setitem(sys.modules, "app.services.provisioning", module)
    return module
