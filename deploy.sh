#!/usr/bin/env bash
# Deploy wiki-polis v2 on Toolforge.
# Run from anywhere: bash ~/wiki-polis/deploy.sh [branch] [options]
#
# Examples:
#   bash ~/wiki-polis/deploy.sh main --migrate   # deploy main + run migrations
#   bash ~/wiki-polis/deploy.sh main             # deploy main, skip migrations
#   bash ~/wiki-polis/deploy.sh feat/my-branch   # deploy a specific branch
#   bash ~/wiki-polis/deploy.sh --pr 303 --expect 94fda38
#   bash ~/wiki-polis/deploy.sh --migrate        # re-deploy CURRENT branch + migrate
#
# Without a branch argument the script stays on whatever branch is currently
# checked out on the server — always pass "main" explicitly to deploy main.

set -euo pipefail

BRANCH=""
PULL_REQUEST=""
EXPECTED_REV=""
MIGRATE=0

usage() {
  cat <<'EOF'
Usage: deploy.sh [branch] [--pr NUMBER] [--expect SHA] [--migrate]

Deploy a live origin branch, or a GitHub pull-request head via --pr.
Use --expect with a 7-40 character commit SHA to prevent deploying a moved ref.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --migrate)
      MIGRATE=1
      shift
      ;;
    --pr)
      [ "$#" -ge 2 ] || { echo "!!  ERROR: --pr requires a number." >&2; exit 2; }
      PULL_REQUEST="$2"
      shift 2
      ;;
    --expect)
      [ "$#" -ge 2 ] || { echo "!!  ERROR: --expect requires a commit SHA." >&2; exit 2; }
      EXPECTED_REV="${2,,}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      echo "!!  ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      [ -z "$BRANCH" ] || { echo "!!  ERROR: pass only one branch." >&2; exit 2; }
      BRANCH="$1"
      shift
      ;;
  esac
done

if [ -n "$BRANCH" ] && [ -n "$PULL_REQUEST" ]; then
  echo "!!  ERROR: pass either a branch or --pr, not both." >&2
  exit 2
fi
if [ -n "$PULL_REQUEST" ] && [[ ! "$PULL_REQUEST" =~ ^[1-9][0-9]*$ ]]; then
  echo "!!  ERROR: --pr must be a positive integer." >&2
  exit 2
fi
if [ -n "$EXPECTED_REV" ] && [[ ! "$EXPECTED_REV" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "!!  ERROR: --expect must be a 7-40 character commit SHA." >&2
  exit 2
fi

echo "==> Resolving deployment revision..."
cd ~/wiki-polis
if [ -n "$PULL_REQUEST" ]; then
  git fetch --prune origin "refs/pull/$PULL_REQUEST/head"
  TARGET_REV=$(git rev-parse --verify 'FETCH_HEAD^{commit}')
  DEPLOY_LABEL="PR #$PULL_REQUEST"
else
  if [ -z "$BRANCH" ]; then
    BRANCH=$(git symbolic-ref --quiet --short HEAD) || {
      echo "!!  ERROR: detached HEAD; pass a branch or --pr." >&2
      exit 2
    }
  fi
  git fetch --prune origin
  REMOTE_REF="refs/remotes/origin/$BRANCH"
  if ! git show-ref --verify --quiet "$REMOTE_REF"; then
    echo "!!  ERROR: origin/$BRANCH does not exist after fetch --prune." >&2
    exit 1
  fi
  TARGET_REV=$(git rev-parse --verify "$REMOTE_REF^{commit}")
  DEPLOY_LABEL="origin/$BRANCH"
fi

if [ -n "$EXPECTED_REV" ] && [[ "$TARGET_REV" != "$EXPECTED_REV"* ]]; then
  echo "!!  ERROR: $DEPLOY_LABEL resolved to $TARGET_REV, expected $EXPECTED_REV." >&2
  echo "!!  No dependencies were installed and the webservice was not restarted." >&2
  exit 1
fi

if [ -n "$PULL_REQUEST" ]; then
  git checkout --detach "$TARGET_REV"
else
  # Recreate the local branch at the verified remote commit. This also handles
  # first-time deployments and force-pushed development branches consistently.
  git checkout -B "$BRANCH" "$TARGET_REV"
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
LAST_HASH=$(git log -1 --format="%h")
LAST_MSG=$(git log -1 --format="%s")
LAST_AGO=$(git log -1 --format="%cr")
echo "    Branch : $CURRENT_BRANCH"
echo "    Source : $DEPLOY_LABEL"
echo "    Last   : $LAST_HASH $LAST_MSG ($LAST_AGO)"

echo "==> Syncing dependencies (v2)..."
~/www/python/venv/bin/pip install -e ~/wiki-polis/v2

echo "==> Building React frontend..."
if command -v npm >/dev/null 2>&1; then
  (
    cd ~/wiki-polis/v2/frontend
    npm ci
    npm run build
  )
elif command -v toolforge >/dev/null 2>&1; then
  # Toolforge bastions intentionally do not provide application runtimes. Run
  # the build in an ephemeral Node pod; the shared home mount makes the output
  # immediately available to the Python webservice after it restarts.
  echo "    npm is unavailable on the bastion; using a Toolforge Node 20 shell..."
  toolforge webservice --backend=kubernetes node20 shell -- \
    "$HOME/wiki-polis/v2/bin/build-spa.sh"
else
  echo "!!  ERROR: npm is required to build v2/frontend (Toolforge CLI fallback unavailable)." >&2
  exit 1
fi

# Existing Toolforge secrets (secret-key, database-url, oauth-*, admin-users) are reused unchanged.
# Only new secret needed: particiapi-base-url
#   read -rsp "particiapi-base-url: " V && printf '%s' "$V" | toolforge secrets create wiki-polis-particiapi-base-url --from-file=value=/dev/stdin
# Set the public Polis URL so result links point to this deployment, not pol.is:
#   toolforge envvars create POLIS_PUBLIC_URL 'https://wiki-polis.toolforge.org'

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
  # shellcheck disable=SC1090
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
