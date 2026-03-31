#!/usr/bin/env bash
# Deploy script for wiki-polis on Toolforge.
# Run from anywhere: bash ~/wiki-polis/deploy.sh

set -euo pipefail

echo "==> Pulling latest changes..."
cd ~/wiki-polis
git pull

echo "==> Syncing dependencies..."
~/www/python/venv/bin/pip install -e ~/wiki-polis

echo "==> Restarting web service..."
cd ~
toolforge webservice --backend=kubernetes python3.13 restart

echo "==> Done."
