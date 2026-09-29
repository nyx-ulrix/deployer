"""A-025: managed MariaDB users get a connection cap, so one app can't use up the connections the
platform database shares with it."""

from contextlib import contextmanager

from app.config import get_settings
from app.services import provisioning


class FakeConn:
    def __init__(self, users=()):
        self.sql: list[str] = []
        self.users = users

    def exec_driver_sql(self, sql, params=None):
        self.sql.append(sql)
        rows = [(u,) for u in self.users] if sql.startswith("SELECT User") else []
        return type("R", (), {"fetchall": lambda _self: rows})()


def _patch_engine(monkeypatch, conn):
    @contextmanager
    def connect():
        yield conn

    monkeypatch.setattr(provisioning, "mariadb_root_engine", lambda: type("E", (), {"connect": staticmethod(connect)}))


def test_new_managed_user_is_created_with_the_cap(monkeypatch):
    conn = FakeConn()
    _patch_engine(monkeypatch, conn)
    provisioning.create_mariadb_database("p_shop_abc123", "u_0123456789ab", "a" * 32)
    create = next(s for s in conn.sql if s.startswith("CREATE USER"))
    assert create.endswith("WITH MAX_USER_CONNECTIONS 20")


def test_existing_managed_users_are_capped_and_others_left_alone(monkeypatch):
    monkeypatch.setattr(get_settings(), "managed_db_max_user_connections", 7)
    conn = FakeConn(users=["u_0123456789ab", "deployer", "root"])
    _patch_engine(monkeypatch, conn)
    assert provisioning.cap_mariadb_users() == 1
    assert conn.sql[1:] == ["ALTER USER 'u_0123456789ab'@'%%' WITH MAX_USER_CONNECTIONS 7"]
