"""docs/CLOUD.md "C2-1": connections to RDS / Aurora verify the server certificate against the vendored RDS CA
bundle, with the host name; every other external source keeps its TLS settings."""

import ssl
from pathlib import Path

import psycopg
import pymysql
import pytest
from sqlalchemy import Engine, event

from app.services import connections, deployments

INSTANCE = "deployer-shop-db.abc123xyz.eu-west-1.rds.amazonaws.com"
CLUSTER = "shop.cluster-ro-abc123xyz.us-east-1.rds.amazonaws.com"
BASE = {"port": 3306, "username": "deployer", "password": "fake-rds-password", "database": "shop", "tls": True}


def _bundle_certs() -> int:
    return Path(connections.RDS_CA_BUNDLE).read_text().count("BEGIN CERTIFICATE")


@pytest.fixture
def driver_kwargs():
    """What SQLAlchemy hands the DB driver's connect(): captured, then the connection is stopped."""
    seen: dict = {}

    def grab(dialect, conn_rec, cargs, cparams):
        seen.clear()
        seen.update(cparams)
        raise RuntimeError("stopped before the network")

    event.listen(Engine, "do_connect", grab)
    yield seen
    event.remove(Engine, "do_connect", grab)


@pytest.mark.parametrize("host", [INSTANCE, CLUSTER, INSTANCE.upper() + "."])
def test_rds_mysql_verifies_certificate_and_host_name(driver_kwargs, host):
    ok, message, _ = connections.try_sql("mysql", {**BASE, "host": host, "tls_verify": False})  # cloud_db's config
    assert not ok and "fake-rds-password" not in message
    ctx = driver_kwargs["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True
    # Only the RDS CAs are trusted for it (not the system store), and all of them load.
    assert ctx.cert_store_stats()["x509_ca"] == _bundle_certs() > 50
    assert all(("organizationalUnitName", "Amazon RDS") in [f for (f,) in c["subject"]] for c in ctx.get_ca_certs())


def test_rds_postgres_uses_verify_full_with_the_bundle(driver_kwargs):
    ok, _, _ = connections.try_sql("postgresql", {**BASE, "host": INSTANCE, "port": 5432, "tls_verify": False})
    assert not ok
    assert driver_kwargs["sslmode"] == "verify-full"
    assert driver_kwargs["sslrootcert"] == connections.RDS_CA_BUNDLE and Path(connections.RDS_CA_BUNDLE).is_file()


@pytest.mark.parametrize(
    "host",
    [
        "db.example.com",
        "shop-proxy.proxy-abc123xyz.eu-west-1.rds.amazonaws.com",  # RDS Proxy: public ACM certificate
        "shop.abc123xyz.us-gov-west-1.rds.amazonaws.com",  # GovCloud: another bundle
        "shop.abc123xyz.cn-north-1.rds.amazonaws.com.cn",
        "evil.example.com/.abc.eu-west-1.rds.amazonaws.com",
    ],
)
def test_other_hosts_keep_their_settings(host):
    cfg = {**BASE, "host": host}
    assert connections.rds_ca(cfg) is None
    assert connections._connect_args("postgresql", cfg)["sslmode"] == "require"
    ctx = connections._connect_args("mysql", cfg)["ssl"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True  # the system store, as before
    insecure = connections._connect_args("mysql", {**cfg, "tls_verify": False})["ssl"]
    assert insecure.verify_mode == ssl.CERT_NONE and insecure.check_hostname is False


def test_tls_off_stays_off_even_on_rds():
    cfg = {**BASE, "host": INSTANCE, "tls": False}
    assert "ssl" not in connections._connect_args("mysql", cfg)
    assert connections._connect_args("postgresql", cfg)["sslmode"] == "prefer"


def test_app_runner_env_names_the_ca_for_rds_only():
    env = deployments.source_env("shop db", "sql", "mysql", {**BASE, "host": INSTANCE}, "shop")
    assert env["DEPLOYER_DB_SHOP_DB_SSL_CA_URL"] == connections.RDS_CA_URL
    assert "ssl=true" in env["DEPLOYER_DB_SHOP_DB_URL"]  # unchanged: works without the CA file
    other = deployments.source_env("shop db", "sql", "mysql", {**BASE, "host": "db.example.com"}, "shop")
    assert "DEPLOYER_DB_SHOP_DB_SSL_CA_URL" not in other


def test_certificate_failures_get_a_plain_hint():
    cfg = {**BASE, "host": INSTANCE}
    my = pymysql.err.OperationalError(
        2003,
        f"Can't connect to MySQL server on '{INSTANCE}' ([SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed)",
    )
    assert connections.friendly_error("sql", my, cfg, []).startswith(
        "The server's TLS certificate could not be verified"
    )
    pg = psycopg.OperationalError(f'server certificate for "x.example.com" does not match host name "{INSTANCE}"')
    assert "rds-ca-rsa2048-g1" in connections.friendly_error("sql", pg, cfg, [])
