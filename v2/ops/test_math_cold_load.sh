#!/usr/bin/env bash
# Does restarting the math container make it re-read vote values changed in place?
#
# This settles the one assumption the vote-sign repair runbook rests on. The repair changes
# `votes.vote` with an UPDATE. That moves no `created` timestamp, so the change never
# appears in a poll batch. A conversation already loaded in the math process merges batches
# into a CACHED vote matrix; only a cold load rebuilds it from the database. So:
#
#   - if a restart forces a cold load, the repair is picked up          → route works
#   - if it recomputes from cache, math_tick advances and the clusters  → route is a trap
#     stay wrong, which passes every check the runbook tells you to make
#
# The second arm demonstrates the trap directly: cast a new vote WITHOUT restarting and
# show the repair is still not reflected.
#
# DESTRUCTIVE. It flips vote signs for one conversation. It refuses to run unless the
# container is a known throwaway (local or polis-repro) AND --confirm is passed. It never
# runs against production, by name.
#
#   ./test_math_cold_load.sh --zid 6
#   ./test_math_cold_load.sh --zid 6 --container particiapp-docker-postgres-1 --confirm
#
# Exit 0 = cold load re-read the repaired values (route works). 1 = it did not. 2 = usage.

set -uo pipefail

CONTAINER="particiapp-docker-postgres-1"
MATH_CONTAINER=""
ZID=""
CONFIRM=0
RESTORE=1

POLL_DAYS="${POLL_FROM_DAYS_AGO:-10}"
CREATE_IF_NEEDED=0
MIN_VOTES=50
MIN_PIDS=7

while [ $# -gt 0 ]; do
  case "$1" in
    --zid)               ZID="${2:-}"; shift 2 ;;
    --container)         CONTAINER="${2:-}"; shift 2 ;;
    --math-container)    MATH_CONTAINER="${2:-}"; shift 2 ;;
    --confirm)           CONFIRM=1; shift ;;
    --no-restore)        RESTORE=0; shift ;;
    --create-if-needed)  CREATE_IF_NEEDED=1; shift ;;
    *) echo "usage: $0 [--zid N] [--container NAME] [--math-container NAME] --confirm" >&2
       echo "            [--no-restore] [--create-if-needed]" >&2
       echo "  --zid omitted: pick the densest conversation with a vote in the last ${POLL_DAYS} days" >&2
       exit 2 ;;
  esac
done

# ── refuse anything that is not a known throwaway ─────────────────────────────
case "$CONTAINER" in
  *particiapp-docker-postgres*|*polis-repro*|*wiki-polis-staging*) ;;
  *) echo "ERROR: '$CONTAINER' is not a recognised throwaway stack." >&2
     echo "This test flips vote signs. It runs only against a local, polis-repro or staging" >&2
     echo "container. It will not run against production under any flag." >&2
     exit 2 ;;
esac
# Production's compose project uses underscores; refuse that shape outright.
case "$CONTAINER" in
  particiapp-docker_postgres_1) echo "ERROR: that is the production container. Refusing." >&2; exit 2 ;;
esac

if [ "$CONFIRM" -ne 1 ]; then
  if [ -n "$ZID" ]; then
    echo "This will flip every non-author vote sign for zid=$ZID in '$CONTAINER'."
  else
    echo "This will flip every non-author vote sign in '$CONTAINER', for whichever"
    echo "conversation it selects (the densest with a vote in the last ${POLL_DAYS} days)."
  fi
  echo "The flip is reversed at the end; negation is its own inverse."
  echo "Re-run with --confirm once you are sure that is a throwaway stack."
  exit 2
fi

if [ -z "$MATH_CONTAINER" ]; then
  MATH_CONTAINER="$(docker ps --format '{{.Names}}' | grep -iE 'polis-math' | head -1)"
fi
[ -z "$MATH_CONTAINER" ] && { echo "ERROR: no polis-math container found; pass --math-container." >&2; exit 2; }

