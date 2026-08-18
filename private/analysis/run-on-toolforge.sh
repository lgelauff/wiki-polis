#!/bin/bash
# Export both halves of an analysis bundle, from inside a Toolforge job.
#
# Must run as a JOB, not on the bastion. Toolforge injects the tool's envvars
# (DATABASE_URL, POLIS_DATABASE_URL) into jobs and the webservice — an interactive
# bastion shell does NOT get them, so the same commands typed there would silently
# receive empty connection strings. Same reasoning as v2/bin/phase-scheduler.sh.
#
# Setup (once, on the bastion as the tool user):
#     become wiki-polis
#     mkdir -p ~/analysis-export
#     # scp bundle.py, export_app_bundle.py, export_polis_bundle.py and this file there
#     chmod +x ~/analysis-export/run-on-toolforge.sh
#     openssl rand -hex 32 > ~/.wiki-polis-export-salt && chmod 600 ~/.wiki-polis-export-salt
#
# Run:
#     toolforge jobs run arbcom-export \
#         --image python3.13 \
#         --command "$HOME/analysis-export/run-on-toolforge.sh 2026-nlwiki-arbcom" \
#         --wait
#
# Then read the log and copy the result back (from your own machine):
#     cat ~/arbcom-export.out ~/arbcom-export.err
#     scp -r <tool>@bastion:~/analysis-export/<slug>_bundle ./
set -euo pipefail

SLUG="${1:?usage: run-on-toolforge.sh <conversation-slug> [--no-text]}"
shift || true

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/${SLUG}_bundle"
SALT="$HOME/.wiki-polis-export-salt"

# The app's own venv — it already has psycopg2 and PyMySQL, because the admin stats
# panel and the app itself use them. Nothing needs installing.
PY="$HOME/www/python/venv/bin/python"

[ -x "$PY" ]      || { echo "no interpreter at $PY — is the webservice venv set up?" >&2; exit 1; }
[ -r "$SALT" ]    || { echo "no salt file at $SALT — see the setup block above" >&2; exit 1; }
: "${DATABASE_URL:?DATABASE_URL is empty — are you running this as a Toolforge job?}"
: "${POLIS_DATABASE_URL:?POLIS_DATABASE_URL is empty — are you running this as a Toolforge job?}"

# Prove both connections and every table we need BEFORE exporting anything, so a
# missing grant or an empty connection string fails here rather than half way
# through a bundle.
echo "=== preflight ==="
if ! "$PY" "$HERE/preflight.py" \
        --app-db-url "$DATABASE_URL" \
        --polis-db-url "$POLIS_DATABASE_URL" \
        --slug "$SLUG"; then
    echo "preflight failed — nothing exported" >&2
    exit 1
fi

echo
echo "=== app database (ToolsDB) ==="
"$PY" "$HERE/export_app_bundle.py" \
    --db-url "$DATABASE_URL" \
    --slug "$SLUG" \
    --salt-file "$SALT" \
    --with-pseudonyms \
    --env prod --out "$OUT" "$@"

echo
echo "=== Polis database (VPS, over the private network) ==="
"$PY" "$HERE/export_polis_bundle.py" \
    --db-url "$POLIS_DATABASE_URL" \
    --conversations "$OUT/conversations.tsv" \
    --salt-file "$SALT" \
    --env prod --out "$OUT" "$@"

echo
echo "done — bundle at $OUT"
du -sh "$OUT"
