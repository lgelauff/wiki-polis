#!/usr/bin/env bash
# Deploy wiki-polis v2 on Toolforge.
# Run from anywhere: bash ~/wiki-polis/deploy.sh

set -euo pipefail

echo "==> Pulling latest changes..."
cd ~/wiki-polis
git pull

echo "==> Syncing dependencies (v2)..."
~/www/python/venv/bin/pip install -e ~/wiki-polis/v2

# All v1 secrets (secret-key, database-url, oauth-*, admin-users) are reused unchanged.
# Only new secret needed: particiapi-base-url
#   toolforge secrets create wiki-polis-particiapi-base-url --from-literal=value=https://particiapi.example.com

echo "==> Checking particiapp-web-components.js..."
WC_DST="$HOME/wiki-polis/v2/static/particiapp-web-components.js"
if [ ! -f "$WC_DST" ]; then
  echo "    WARNING: $WC_DST not found."
  echo "    Copy particiapp-web-components.js from the particiapp-docker subproject"
  echo "    into v2/static/ before the conversation page will work."
else
  echo "    Found."
fi

echo "==> Restarting web service..."
cd ~
toolforge webservice --backend=kubernetes python3.13 restart

echo "==> Done."
