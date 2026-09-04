#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DIR="${PARTICIAPP_DOCKER_DIR:-$SCRIPT_DIR/../particiapp-docker}"
if [ ! -d "$DOCKER_DIR" ]; then
  echo "ERROR: particiapp-docker not found at $DOCKER_DIR" >&2
  echo "Clone it next to wiki-polis, or set PARTICIAPP_DOCKER_DIR=/path/to/particiapp-docker." >&2
  exit 1
fi
DOCKER_DIR="$(cd "$DOCKER_DIR" && pwd)"
FLASK_DIR="$SCRIPT_DIR/v2"
SESSION_FILE="$SCRIPT_DIR/.dev-session"

# ── Session file ──────────────────────────────────────────────────────────────
# Create with defaults on first run; edit to change port assignments.

if [ ! -f "$SESSION_FILE" ]; then
  cat > "$SESSION_FILE" <<'EOF'
POSTGRES_PORT=5433
PARTICIAPI_PORT=8002
POLIS_PORT=8003
FLASK_PORT=5001
EOF
fi

# shellcheck source=/dev/null
source "$SESSION_FILE"

session_set() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$SESSION_FILE" 2>/dev/null; then
    sed -i '' "s|^${key}=.*|${key}=${val}|" "$SESSION_FILE"
  else
    echo "${key}=${val}" >> "$SESSION_FILE"
  fi
}

# ── Docker stack ──────────────────────────────────────────────────────────────

if [ -f "$DOCKER_DIR/.env" ]; then
  DOCKER_ENV_FILE="$DOCKER_DIR/.env"
elif [ -f "$DOCKER_DIR/dev.env" ]; then
  DOCKER_ENV_FILE="$DOCKER_DIR/dev.env"
else
  echo "ERROR: no particiapp-docker env file found. Expected $DOCKER_DIR/.env or $DOCKER_DIR/dev.env." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "ERROR: Docker Compose not found. Install either the 'docker compose' plugin or docker-compose." >&2
  exit 1
fi

COMPOSE+=(
  --env-file "$DOCKER_ENV_FILE"
  -f "$DOCKER_DIR/docker-compose.yaml"
  -f "$FLASK_DIR/docker-compose.wiki-polis.local.yaml"
)

# Trusted-sub secret. The app and the Particiapi container must share one value, or
# Particiapi ignores the asserted subject and every participant is anonymous — silently,
# since a mismatched secret still returns 200. Read it from v2/.env when the shell does
# not already provide one. Unset is fine and means anonymous, exactly as before.
if [ -z "${PARTICIAPI_SUB_SECRET:-}" ] && [ -f "$FLASK_DIR/.env" ]; then
  PARTICIAPI_SUB_SECRET="$(grep -E '^PARTICIAPI_SUB_SECRET=' "$FLASK_DIR/.env" | tail -1 | cut -d= -f2- | tr -d '\042\047')"
fi
export PARTICIAPI_SUB_SECRET="${PARTICIAPI_SUB_SECRET:-}"
if [ -n "$PARTICIAPI_SUB_SECRET" ]; then
  echo "→ trusted-sub enabled: participants get a stable identity across rounds"
else
  echo "→ trusted-sub NOT set (PARTICIAPI_SUB_SECRET absent) — participants will be anonymous"
fi

compose() {
  env \
    POSTGRES_HOST_PORT="$POSTGRES_PORT" \
    PARTICIAPI_HOST_PORT="$PARTICIAPI_PORT" \
    POLIS_HOST_PORT="$POLIS_PORT" \
    FLASK_HOST_PORT="$FLASK_PORT" \
    WIKI_POLIS_DIR="$SCRIPT_DIR" \
    PARTICIAPI_SUB_SECRET="$PARTICIAPI_SUB_SECRET" \
    "${COMPOSE[@]}" "$@"
}

stop_docker() {
  echo ""
  echo "Stopping Docker stack..."
  compose down
  session_set POSTGRES_STATUS stopped
  session_set PARTICIAPI_STATUS stopped
  session_set FLASK_STATUS stopped
}

