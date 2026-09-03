#!/usr/bin/env bash
# Is Polis math keeping up? Read-only.
#
# Compares, per conversation, the newest vote math has incorporated
# (`math_main.last_vote_timestamp`) against the newest vote that actually exists
# (`max(votes.created)`). A conversation whose votes are newer than math's high-water mark
# has clustering that is behind the data.
#
# This is the check to use. The obvious-looking alternatives do not work:
#
#   - `worker_tasks.finished_time` is never set for `update_math` tasks, on any deployment.
#   - `worker_tasks.attempts` is written by no code in polis at all; it is the schema
#     default. A consumed row and an ignored one look identical.
#
# What it CANNOT tell you: whether a recompute that did happen used current values. A
# conversation already loaded in the math process merges new votes into a cached matrix,
# so an in-place UPDATE (as the vote-sign repair performs) can be missed while every
# number here looks healthy. Only test_math_cold_load.sh distinguishes those.
#
#   ./check_math_freshness.sh                                   # local default
#   ./check_math_freshness.sh particiapp-docker_postgres_1      # production (read-only)
#   ./check_math_freshness.sh wiki-polis-staging_postgres_1     # staging
#
# Exit 0 = every conversation current. Exit 1 = at least one is behind. Exit 2 = usage.

set -uo pipefail

CONTAINER="${1:-particiapp-docker-postgres-1}"
LAG_TOLERANCE_SEC="${LAG_TOLERANCE_SEC:-300}"   # a poll cycle plus compute time

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: no running container named '$CONTAINER'." >&2
  echo "Running Postgres containers:" >&2
  docker ps --format '  {{.Names}}' | grep -i postgres >&2 || echo "  (none)" >&2
  exit 2
fi

echo "Polis math freshness — container: $CONTAINER"
echo "Tolerance: ${LAG_TOLERANCE_SEC}s (a conversation behind by more than this is flagged)"
echo

# `created` is epoch-millis; last_vote_timestamp is the same scale. Conversations with no
# votes at all are excluded — they are legitimately uncomputed rather than behind.
read -r -d '' SQL <<'EOSQL'
SELECT
  m.zid,
  COALESCE(z.zinvite, '?')                                       AS zinvite,
  m.math_tick,
  to_char(to_timestamp(m.last_vote_timestamp/1000), 'YYYY-MM-DD HH24:MI') AS math_has,
  to_char(to_timestamp(v.newest/1000),               'YYYY-MM-DD HH24:MI') AS newest_vote,
  ROUND((v.newest - m.last_vote_timestamp)/1000.0)                AS lag_seconds
FROM math_main m
JOIN (SELECT zid, MAX(created) AS newest FROM votes GROUP BY zid) v ON v.zid = m.zid
LEFT JOIN zinvites z ON z.zid = m.zid
ORDER BY (v.newest - m.last_vote_timestamp) DESC;
EOSQL

OUT="$(printf '%s' "$SQL" | docker exec -i "$CONTAINER" psql -U polis -d polis -t -A -F'|' -v ON_ERROR_STOP=1 2>&1)"
RC=$?
if [ $RC -ne 0 ]; then
  echo "ERROR: query failed:" >&2
  echo "$OUT" >&2
  exit 2
fi

printf '%-6s %-12s %-10s %-17s %-17s %s\n' zid zinvite math_tick "math has" "newest vote" "lag"
printf '%-6s %-12s %-10s %-17s %-17s %s\n' ----- -------- --------- -------- ----------- ---
behind=0
while IFS='|' read -r zid zinvite tick math_has newest lag; do
  [ -z "$zid" ] && continue
  lag_int="${lag%%.*}"; lag_int="${lag_int:-0}"
  mark=""
  if [ "$lag_int" -gt "$LAG_TOLERANCE_SEC" ] 2>/dev/null; then mark="  <-- BEHIND"; behind=$((behind+1)); fi
  printf '%-6s %-12s %-10s %-17s %-17s %ss%s\n' "$zid" "$zinvite" "$tick" "$math_has" "$newest" "$lag_int" "$mark"
done <<< "$OUT"

echo
if [ "$behind" -gt 0 ]; then
  echo "$behind conversation(s) behind by more than ${LAG_TOLERANCE_SEC}s."
  echo "To force a recompute, see ops/phase6-vote-sign-repair.md step 5b."
  exit 1
fi
echo "All conversations current."
exit 0
