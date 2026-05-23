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

compose() {
  env \
    POSTGRES_HOST_PORT="$POSTGRES_PORT" \
    PARTICIAPI_HOST_PORT="$PARTICIAPI_PORT" \
    POLIS_HOST_PORT="$POLIS_PORT" \
    FLASK_HOST_PORT="$FLASK_PORT" \
    WIKI_POLIS_DIR="$SCRIPT_DIR" \
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
export POLIS_DATABASE_URL="postgresql://polis:polis@127.0.0.1:$POSTGRES_PORT/polis"

uv run flask --app app init-db
exec uv run flask --app app run --host 127.0.0.1 --port "$FLASK_PORT"
