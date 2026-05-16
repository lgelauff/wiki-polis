#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DIR="$(cd "$SCRIPT_DIR/../particiapp-docker" && pwd)"
FLASK_DIR="$SCRIPT_DIR/v2"
SESSION_FILE="$SCRIPT_DIR/.dev-session"

# ── Session file ──────────────────────────────────────────────────────────────
# Create with defaults on first run; edit to change port assignments.

if [ ! -f "$SESSION_FILE" ]; then
  cat > "$SESSION_FILE" <<'EOF'
POSTGRES_PORT=5432
PARTICIAPI_PORT=8000
POLIS_PORT=8001
FLASK_PORT=5000
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

COMPOSE="docker compose \
  -f $DOCKER_DIR/docker-compose.yaml \
  -f $DOCKER_DIR/docker-compose.wiki-polis.yaml \
  -f $DOCKER_DIR/docker-compose.local.yaml"

stop_docker() {
  echo ""
  echo "Stopping Docker stack..."
  $COMPOSE down
  session_set POSTGRES_STATUS stopped
  session_set PARTICIAPI_STATUS stopped
  session_set FLASK_STATUS stopped
}

if docker ps --filter "name=particiapp-docker" --format "{{.Names}}" | grep -q .; then
  echo "particiapp-docker stack already running — skipping docker compose up"
else
  echo "Starting Docker stack..."
  POSTGRES_HOST_PORT=$POSTGRES_PORT $COMPOSE up -d
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
exec uv run flask run --host 127.0.0.1 --port "$FLASK_PORT"
