#!/usr/bin/env bash
# Deploy wiki-polis v2 on Toolforge.
# Run from anywhere: bash ~/wiki-polis/deploy.sh [branch] [--migrate]
#
# Examples:
#   bash ~/wiki-polis/deploy.sh main --migrate   # deploy main + run migrations
#   bash ~/wiki-polis/deploy.sh main             # deploy main, skip migrations
#   bash ~/wiki-polis/deploy.sh feat/my-branch   # deploy a specific branch
#   bash ~/wiki-polis/deploy.sh --migrate        # re-deploy CURRENT branch + migrate
#
# Without a branch argument the script stays on whatever branch is currently
# checked out on the server — always pass "main" explicitly to deploy main.

set -euo pipefail

BRANCH=""
MIGRATE=0
for arg in "$@"; do
  case "$arg" in
    --migrate) MIGRATE=1 ;;
    *) BRANCH="$arg" ;;
  esac
done

echo "==> Pulling latest changes..."
cd ~/wiki-polis
if [ -n "$BRANCH" ]; then
  git fetch origin
  git checkout "$BRANCH"
  # Use reset instead of pull to handle force-pushed branches cleanly
  git reset --hard "origin/$BRANCH"
else
  git fetch origin
  git reset --hard "origin/$(git rev-parse --abbrev-ref HEAD)"
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
LAST_HASH=$(git log -1 --format="%h")
LAST_MSG=$(git log -1 --format="%s")
LAST_AGO=$(git log -1 --format="%cr")
echo "    Branch : $CURRENT_BRANCH"
echo "    Last   : $LAST_HASH $LAST_MSG ($LAST_AGO)"

echo "==> Syncing dependencies (v2)..."
~/www/python/venv/bin/pip install -e ~/wiki-polis/v2

# Existing Toolforge secrets (secret-key, database-url, oauth-*, admin-users) are reused unchanged.
# Only new secret needed: particiapi-base-url
#   read -rsp "particiapi-base-url: " V && printf '%s' "$V" | toolforge secrets create wiki-polis-particiapi-base-url --from-file=value=/dev/stdin
# Set the public Polis URL so result links point to this deployment, not pol.is:
#   toolforge envvars create POLIS_PUBLIC_URL 'https://wiki-polis.toolforge.org'

echo "==> Checking particiapp-web-components.js..."
WC_DST="$HOME/wiki-polis/v2/static/particiapp-web-components.js"
if [ ! -f "$WC_DST" ]; then
  echo "    WARNING: $WC_DST not found."
  echo "    Copy particiapp-web-components.js from the particiapp-docker subproject"
  echo "    into v2/static/ before the conversation page will work."
else
  echo "    Found."
fi

if [ "$MIGRATE" -eq 1 ]; then
  echo "==> Running database migrations..."
  # Load all Toolforge envvars so the app can start. Envvars are the single
  # source of truth — no manual list to maintain here.
  echo "    Loading Toolforge envvars..."
  while IFS= read -r name; do
    [[ -z "$name" || "$name" == "name" ]] && continue
    value=$(toolforge envvars show "$name" 2>/dev/null | tail -1 | awk '{print $NF}')
    [[ -n "$value" ]] && export "$name=$value"
  done < <(toolforge envvars list | awk 'NR>1 {print $1}')
  # MIGRATION_MODE=1 skips web-server-only startup checks (Redis, TRUSTED_HOSTS)
  # that require Kubernetes-injected vars unavailable on the bastion.
  # Has no effect on which code runs — migrations only touch the DB.
  source ~/www/python/venv/bin/activate
  cd ~/wiki-polis/v2
  MIGRATION_MODE=1 flask --app app db upgrade
  echo "    Migrations done."
fi

echo "==> Reconciling scheduled jobs (Toolforge jobs framework)..."
# Idempotent: re-asserts the schedule defined in jobs.yaml on every deploy.
# Non-fatal (a jobs failure must not block the web deploy) but LOUD — an earlier soft
# "WARNING" let a failed load slide past unnoticed, leaving the scheduler unregistered.
if toolforge jobs load ~/wiki-polis/jobs.yaml; then
  toolforge jobs list   # echo what's now registered so a silent no-op is visible
else
  echo "!!  ERROR: 'toolforge jobs load' FAILED — scheduled jobs (phase-scheduler) are NOT registered." >&2
  echo "!!  Web deploy will still finish, but scheduled phase transitions will NOT fire until you" >&2
  echo "!!  run 'toolforge jobs load ~/wiki-polis/jobs.yaml' manually and check 'toolforge jobs list'." >&2
fi

echo "==> Restarting web service..."
cd ~
toolforge webservice --backend=kubernetes python3.13 restart

echo "==> Done."