if docker ps --filter "name=particiapp-docker" --format "{{.Names}}" | grep -q .; then
  echo "particiapp-docker stack already running — skipping Docker Compose up"
else
  echo "Starting Docker stack..."
  compose up -d
  trap stop_docker EXIT
fi

session_set POSTGRES_STATUS waiting
echo "Waiting for postgres on :$POSTGRES_PORT..."
until docker exec particiapp-docker-postgres-1 pg_isready -U polis -q 2>/dev/null; do
  sleep 2
done
session_set POSTGRES_STATUS ready

# Setting the secret is not enough: the published particiapi image predates the
# trusted-sub feature, and an image without it accepts the header, ignores it, and
# returns 200. Nothing downstream can tell that apart from working — so check the
# image itself rather than trusting the configuration.
if [ -n "$PARTICIAPI_SUB_SECRET" ]; then
  if docker exec particiapp-docker-particiapi-1 sh -c \
       'grep -rqs "X-Particiapi-Sub" /app' 2>/dev/null; then
    echo "→ trusted-sub: image supports it, participants will get a stable identity"
  else
    echo "!! PARTICIAPI_SUB_SECRET is set, but this particiapi image does NOT implement"
    echo "!! trusted-sub. Identity binding will silently do nothing: subjects are ignored,"
    echo "!! every participant stays anonymous, and particiapi_users stays empty."
    echo "!! Build an image from subprojects/particiapi (which has the feature) and retag it:"
    echo "!!   docker build -t registry.gitlab.com/particiapp/particiapi/particiapi:latest \\"
    echo "!!     \"\$PARTICIAPP_DOCKER_DIR/subprojects/particiapi\""
  fi
fi

session_set PARTICIAPI_STATUS waiting
echo "Waiting for particiapi on :$PARTICIAPI_PORT..."
until curl -o /dev/null -sf -w "%{http_code}" "http://127.0.0.1:$PARTICIAPI_PORT/" 2>/dev/null | grep -qE "^[2345]"; do
  sleep 2
done
session_set PARTICIAPI_STATUS ready

echo ""
echo "Stack ready."
echo "  Particiapi : http://127.0.0.1:$PARTICIAPI_PORT"
echo "  Polis      : http://127.0.0.1:$POLIS_PORT"
echo "  Flask app  : http://127.0.0.1:$FLASK_PORT  (starting now)"
echo "  Dev login  : http://127.0.0.1:$FLASK_PORT/dev-login"
echo ""

# ── Flask ─────────────────────────────────────────────────────────────────────

# Kill any stale Python processes on this port
STALE=$(lsof -ti :"$FLASK_PORT" | xargs ps -p 2>/dev/null | grep -i python | awk '{print $1}' || true)
if [ -n "$STALE" ]; then
  echo "Killing stale Flask process(es): $STALE"
  kill $STALE 2>/dev/null || true
  sleep 1
fi

# Warn if AirPlay Receiver is still holding the port
if lsof -i :"$FLASK_PORT" | grep -q ControlCe 2>/dev/null; then
  echo "WARNING: AirPlay Receiver (ControlCenter) is using port $FLASK_PORT."
  echo "  Disable: System Settings > General > AirDrop & Handoff > AirPlay Receiver"
  echo ""
fi

session_set FLASK_STATUS running
cd "$FLASK_DIR"
export FLASK_DEBUG=1
export FLASK_APP=app.py
export SECRET_KEY="${SECRET_KEY:-dev-insecure-key}"
export ADMIN_USERS="${ADMIN_USERS:-DevUser}"
export DEV_LOGIN_USER="${DEV_LOGIN_USER:-DevUser}"
export DEV_DATABASE_URL="${DEV_DATABASE_URL:-sqlite:///dev.db}"
export PARTICIAPI_BASE_URL="http://127.0.0.1:$PARTICIAPI_PORT"
export POLIS_SERVER_URL="http://127.0.0.1:$POLIS_PORT"
export POLIS_DATABASE_URL="postgresql://polis:polis@127.0.0.1:$POSTGRES_PORT/polis"

uv run flask --app app init-db
exec uv run flask --app app run --host 127.0.0.1 --port "$FLASK_PORT"
