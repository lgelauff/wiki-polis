#!/bin/bash
# Toolforge scheduled job: fire due scheduled phase transitions.
# Registered via ../../jobs.yaml (loaded by deploy.sh). Runs with the tool's injected
# envvars, so — unlike an interactive bastion shell — SECRET_KEY etc. are present and no
# MIGRATION_MODE / manual env export is needed.
set -euo pipefail
cd "$HOME/wiki-polis/v2"
exec "$HOME/www/python/venv/bin/flask" --app app process-phase-schedules