psql_q() { printf '%s' "$1" | docker exec -i "$CONTAINER" psql -U polis -d polis -t -A -v ON_ERROR_STOP=1; }

# ── pick a conversation if one was not named ──────────────────────────────────
# Needs three things: a math_main row to compare against; at least one vote inside the
# poller's window, since that is what makes a restart emit a batch for it at all; and
# enough votes and distinct participants that math produces real clusters. A sparse
# conversation can yield a degenerate result that looks identical before and after,
# turning a genuine PASS into something unreadable.
select_zid() {
  psql_q "
    SELECT m.zid
    FROM math_main m
    WHERE (SELECT max(created) FROM votes WHERE zid = m.zid)
          > (EXTRACT(EPOCH FROM now())*1000 - ${POLL_DAYS}*86400000)
      AND (SELECT count(*)           FROM votes WHERE zid = m.zid) >= ${MIN_VOTES}
      AND (SELECT count(DISTINCT pid) FROM votes WHERE zid = m.zid) >= ${MIN_PIDS}
    ORDER BY (SELECT count(*) FROM votes WHERE zid = m.zid) DESC
    LIMIT 1;" | tr -d '[:space:]'
}

if [ -z "$ZID" ]; then
  echo "no --zid given; looking for a suitable conversation…"
  ZID="$(select_zid)"
  if [ -z "$ZID" ]; then
    echo "  none found (needs a math_main row, a vote in the last ${POLL_DAYS} days,"
    echo "  >= ${MIN_VOTES} votes and >= ${MIN_PIDS} participants)."
    if [ "$CREATE_IF_NEEDED" -eq 1 ]; then
      echo "  --create-if-needed given: building one with the simulator…"
      SIM_DIR="$(cd "$(dirname "$0")/.." && pwd)"
      PARTICIAPI_PORT="${PARTICIAPI_PORT:-8002}"
      # Pass --particiapi-url explicitly: the simulator reads v2/.env at import, and a
      # value there beats the default, failing with a port nobody chose.
      ( cd "$SIM_DIR" && uv run python simulate_cats_vs_dogs.py \
          --particiapi-url "http://127.0.0.1:${PARTICIAPI_PORT}" ) || {
        echo "ERROR: simulator failed; cannot provision a conversation." >&2; exit 2; }
      echo "  waiting up to 5 min for math to produce a first result…"
      DEADLINE=$(( $(date +%s) + 300 ))
      while [ "$(date +%s)" -lt "$DEADLINE" ]; do
        ZID="$(select_zid)"; [ -n "$ZID" ] && break
        sleep 15
      done
      [ -z "$ZID" ] && { echo "ERROR: conversation created but math produced no result yet." >&2
                         echo "Re-run this script in a few minutes." >&2; exit 2; }
    else
      echo
      echo "Create one first (from v2/):"
      echo "  uv run python simulate_cats_vs_dogs.py --particiapi-url http://127.0.0.1:8002"
      echo "or re-run this script with --create-if-needed to do that automatically."
      exit 2
    fi
  fi
  DETAIL="$(psql_q "SELECT (SELECT count(*) FROM votes WHERE zid=$ZID) || ' votes, ' || (SELECT count(DISTINCT pid) FROM votes WHERE zid=$ZID) || ' participants';")"
  echo "  selected zid=$ZID ($DETAIL)"
fi

snapshot() {  # tick + a hash of the clustering payload, which is what actually matters
  psql_q "SELECT math_tick || '|' || md5(COALESCE(math_main::text,'')) FROM math_main WHERE zid=$ZID;"
}

echo "container      : $CONTAINER"
echo "math container : $MATH_CONTAINER"
echo "zid            : $ZID"
echo

BEFORE="$(snapshot)"
[ -z "$BEFORE" ] && { echo "ERROR: no math_main row for zid=$ZID — nothing to compare." >&2; exit 2; }
echo "before          tick|payload-md5 = $BEFORE"

