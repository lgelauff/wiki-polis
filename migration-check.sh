#!/usr/bin/env bash
# migration-check.sh — run the Alembic migration chain against MariaDB (the deploy DB),
# not just SQLite. Catches MySQL-specific migration bugs (FK/index ordering, ENUM/JSON
# DDL, etc.) BEFORE they reach staging — the gap that let err 1553 ship (#236 review).
#
# What it does, faithfully reproducing a Toolforge deploy:
#   1. brings up a throwaway MariaDB (or uses $MIGCHECK_DB_URL if provided, e.g. CI service)
#   2. builds the BASE_REF schema with create_all() + stamps BASE_REF's migration head
#      (mirrors how the live DB was originally created, then evolved by migrations)
#   3. runs `flask db upgrade` with the CURRENT working tree's migrations
#   4. reports the final head and tears everything down
#
# Usage:
#   bash migration-check.sh [BASE_REF]      # BASE_REF defaults to origin/main
# CI passes MIGCHECK_DB_URL pointing at a MariaDB service container.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Positional-only by design: CI also sets a $BASE_REF env var, but that's just how it
# constructs the argument it passes below — this always reads $1, never the environment.
BASE_REF="${1:-origin/main}"
DBNAME="wikipolis_migcheck"
CONTAINER="wp-migcheck-mariadb"
STARTED_CONTAINER=0
BASE_WT="$(mktemp -d)/base"

cleanup() {
  git -C "$REPO_ROOT" worktree remove --force "$BASE_WT" >/dev/null 2>&1 || true
  rm -rf "$(dirname "$BASE_WT")" >/dev/null 2>&1 || true
  if [ "$STARTED_CONTAINER" = 1 ]; then docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

# ── 1. database ──────────────────────────────────────────────────────────────
if [ -n "${MIGCHECK_DB_URL:-}" ]; then
  DBURL="$MIGCHECK_DB_URL"
  echo "==> using provided MariaDB: ${DBURL%%@*}@…"
else
  echo "==> starting throwaway MariaDB ($CONTAINER:3310)…"
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$CONTAINER" -e MARIADB_ROOT_PASSWORD=root \
    -e MARIADB_DATABASE="$DBNAME" -p 3310:3306 mariadb:11 >/dev/null
  STARTED_CONTAINER=1
  DBURL="mysql+pymysql://root:root@127.0.0.1:3310/$DBNAME"
  READY=0
  for _ in $(seq 1 40); do
    docker exec "$CONTAINER" mariadb -uroot -proot -e "SELECT 1" >/dev/null 2>&1 && { READY=1; break; }
    sleep 2
  done
  if [ "$READY" != 1 ]; then
    echo "==> ERROR: MariaDB did not become ready within 80s." >&2
    exit 1
  fi
fi

# Pick an interpreter: prefer uv (CI/canonical), else a local venv we create.
runner() {  # runner <workdir> <flask|python> [args…]
  local wd="$1"; shift; local tool="$1"; shift
  if command -v uv >/dev/null 2>&1; then ( cd "$wd" && uv run "$tool" "$@" ); else ( cd "$wd" && ".venv/bin/$tool" "$@" ); fi
}
ensure_venv() {  # ensure_venv <v2dir>
  command -v uv >/dev/null 2>&1 && { ( cd "$1" && uv sync >/dev/null 2>&1 ); return; }
  [ -x "$1/.venv/bin/python" ] || "${PYTHON:-python3}" -m venv "$1/.venv"
  ( cd "$1" && .venv/bin/python -m pip install -q -e . pymysql >/dev/null 2>&1 )
}

export MIGRATION_MODE=1 SECRET_KEY=migcheck FLASK_DEBUG=0 DATABASE_URL="$DBURL"

# ── 2. bootstrap BASE_REF schema (create_all + stamp its head) ───────────────
echo "==> bootstrapping pre-change schema from '$BASE_REF'…"
git -C "$REPO_ROOT" worktree add --quiet --detach "$BASE_WT" "$BASE_REF"
ensure_venv "$BASE_WT/v2"
runner "$BASE_WT/v2" python -c "from app import app, db; ctx=app.app_context(); ctx.push(); db.create_all()"

# Don't let `grep`'s no-match exit swallow the real error under `set -e`/`pipefail` — capture
# stderr too so a genuine bootstrap failure (bad venv, import error) is visible instead of a
# silent crash, and fail loudly on zero or multiple heads instead of picking one arbitrarily.
BASE_HEADS_RAW="$(runner "$BASE_WT/v2" flask --app app db heads 2>&1)" || {
  echo "==> ERROR: 'flask db heads' failed on base ref '$BASE_REF':" >&2
  echo "$BASE_HEADS_RAW" >&2
  exit 1
}
BASE_HEADS="$(echo "$BASE_HEADS_RAW" | grep -oE '^[0-9a-f]{12}' || true)"
BASE_HEAD_COUNT="$(echo "$BASE_HEADS" | grep -c . || true)"
if [ -z "$BASE_HEADS" ]; then
  echo "==> ERROR: no migration head found for base ref '$BASE_REF' — cannot stamp a baseline." >&2
  exit 1
fi
if [ "$BASE_HEAD_COUNT" -gt 1 ]; then
  echo "==> ERROR: base ref '$BASE_REF' has multiple migration heads (unmerged branches) —" >&2
  echo "    refusing to silently pick one (see #236/60e03ee for why this matters):" >&2
  echo "$BASE_HEADS" >&2
  exit 1
fi
BASE_HEAD="$BASE_HEADS"
echo "    base migration head: $BASE_HEAD"
runner "$BASE_WT/v2" flask --app app db stamp "$BASE_HEAD" >/dev/null

# ── 3. upgrade with the CURRENT tree's migrations ────────────────────────────
echo "==> applying current-branch migrations on MariaDB…"
ensure_venv "$REPO_ROOT/v2"
if runner "$REPO_ROOT/v2" flask --app app db upgrade; then
  echo "==> ✅ migrations apply cleanly on MariaDB. Final head:"
  runner "$REPO_ROOT/v2" flask --app app db current 2>/dev/null | grep -oE '^[0-9a-f]{12} \(head\)' || true
else
  echo "==> ❌ migration FAILED on MariaDB (see error above). This would break the Toolforge deploy."
  exit 1
fi
