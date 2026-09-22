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
# Query console (docs/QUERY_CONSOLE.md): MongoDB Shell (`mongosh`) from the official .deb
# (https://downloads.mongodb.com/compass/, same file as the GitHub release), pinned SHA-256.
# Push-to-deploy (docs/DEPLOYMENTS.md, worker only): git, the Docker CLI and BuildKit plugin from
# Docker's apt repository (signing key checked by fingerprint). The image stays non-root; compose
# switches only the worker service to root for the Docker socket.
ARG MARIADB_SERIES=11.8
ARG MARIADB_SIGNER_FINGERPRINT=177F4010FE56CA3336300305F1656F24C74CD1D8
ARG DOCKER_SIGNER_FINGERPRINT=9DC858229FC7DD38854AE2D88D81803C0EBFCD88
ARG MONGO_TOOLS_VERSION=100.17.0
ARG MONGO_TOOLS_SHA256_AMD64=101eb691713880ad2ece723ce4a655e81c6c026328d8e1cfd84aef687d4681b4
ARG MONGOSH_VERSION=2.11.1
ARG MONGOSH_SHA256_AMD64=643495f22efd6c29caea486780e0c8b20e98529d73d539a48e7f460e1a1c2b76
ARG TARGETARCH
RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    if [ "$arch" != "amd64" ]; then echo "MongoDB Database Tools and mongosh .deb packages are only installed for amd64" >&2; exit 1; fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
    install -d -m 0755 /etc/apt/keyrings; \
    curl -fsSL https://mariadb.org/mariadb_release_signing_key.pgp -o /tmp/mariadb.pgp; \
    gpg --show-keys --with-colons /tmp/mariadb.pgp | grep -q "^fpr:::::::::${MARIADB_SIGNER_FINGERPRINT}:"; \
    gpg --dearmor < /tmp/mariadb.pgp > /etc/apt/keyrings/mariadb.gpg; \
    echo "deb [signed-by=/etc/apt/keyrings/mariadb.gpg] https://dlm.mariadb.com/repo/mariadb-server/${MARIADB_SERIES}/repo/debian bookworm main" \
        > /etc/apt/sources.list.d/mariadb.list; \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /tmp/docker.pgp; \
    gpg --show-keys --with-colons /tmp/docker.pgp | grep -q "^fpr:::::::::${DOCKER_SIGNER_FINGERPRINT}:"; \
    gpg --dearmor < /tmp/docker.pgp > /etc/apt/keyrings/docker.gpg; \
    echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list; \
    curl -fsSL "https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian12-x86_64-${MONGO_TOOLS_VERSION}.deb" \
        -o /tmp/mongo-tools.deb; \
    echo "${MONGO_TOOLS_SHA256_AMD64}  /tmp/mongo-tools.deb" | sha256sum -c -; \
    curl -fsSL "https://downloads.mongodb.com/compass/mongodb-mongosh_${MONGOSH_VERSION}_amd64.deb" \
        -o /tmp/mongosh.deb; \
    echo "${MONGOSH_SHA256_AMD64}  /tmp/mongosh.deb" | sha256sum -c -; \
    apt-get update; \
    apt-get install -y --no-install-recommends mariadb-client /tmp/mongo-tools.deb /tmp/mongosh.deb \
        git docker-ce-cli docker-buildx-plugin; \
    apt-get purge -y --auto-remove curl gnupg; \
    rm -rf /var/lib/apt/lists/* /tmp/mariadb.pgp /tmp/docker.pgp /tmp/mongo-tools.deb /tmp/mongosh.deb; \
    mariadb-dump --version; mariadb-binlog --version; mongodump --version; mongorestore --version; \
    mongosh --version; git --version; docker --version; docker buildx version

# mongosh global settings (docs/QUERY_CONSOLE.md): no telemetry, no update checks, no log files.
# Each console run gets a private temporary HOME, so nothing else is ever written or read.
RUN printf 'mongosh:\n  forceDisableTelemetry: true\n  disableLogging: true\n  updateURL: ""\n' \
        > /etc/mongosh.conf \
    && chmod 0644 /etc/mongosh.conf

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
