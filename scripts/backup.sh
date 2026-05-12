#!/usr/bin/env bash
# Dump the tacacs-web Postgres database to a timestamped pg_dump custom-format file.
#
# The dump is encrypted-at-rest at the column level (see ADR-0004), so the dump
# file alone is unrecoverable without the master key. Back up both:
#   * the dump file produced by this script
#   * the master-key file (./secrets/master.key by default)
#
# Usage:  ./scripts/backup.sh [output-dir]
# Default output dir: ./backups
set -euo pipefail

cd "$(dirname "$0")/.."

OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${OUT_DIR}/tacacs-${TS}.dump"

DB_USER="${POSTGRES_USER:-tacacs}"
DB_NAME="${POSTGRES_DB:-tacacs}"

echo "Dumping ${DB_NAME} as ${DB_USER} -> ${OUT_FILE}"
docker compose --project-directory docker exec -T db \
    pg_dump -Fc -U "${DB_USER}" -d "${DB_NAME}" \
    > "${OUT_FILE}"

echo "Wrote $(wc -c < "${OUT_FILE}") bytes to ${OUT_FILE}"
echo
echo "REMINDER: also back up the master key (secrets/master.key)."
echo "Without it, this dump is unrecoverable."