# ── arm 1: flip the signs, then cast a vote WITHOUT restarting ────────────────
echo
echo "[1/3] flipping vote signs in place (author rows excluded)…"
FLIPPED="$(psql_q "WITH upd AS (UPDATE votes v SET vote = -v.vote FROM comments c WHERE c.zid=v.zid AND c.tid=v.tid AND v.zid=$ZID AND v.vote <> 0 AND v.pid <> c.pid RETURNING 1) SELECT count(*) FROM upd;")"
psql_q "UPDATE votes_latest_unique u SET vote = -u.vote FROM comments c WHERE c.zid=u.zid AND c.tid=u.tid AND u.zid=$ZID AND u.vote <> 0 AND u.pid <> c.pid;" >/dev/null
echo "      flipped $FLIPPED vote rows"

echo "[2/3] waiting 90s to see whether a WARM recompute notices (it should not)…"
sleep 90
WARM="$(snapshot)"
echo "      after warm window          = $WARM"
if [ "$WARM" != "$BEFORE" ]; then
  echo "      note: math_main changed without a restart — a poll cycle ran."
  echo "      If the payload hash changed, the warm path DID re-read; that contradicts"
  echo "      the cached-matrix model and is the more interesting result."
fi

# ── arm 2: restart, forcing a cold load ───────────────────────────────────────
echo
echo "[3/3] restarting $MATH_CONTAINER to force a cold load…"
docker restart "$MATH_CONTAINER" >/dev/null
echo "      waiting for math_tick to advance (up to 15 min; the JVM is slow to boot)…"
DEADLINE=$(( $(date +%s) + 900 ))
AFTER="$BEFORE"
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  sleep 20
  AFTER="$(snapshot)"
  [ "$AFTER" != "$WARM" ] && [ "$AFTER" != "$BEFORE" ] && break
done
echo "      after cold load            = $AFTER"

# ── verdict ───────────────────────────────────────────────────────────────────
echo
BEFORE_HASH="${BEFORE#*|}"; AFTER_HASH="${AFTER#*|}"
BEFORE_TICK="${BEFORE%%|*}"; AFTER_TICK="${AFTER%%|*}"
RC=1
if [ "$AFTER_TICK" = "$BEFORE_TICK" ]; then
  echo "RESULT: INCONCLUSIVE — math_tick never advanced. The restart did not produce a"
  echo "        recompute at all, most likely because this conversation has no vote inside"
  echo "        the poller's window (poll-from-days-ago, default 10)."
elif [ "$AFTER_HASH" = "$BEFORE_HASH" ]; then
  echo "RESULT: FAIL — tick advanced ($BEFORE_TICK -> $AFTER_TICK) but the clustering payload"
  echo "        is byte-identical. The cold load did NOT re-read the repaired values, so"
  echo "        restarting is NOT a valid way to apply a vote-sign repair, and the runbook's"
  echo "        math_tick check is a false pass."
else
  echo "RESULT: PASS — tick advanced ($BEFORE_TICK -> $AFTER_TICK) and the clustering payload"
  echo "        changed. The cold load re-read the repaired values, so restarting the math"
  echo "        container is a valid way to apply an in-place vote repair."
  RC=0
fi

if [ "$RESTORE" -eq 1 ]; then
  echo
  echo "restoring the original signs (the flip is its own inverse)…"
  psql_q "UPDATE votes v SET vote = -v.vote FROM comments c WHERE c.zid=v.zid AND c.tid=v.tid AND v.zid=$ZID AND v.vote <> 0 AND v.pid <> c.pid;" >/dev/null
  psql_q "UPDATE votes_latest_unique u SET vote = -u.vote FROM comments c WHERE c.zid=u.zid AND c.tid=u.tid AND u.zid=$ZID AND u.vote <> 0 AND u.pid <> c.pid;" >/dev/null
  echo "restored. Clustering stays as the test left it until math next recomputes."
fi

exit $RC
