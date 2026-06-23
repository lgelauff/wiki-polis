#!/usr/bin/env bash
# Dump one Polis Postgres container, upload to rclone/B2, then remove the local copy.

set -euo pipefail

CONTAINER="${POLIS_POSTGRES_CONTAINER:-particiapp-docker_postgres_1}"
NAME="${BACKUP_NAME:-prod}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/particiapp-data/postgres-backups}"
RCLONE_REMOTE="${RCLONE_REMOTE:?set RCLONE_REMOTE, e.g. b2:wiki-polis-postgres-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
HEALTHCHECKS_URL="${HEALTHCHECKS_URL:-}"

usage() {
  cat <<'EOF'
Usage: backup_polis_postgres_b2.sh [--container NAME] [--name LABEL]

Required env:
  RCLONE_REMOTE      rclone destination, e.g. b2:wiki-polis-postgres-backups

Optional env:
  BACKUP_DIR         local staging dir (default: ~/particiapp-data/postgres-backups)
  RETENTION_DAYS     remote retention in days (default: 14)
  HEALTHCHECKS_URL   ping URL; /fail is called on error

Examples:
  RCLONE_REMOTE=b2:wiki-polis-postgres-backups ./backup_polis_postgres_b2.sh
  RCLONE_REMOTE=b2:wiki-polis-postgres-backups ./backup_polis_postgres_b2.sh \
    --container wiki-polis-staging_postgres_1 --name staging
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --container)
      CONTAINER="${2:?missing --container value}"
      shift 2
      ;;
    --name)
      NAME="${2:?missing --name value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ping_healthchecks() {
  local suffix="${1:-}"
  if [[ -n "$HEALTHCHECKS_URL" ]]; then
    curl -fsS -m 10 "${HEALTHCHECKS_URL%/}${suffix}" >/dev/null || true
  fi
}

on_error() {
  local status=$?
  [[ -n "${tmpfile:-}" ]] && rm -f "$tmpfile"
  ping_healthchecks "/fail"
  exit "$status"
}
trap on_error ERR

mkdir -p "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
outfile="$BACKUP_DIR/${NAME}-polis-${timestamp}.sql.gz"
tmpfile="${outfile}.tmp"

docker exec "$CONTAINER" pg_dump -U polis -d polis | gzip -c > "$tmpfile"
gzip -t "$tmpfile"
test -s "$tmpfile"
mv "$tmpfile" "$outfile"

rclone copyto "$outfile" "$RCLONE_REMOTE/$NAME/$(basename "$outfile")"
rclone delete --min-age "${RETENTION_DAYS}d" "$RCLONE_REMOTE/$NAME"
rclone rmdirs "$RCLONE_REMOTE/$NAME" >/dev/null 2>&1 || true

rm -f "$outfile"
ping_healthchecks
echo "Uploaded $(basename "$outfile") to $RCLONE_REMOTE/$NAME"
