#!/usr/bin/env bash
# Restore a tacacs-web Postgres dump produced by ./scripts/backup.sh.
#
# Destructive operation: this drops the existing database content. The stack
# must run with the same MASTER_KEY that was active at backup time (docker/.env
# or your Portainer stack env) — otherwise the restored ciphertext is unreadable.
#
# Usage:  ./scripts/restore.sh path/to/tacacs-YYYYMMDDTHHMMSSZ.dump
set -euo pipefail

if [[ "${1-}" == "" || "${1-}" == "-h" || "${1-}" == "--help" ]]; then
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
fi

DUMP_FILE="$1"
[[ -f "$DUMP_FILE" ]] || { echo "No such file: $DUMP_FILE" >&2; exit 2; }

cd "$(dirname "$0")/.."

DB_USER="${POSTGRES_USER:-tacacs}"
DB_NAME="${POSTGRES_DB:-tacacs}"

echo "About to restore ${DUMP_FILE} into database ${DB_NAME}."
echo "This will DROP and RECREATE the schema. Type the database name to confirm:"
read -r CONFIRM
[[ "$CONFIRM" == "$DB_NAME" ]] || { echo "Aborted." >&2; exit 3; }

# Stop the backend so nothing is writing while we restore.
docker compose --project-directory docker stop backend tac_plus-ng nginx

docker compose --project-directory docker exec -T db \
    psql -U "${DB_USER}" -d postgres -c "DROP DATABASE IF EXISTS \"${DB_NAME}\";"
docker compose --project-directory docker exec -T db \
    psql -U "${DB_USER}" -d postgres -c "CREATE DATABASE \"${DB_NAME}\";"

docker compose --project-directory docker exec -T db \
    pg_restore -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-privileges \
    < "${DUMP_FILE}"

docker compose --project-directory docker start backend tac_plus-ng nginx

echo "Restore complete. Verify with: docker compose logs -f backend"
