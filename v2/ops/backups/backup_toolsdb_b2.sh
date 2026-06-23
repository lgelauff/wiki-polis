#!/usr/bin/env bash
# Dump the wiki-polis ToolsDB database from Toolforge, upload to rclone/B2, then
# remove the local copy. Use a MySQL option file so credentials are never passed
# on the command line.

set -euo pipefail

NAME="${BACKUP_NAME:-toolsdb}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/wiki-polis-backups}"
TOOLSDB_HOST="${TOOLSDB_HOST:-tools.db.svc.wikimedia.cloud}"
TOOLSDB_DEFAULTS_FILE="${TOOLSDB_DEFAULTS_FILE:-$HOME/replica.my.cnf}"
TOOLSDB_DATABASE="${TOOLSDB_DATABASE:?set TOOLSDB_DATABASE, e.g. s12345__wiki-polis}"
RCLONE_REMOTE="${RCLONE_REMOTE:?set RCLONE_REMOTE, e.g. b2:wiki-polis-postgres-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
HEALTHCHECKS_URL="${HEALTHCHECKS_URL:-}"

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
outfile="$BACKUP_DIR/${NAME}-${timestamp}.sql.gz"
tmpfile="${outfile}.tmp"

mysqldump \
  --defaults-extra-file="$TOOLSDB_DEFAULTS_FILE" \
  --host="$TOOLSDB_HOST" \
  --single-transaction \
  --quick \
  --routines \
  --triggers \
  "$TOOLSDB_DATABASE" | gzip -c > "$tmpfile"

gzip -t "$tmpfile"
test -s "$tmpfile"
mv "$tmpfile" "$outfile"

rclone copyto "$outfile" "$RCLONE_REMOTE/$NAME/$(basename "$outfile")"
rclone delete --min-age "${RETENTION_DAYS}d" "$RCLONE_REMOTE/$NAME"
rclone rmdirs "$RCLONE_REMOTE/$NAME" >/dev/null 2>&1 || true

rm -f "$outfile"
ping_healthchecks
echo "Uploaded $(basename "$outfile") to $RCLONE_REMOTE/$NAME"
