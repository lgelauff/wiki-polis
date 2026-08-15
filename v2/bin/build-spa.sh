#!/usr/bin/env bash
# Build the React SPA from any runtime that provides Node and npm.

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR/../frontend"

npm ci
npm run build
