#!/usr/bin/env bash
# Deploy wiki-polis v2 on Toolforge.
# Run from anywhere: bash ~/wiki-polis/deploy.sh

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
  _envvar() { toolforge envvars show "$1" | tail -1 | awk '{print $NF}'; }
  export DATABASE_URL=$(_envvar DATABASE_URL)
  export SECRET_KEY=$(_envvar SECRET_KEY)
  export PARTICIAPI_BASE_URL=$(_envvar PARTICIAPI_BASE_URL)
  export TRUSTED_HOSTS=$(_envvar TRUSTED_HOSTS)
  export RATELIMIT_KEY_PREFIX=$(_envvar RATELIMIT_KEY_PREFIX)
  export RATELIMIT_IDENTITY_SECRET=$(_envvar RATELIMIT_IDENTITY_SECRET)
  export FLASK_DEBUG=1  # skip production startup validation (rate-limit storage etc.) during migrations
  source ~/www/python/venv/bin/activate
  cd ~/wiki-polis/v2
  flask --app app db upgrade
  echo "    Migrations done."
fi

echo "==> Restarting web service..."
cd ~
toolforge webservice --backend=kubernetes python3.13 restart

echo "==> Done."
