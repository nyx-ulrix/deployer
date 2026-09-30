"""A-115: a managed-source row naming the platform or a system database never drops, creates or
re-grants it on the shared servers, and an import can't pick such a name."""

import pytest

from app.config import get_settings
from app.services import provisioning


def _no_root(*_a, **_k):
    raise AssertionError("root connection must not be opened for a reserved database")


@pytest.mark.parametrize("name", ["deployer", "mysql", "sys", "information_schema", "admin"])
def test_reserved_databases_are_refused_before_touching_the_server(monkeypatch, name):
    monkeypatch.setattr(provisioning, "mariadb_root_engine", _no_root)
    monkeypatch.setattr(provisioning, "mongo_root_client", _no_root)
    for call in (
        lambda: provisioning.drop_mariadb_database(name, "u_0123456789ab"),
        lambda: provisioning.drop_mongo_database(name, "u_0123456789ab"),
        lambda: provisioning.create_mariadb_database(name, "u_0123456789ab", "a" * 32),
        lambda: provisioning.set_mariadb_read_only(name, "u_0123456789ab", True),
    ):
        with pytest.raises(ValueError, match="reserved"):
            call()


def test_configured_platform_database_is_reserved(monkeypatch):
    monkeypatch.setattr(get_settings(), "mariadb_database", "platform_db")
    monkeypatch.setattr(provisioning, "mariadb_root_engine", _no_root)
    with pytest.raises(ValueError, match="reserved"):
        provisioning.drop_mariadb_database("platform_db", None)


def test_pick_never_returns_a_reserved_preferred_name():
    name = provisioning._pick_database_name("shop", "mysql", lambda _n: False)
    assert name.startswith("p_shop_")


def test_legacy_reserved_rows_are_skipped_not_retried(monkeypatch):
    """A row created before A-115 with a reserved name: deleting/purging it or cleaning up an old move
    copy must neither touch the server nor fail forever as "unreachable"."""
    from types import SimpleNamespace

    from app.services import connections, device_moves

    monkeypatch.setattr(provisioning, "mariadb_root_engine", _no_root)
    monkeypatch.setattr(provisioning, "mongo_root_client", _no_root)
    monkeypatch.setattr(connections, "device_removed", lambda _ds: False)
    monkeypatch.setattr(connections, "load_config", lambda _ds: {"username": "u_0123456789ab"})
    for kind in ("sql", "nosql"):
        ds = SimpleNamespace(id="ds1", mode="managed", device_id=None, kind=kind, database_name="test")
        provisioning.drop_managed_source(None, ds)
        device_moves.drop_copy(kind, None, "mysql", None)
