#!/usr/bin/env bash
# Deploy script for wiki-polis on Toolforge.
# Run from the home directory: bash ~/wiki-polis/deploy.sh
# Do a git pull manually before running this.

set -euo pipefail

cd ~/wiki-polis

echo "==> Syncing dependencies..."
uv sync

echo "==> Restarting web service..."
cd ~
toolforge webservice --backend=kubernetes python3.11 restart

echo "==> Done."
