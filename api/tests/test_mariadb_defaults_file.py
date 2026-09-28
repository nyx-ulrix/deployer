"""The MariaDB credentials file is shared by mariadb-dump, mariadb and mariadb-binlog. Its `[client]`
group must only contain options every one of those tools accepts (or `loose-` prefixed ones), otherwise
mariadb-binlog exits with "unknown variable" and binlog archiving (point-in-time recovery) breaks."""

from app.services import backup_engine

UNIVERSAL_CLIENT_OPTIONS = {"user", "password", "host", "port", "socket", "protocol"}


def test_client_group_only_has_options_mariadb_binlog_accepts(monkeypatch):
    # Patch the cached Settings: the API lifespan (config.seal_process) removes secrets from os.environ.
    monkeypatch.setattr(backup_engine.get_settings(), "mariadb_root_password", "unit-test-password")
    with backup_engine.mariadb_defaults_file() as cnf:
        lines = [ln.strip() for ln in cnf.read_text(encoding="utf-8").splitlines() if ln.strip()]

    assert lines[0] == "[client]"
    for line in lines[1:]:
        if line.startswith("["):
            break
        name = line.split("=", 1)[0]
        assert name in UNIVERSAL_CLIENT_OPTIONS or name.startswith("loose-"), line
