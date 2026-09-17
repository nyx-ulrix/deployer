# Deployer control-plane API (FastAPI).
# Debian bookworm: the MariaDB client packages below come from MariaDB's bookworm repository.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system --gid 10001 deployer \
    && useradd --system --uid 10001 --gid deployer --home-dir /app --no-create-home deployer

# Backup tools (docs/BACKUPS.md): MariaDB 11.8 client (mariadb, mariadb-dump, mariadb-binlog) from the
# official MariaDB apt repository (signing key checked by fingerprint) and MongoDB Database Tools
# (mongodump, mongorestore) from the official .deb, checked against a pinned SHA-256.
ARG MARIADB_SERIES=11.8
ARG MARIADB_SIGNER_FINGERPRINT=177F4010FE56CA3336300305F1656F24C74CD1D8
ARG MONGO_TOOLS_VERSION=100.17.0
ARG MONGO_TOOLS_SHA256_AMD64=101eb691713880ad2ece723ce4a655e81c6c026328d8e1cfd84aef687d4681b4
ARG TARGETARCH
RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    if [ "$arch" != "amd64" ]; then echo "MongoDB Database Tools for Debian 12 are only published for amd64" >&2; exit 1; fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
    install -d -m 0755 /etc/apt/keyrings; \
    curl -fsSL https://mariadb.org/mariadb_release_signing_key.pgp -o /tmp/mariadb.pgp; \
    gpg --show-keys --with-colons /tmp/mariadb.pgp | grep -q "^fpr:::::::::${MARIADB_SIGNER_FINGERPRINT}:"; \
    gpg --dearmor < /tmp/mariadb.pgp > /etc/apt/keyrings/mariadb.gpg; \
    echo "deb [signed-by=/etc/apt/keyrings/mariadb.gpg] https://dlm.mariadb.com/repo/mariadb-server/${MARIADB_SERIES}/repo/debian bookworm main" \
        > /etc/apt/sources.list.d/mariadb.list; \
    curl -fsSL "https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian12-x86_64-${MONGO_TOOLS_VERSION}.deb" \
        -o /tmp/mongo-tools.deb; \
    echo "${MONGO_TOOLS_SHA256_AMD64}  /tmp/mongo-tools.deb" | sha256sum -c -; \
    apt-get update; \
    apt-get install -y --no-install-recommends mariadb-client /tmp/mongo-tools.deb; \
    apt-get purge -y --auto-remove curl gnupg; \
    rm -rf /var/lib/apt/lists/* /tmp/mariadb.pgp /tmp/mongo-tools.deb; \
    mariadb-dump --version; mariadb-binlog --version; mongodump --version; mongorestore --version

# Backup store (the `backups` volume). Owned by the non-root user so a fresh volume is writable.
RUN mkdir -p /backups && chown deployer:deployer /backups && chmod 0700 /backups
ENV BACKUP_DIR=/backups

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# Tolerate CRLF checkouts on Windows.
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod 0755 /usr/local/bin/docker-entrypoint.sh

# Mount point of the `tunnel_state` volume shared with the tunnel sidecar (docs/REMOTE_ACCESS.md).
# Owned by uid 10001 so a fresh volume is writable whichever container initialises it first.
RUN mkdir -p /tunnel && chown deployer:deployer /tunnel && chmod 0700 /tunnel

USER deployer

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=4); sys.exit(0)" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
