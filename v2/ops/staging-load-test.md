# Staging load test — measuring the 1000-voter scaling work

> **Purpose.** Measure on **staging** (`wiki-polis-dev.toolforge.org` + the staging VPS
> stack) the improvements that a local run cannot show: the **uWSGI threading ceiling**,
> **connection-churn avoidance**, and end-to-end **latency/throughput under real network +
> TLS to the VPS**. Output: a go / no-go for ~1000 participants, plus the pool/thread numbers.

## Why staging, not local

A local run understates the change because loopback has ~no per-connection cost (no TLS, no
RTT), the dev server isn't uWSGI (no threading), and 1000s of connections / TIME_WAIT / port
exhaustion don't reproduce at small scale. Locally we *proved the mechanism* — pooling reuses
1 connection vs N, and with an injected +40 ms/connection the PG path was **20× faster** —
but the concurrency ceiling and churn effects only appear against the real backend under a
real server. This plan measures those.

## What each change should show on staging (tie a metric to each)

| Change | Observable on staging |
|---|---|
| **A1** HTTP pooling | Flask→Particiapi TCP connections stay **bounded ≈ pool size**; baseline shows growing conns + `TIME_WAIT`. Lower p95 vote latency (no per-vote TCP+TLS handshake). |
| **A2/A3** PG pooling + O(N)→1 | VPS Postgres `pg_stat_activity` **bounded** vs a churn of short-lived connects. Admin *participants* page load time **flat vs ~linear** in participant count. |
| **A4** results cache | Results-tab load: Particiapi/PG call rate for `/results/` ≈ **1 per TTL per conversation** vs once per view; lower p95 under many concurrent viewers. |
| **A5** Phase 6 session reuse | Informed-voting load: Particiapi request rate ≈ **1× votes** (was ~2×). |
| **A7 / B** threaded uWSGI | **The headline.** Single-threaded ~4 workers saturate at ~4 in-flight (ceiling ≈ 4 / latency); threaded clears far more. The **req/s-ceiling ratio is the threading win**. |

## Prerequisites

1. **Deploy the scaling branch** to `wiki-polis-dev` (`bash ~/wiki-polis/deploy.sh <branch>`).
2. **Install the threaded uWSGI config** on the staging tool: copy `v2/ops/uwsgi.ini` to
   `~/www/python/uwsgi.ini`, then `toolforge webservice restart` (raise pod memory too:
   `toolforge webservice --mem 2Gi --cpu 1 python3.13 start`).
