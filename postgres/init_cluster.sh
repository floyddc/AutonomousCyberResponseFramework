#!/bin/bash
set -euo pipefail

export PGPASSWORD="${POSTGRES_PASSWORD}"
ready=0

for attempt in $(seq 1 90); do
    if recovery_state=$(
        psql \
            --no-psqlrc \
            --host=postgres \
            --port=5432 \
            --username="${POSTGRES_USER}" \
            --dbname=postgres \
            --tuples-only \
            --no-align \
            --command="SELECT pg_is_in_recovery()" \
            2>/dev/null
    ) && [[ "${recovery_state}" == "f" ]]; then
        ready=1
        break
    fi
    echo "Waiting for a writable PostgreSQL primary (${attempt}/90)..."
    sleep 2
done

if [[ "${ready}" -ne 1 ]]; then
    echo "No writable PostgreSQL primary became available; database initialization failed." >&2
    exit 1
fi

incident_db_exists=$(
    psql \
        --no-psqlrc \
        --host=postgres \
        --port=5432 \
        --username="${POSTGRES_USER}" \
        --dbname=postgres \
        --tuples-only \
        --no-align \
        --command="SELECT 1 FROM pg_database WHERE datname = 'incident_registry'"
)
if [[ "${incident_db_exists}" != "1" ]]; then
    psql \
        --no-psqlrc \
        --set=ON_ERROR_STOP=1 \
        --host=postgres \
        --port=5432 \
        --username="${POSTGRES_USER}" \
        --dbname=postgres \
        --command="CREATE DATABASE incident_registry"
fi

for schema_file in /init/00*.sql; do
    echo "Applying ${schema_file}..."
    psql \
        --no-psqlrc \
        --set=ON_ERROR_STOP=1 \
        --host=postgres \
        --port=5432 \
        --username="${POSTGRES_USER}" \
        --dbname=incident_registry \
        --file="${schema_file}"
done

echo "PostgreSQL database initialization completed."
