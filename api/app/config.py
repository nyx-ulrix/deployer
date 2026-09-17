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
