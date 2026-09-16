#!/bin/sh
# Runs database migrations (retrying while MariaDB starts), then the API server.
set -eu

attempts="${MIGRATION_ATTEMPTS:-30}"
i=1
until alembic upgrade head; do
    if [ "$i" -ge "$attempts" ]; then
        echo "Database migrations failed after $attempts attempts" >&2
        exit 1
    fi
    echo "Migrations failed (attempt $i/$attempts); retrying in 2s..." >&2
    i=$((i + 1))
    sleep 2
done

exec "$@"
