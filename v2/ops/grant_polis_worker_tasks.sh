#!/usr/bin/env bash
# Grant the minimum extra Polis Postgres privileges wiki-polis needs to enqueue
# math recompute work through Polis' worker_tasks table.

set -euo pipefail

CONTAINER="${POLIS_POSTGRES_CONTAINER:-particiapp-docker_postgres_1}"
ROLE="${POLIS_APP_ROLE:-wiki_polis_ro}"

usage() {
  cat <<'EOF'
Usage: grant_polis_worker_tasks.sh [--container NAME] [--role ROLE]

Defaults:
  --container particiapp-docker_postgres_1
  --role      wiki_polis_ro

Examples:
  ./grant_polis_worker_tasks.sh
  ./grant_polis_worker_tasks.sh --container wiki-polis-staging_postgres_1
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --container)
      CONTAINER="${2:?missing --container value}"
      shift 2
      ;;
    --role)
      ROLE="${2:?missing --role value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "$ROLE" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "Refusing unsafe Postgres role name: $ROLE" >&2
  exit 2
fi

echo "Granting worker_tasks enqueue privileges to role '$ROLE' in container '$CONTAINER'..."
docker exec -i "$CONTAINER" psql -U polis -d polis -v ON_ERROR_STOP=1 <<SQL
GRANT INSERT ON TABLE worker_tasks TO "$ROLE";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "$ROLE";
SQL
echo "Done."
