import ctypes
import os
import sys
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration, read from environment variables (see deploy/.env.example).

    Values that the instance owner can change at runtime (public URL, OAuth apps, signup policy)
    live in the `instance_settings` table; the env values here are only their initial defaults.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    public_url: str = "http://localhost:8080"

    # Platform metadata database (MariaDB). The root account is used to provision managed databases.
    mariadb_host: str = "mariadb"
    mariadb_port: int = 3306
    mariadb_database: str = "deployer"
    mariadb_user: str = "deployer"
    mariadb_password: str = ""
    mariadb_root_password: str = ""
    # A-025: connection cap for each managed database user. MariaDB allows 150 connections in total
    # and the platform user shares them, so one leaky app must not be able to take them all (0 = no cap).
    managed_db_max_user_connections: int = 20

    # Managed MongoDB.
    mongo_host: str = "mongodb"
    mongo_port: int = 27017
    mongo_root_username: str = "admin"
    mongo_root_password: str = ""

    # False on CPUs without AVX (MongoDB 5+ needs it): the installer leaves the mongodb container
    # out and projects can only attach external MongoDB (e.g. Atlas).
    managed_mongodb_enabled: bool = True

    redis_url: str = "redis://redis:6379/0"

    jwt_secret: str = ""
    # base64-encoded 32 bytes; encrypts secrets stored in the database.
    master_key: str = ""

    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_days: int = 30

    # Optional initial OAuth apps (the setup wizard can set these instead).
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    allow_signup: bool = False

    # docs/REMOTE_ACCESS.md: shared volume with the tunnel sidecar (desired.json / status.json), and
    # the host port Caddy is published on (public_url falls back to http://localhost:<port>).
    tunnel_state_dir: str = "/tunnel"
    deployer_http_port: int = 0

    # docs/DEPLOYMENTS.md (worker only): generated Caddy site files (`caddy_apps` volume), the compose
    # network app containers join, their memory limit, and where checkouts are built (default: tmp).
    caddy_apps_dir: str = "/etc/caddy/apps"
    # docs/COHOSTING.md "Ids" (worker only): MariaDB's conf.d (`mariadb_conf` volume); co-hosting writes
    # its auto_increment step/offset there so they survive MariaDB restarts. Empty = runtime only.
    mariadb_conf_dir: str = ""
    app_network: str = "deployer_apps"  # only caddy and the worker share it (A-019)
    app_db_network: str = "deployer_backend"  # joined only by apps with database access
    app_mem_limit: str = "512m"
    app_build_dir: str = ""
    # docs/MONITORING.md: containers of this compose project (plus deployed apps) are sampled.
    compose_project: str = "deployer"

    # Test hook: use an explicit SQLAlchemy URL instead of MariaDB (e.g. sqlite in unit tests).
    database_url_override: str = ""

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"mysql+pymysql://{self.mariadb_user}:{self.mariadb_password}"
            f"@{self.mariadb_host}:{self.mariadb_port}/{self.mariadb_database}?charset=utf8mb4"
        )

    @property
    def mongo_root_uri(self) -> str:
        return (
            f"mongodb://{self.mongo_root_username}:{self.mongo_root_password}"
            f"@{self.mongo_host}:{self.mongo_port}/?authSource=admin"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Settings fields that hold secrets (their env var names): removed from os.environ by seal_process().
SECRET_ENV = (
    "MARIADB_PASSWORD",
    "MARIADB_ROOT_PASSWORD",
    "MONGO_ROOT_PASSWORD",
    "REDIS_URL",
    "JWT_SECRET",
    "MASTER_KEY",
    "GOOGLE_CLIENT_SECRET",
    "GITHUB_CLIENT_SECRET",
)
PR_SET_DUMPABLE = 4


def seal_process() -> None:
    """SECURITY.md "Query console": loads the Settings, then drops the secrets from `os.environ` (no
    child process inherits them) and marks the process non-dumpable. The kernel then makes
    /proc/<pid>/environ, /mem, /fd... root-owned and refuses ptrace, so another process of the same
    uid (the mongosh query shell) cannot read the secrets the process started with. Linux only."""
    get_settings()
    for key in SECRET_ENV:
        os.environ.pop(key, None)
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE, 0) failed")
