#!/bin/bash
# Deployer MongoDB entrypoint wrapper (docs/BACKUPS.md).
#
# Point-in-time recovery needs an oplog, so the managed MongoDB runs as a single-node replica set
# (`rs0`). Replica-set members authenticate each other with a keyfile; it is derived from
# MONGO_INITDB_ROOT_PASSWORD so nothing extra has to be generated, stored or backed up. The file is
# written to tmpfs-backed /tmp on every start (owner mongodb, mode 0400) and never leaves the
# container. The replica set itself is initiated by the Deployer API/worker on startup
# (app.services.backup_engine.ensure_mongo_replica_set), which also upgrades existing installs.
set -euo pipefail

keyfile="${DEPLOYER_MONGO_KEYFILE:-/tmp/deployer-mongo-keyfile}"
if [ -z "${MONGO_INITDB_ROOT_PASSWORD:-}" ]; then
    echo "deployer: MONGO_INITDB_ROOT_PASSWORD is required for the replica-set keyfile" >&2
    exit 1
fi
umask 077
# 64 hex chars from SHA-256, twice with different labels -> 128 base64-alphabet characters.
{
    printf '%s' "deployer-mongo-keyfile-v1:a:${MONGO_INITDB_ROOT_PASSWORD}" | sha256sum | cut -d' ' -f1
    printf '%s' "deployer-mongo-keyfile-v1:b:${MONGO_INITDB_ROOT_PASSWORD}" | sha256sum | cut -d' ' -f1
} | tr -d '\n' > "${keyfile}.tmp"
mv -f "${keyfile}.tmp" "$keyfile"
chown mongodb:mongodb "$keyfile"
chmod 0400 "$keyfile"

exec /usr/local/bin/docker-entrypoint.sh "$@"