3. **Fix already in place:** the soak-submit coverage check (#130) — so `submit` is exercised
   and a run where it silently 401/404s fails loudly.
4. **Auth for many identities.** The proxy rate-limits **180/min (3 req/s) per identity**, so
   a single identity caps at 3 req/s. To reach 75+ req/s you need **≥ ~30 identities** (aim
   for ~100–300 to mirror a real spike). Two options:
   - Set `STAGING_DEV_TOKEN` on `wiki-polis-dev` and generate per-user tokens for
     `dev-user-1..N` (see `guide_runbook.md` → *Logging in to staging*); point
     `synthetic_traffic.py` at them, **or**
   - Temporarily widen the rate limit for the test window (raise the `@limiter.limit` values
     behind an env flag, or set a high `RATELIMIT` on staging) — note this in the run log.
5. **A votable staging conversation** with a healthy statement set (seed with
   `simulate_cats_vs_dogs.py --particiapi-url <staging particiapi>`); for the **A3** test,
   seed it with **many Participation rows** (100+) so the admin page has O(N) to exercise.
6. **Monitoring access:** the uWSGI stats socket, ToolsDB, and SSH to the VPS
   (`docker stats`, `psql`, `ss`).

## Target (derived from ~1000 participants)

- ~1000 over a launch window; worst-case spike ≈ **hundreds concurrent**.
- **Design target: sustain ~75 req/s, burst ~100+ req/s** (≈300 active voters × ~0.17
  votes/s + statement/results fetches).
- **Pass thresholds:** zero app 5xx; `/results/` always 200; statement-quota 403 clean (never
  500); **p95 proxied latency < ~1.5 s** at target; no uWSGI listen-queue starvation; ingress
  503s ≈ 0.

## Method — A/B, ramp to the ceiling

Two arms against the **same** staging backend:

- **Arm A (baseline):** `origin/main` code **+ default single-threaded uWSGI** (buffer-size
  only). This is the pre-change production posture.
- **Arm B (new):** the scaling branch **+ threaded `uwsgi.ini`**.

For each arm, ramp concurrency and hold each step ~3–5 min, capturing metrics per step:

```
workers:  10 → 25 → 50 → 100 → 200        (multi-identity)
mix:      ~80% vote, 15% results, 5% submit  (+ a Phase 6 vote action if testing A5)
```

```bash
# one step (repeat per workers value, per arm)
python v2/synthetic_traffic.py \
  --base-url https://wiki-polis-dev.toolforge.org \
  --slug <staging-conv> --conversation-id <polis_id> \
  --actions vote,results,submit --workers 100 --rate 2 --duration 240
```

- Find the concurrency where each arm's **error rate / p95** breaks (its **ceiling**).
- **Improvement = B's ceiling ÷ A's ceiling**, plus **p95 at a fixed load** (e.g. 50 req/s).

## Metrics per step, per arm

**Client** (synthetic_traffic summary): req/s, p50/p95/p99 per action, 5xx, 429.

**Server — the mechanism (what local couldn't show):**

```bash
# uWSGI worker/queue saturation (the ceiling). On the tool:
uwsgitop /tmp/uwsgi-stats.sock          # or read the stats socket; watch busy workers + listen queue

# A1 churn — Flask→Particiapi connections (on the VPS):
watch -n2 'ss -tan | grep ":8010" | awk "{print \$1}" | sort | uniq -c'   # staging particiapi port; watch ESTAB vs TIME_WAIT

# A2/A3 — VPS Postgres connections (staging PG):
docker exec wiki-polis-staging_postgres_1 psql -U polis -d polis -tAc \
  "SELECT state, count(*) FROM pg_stat_activity GROUP BY state;"

# ToolsDB (A7 pool vs cap) — on the tool / ToolsDB:
#   SHOW VARIABLES LIKE 'max_user_connections';  and  SHOW PROCESSLIST;  (count the tool's conns)

# VPS backend health:
docker stats --no-stream            # polismath / postgres CPU + RSS
docker logs --since 5m wiki-polis-staging_polis-math-1 | grep -iE 'GC|OOM|error'
# polismath recompute lag: REMOVED — this always returned NULL and measured nothing.
# `finished_time` is never set for update_math tasks, and `created` is epoch-millis so it
# cannot be compared to now() anyway. Read math_tick in math_main before/after instead.

# Ingress 503s (Toolforge front proxy saturation — absent from the app log):
grep -a ' 503 ' /data/project/wiki-polis-dev/uwsgi.log | tail   # and compare to app-logged 5xx
```

**Expected contrast:** Arm A shows **growing TCP connections + TIME_WAIT** to Particiapi, a
**spiky pg_stat_activity**, and a **req/s ceiling near ~4× (1/latency)**; Arm B keeps
connections **bounded** and clears **many-fold** more req/s before p95 degrades.

## Tuning loop (Arm B)

1. Raise `processes`×`threads` in `uwsgi.ini` until the binding constraint becomes **ToolsDB
   `max_user_connections`** or **VPS Postgres `max_connections`** (not the app).
2. Set the pools to fit under those caps: `TOOLSDB_POOL_SIZE`+`TOOLSDB_MAX_OVERFLOW` so
   `processes × (size+overflow) < max_user_connections`; `POLIS_PG_POOL_MAXCONN` and
   `POLIS_HTTP_POOL_MAXSIZE` ≈ threads-per-process. If PG connections are the wall, front the
   VPS Postgres with **pgbouncer**.
3. Re-run the ramp; confirm the **target** (75 req/s sustained, 100+ burst, all thresholds
   green). Record the winning `processes/threads/pool` numbers.

## Feeds the VPS capacity ask (Workstream C)

Watch `docker stats` on the VPS during the peak step: if polismath/Postgres saturate CPU or
RAM before the app does, the **VPS is the ceiling** → request the capacity bump (target
**8 vCPU / 16 GB**, min 4/8) with these numbers as justification.

## Safety / hygiene

- **The staging and production stacks share one VPS host** (`guide_runbook.md` → *Staging
  environment*). A heavy staging load **stresses the shared host**, so run it during **low
  production traffic** (or coordinate a window) and watch prod's health during the run.
- Staging only; use a disposable conversation (mutating the staging test conv is fine).
- Freeze any other synthetic load during the run so numbers are clean.

## Deliverable

A table — *concurrency step × arm ×* (req/s, p95, 5xx, uWSGI busy, Particiapi conns, PG conns)
— yielding: each arm's **ceiling**, the **improvement ratio**, the tuned **pool/thread**
numbers, a **VPS capacity** verdict, and a **go / no-go for ~1000 participants**.
