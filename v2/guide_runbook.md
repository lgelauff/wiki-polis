# Operator runbook

> **Status — operational.** Production is **live** at `wiki-polis.toolforge.org` (VPS
> backend up). This is the day-2 operations guide — people follow it to actually run
> things, so anything **not yet live or unverified in production is flagged inline with
> ⚠️ not live yet**. Unmarked procedures are live. First-time provisioning lives in
> [`guide_deployment.md`](guide_deployment.md); env vars are in its Environment variables reference.

## Routine procedures

These already live in the deployment guide; this runbook is the day-2 entry point to
them:

- **Deploy a new version** → [Ongoing deploys](guide_deployment.md#ongoing-deploys) (or `bash ~/wiki-polis/deploy.sh`).
- **Run a database migration** → [Database migrations](guide_deployment.md#database-migrations) (must run inside the webservice shell).
- **Toolforge quirks** → [Toolforge gotchas](guide_deployment.md#toolforge-gotchas).

## Monitoring & health

- `GET /health` returns `{"db", "particiapi", "status"}`. **Caveat:** it is a
  *reachability* check, not a correctness check — it reports `"particiapi": "ok"` even
  when its upstream probe returns a 404. A green `/health` means "the process answered,"
  not "Particiapi is serving correctly." Treat a non-200 or a connection error as the
  real alarm.
- Centralised log aggregation / alerting across the VPS + Toolforge — **⚠️ not live
  yet**, deferred by decision D-MON
  ([#49](https://github.com/lgelauff/wiki-polis/issues/49)). There is no alerting today;
  you find problems by checking `/health` and the logs by hand.

## Logs

- **Toolforge (Flask):** `/data/project/wiki-polis/uwsgi.log` (staging:
  `/data/project/wiki-polis-dev/uwsgi.log`). The file can contain non-text bytes, so
  **force text mode with `grep -a`** or matches are silently hidden ("binary file
  matches"). Filter rotation noise: `tail -50 …/uwsgi.log | grep -av lseek`. See
  [Investigating a 5xx](#investigating-a-5xx) for reading the status code correctly.
- **VPS (Polis / Particiapi / Postgres):** `docker logs <container>`, or
  `docker-compose logs <service>` from the `particiapp-docker` directory for
  **production**. For **staging** the stack runs under a non-default compose project
  name — use `docker-compose -p wiki-polis-staging logs <service>` (see
  [Staging environment](#staging-environment)).

## Changes not showing up in the browser

If a deployed change to CSS, JS, or fonts isn't visible:

1. **Check the footer SHA.** The git commit hash in the page footer must match what you
   deployed. If it doesn't, the pod is still running the old code — wait for the deploy
   to finish or restart the webservice.
2. **Hard-reload isn't enough.** Static assets are cached for 1 year in the browser.
   A normal reload or even `Cmd+Shift+R` may still serve the old cached file if the URL
   hasn't changed.
3. **The URL must change.** The `?v=<git-sha>` suffix on static URLs is what busts the
   cache. If the footer SHA matches your deploy but the asset still looks wrong, open
   DevTools → Network → find the file and check its URL contains the new SHA. If it
   doesn't, something is serving stale HTML — check your local browser cache or a
   proxy/CDN in front.
4. **Force-clear for local testing.** DevTools → Network → check **Disable cache** while
   DevTools is open, then reload. This bypasses the browser cache entirely for that session.

## Investigating a 5xx

When a 5xx is reported (by a soak run, monitoring, or a user), work outside-in:

1. **Did it even reach the Flask app?** Grep the uwsgi log (with `-a`, see above):

       grep -a "<path fragment>" /data/project/<tool>/uwsgi.log | tail -20

   **⚠️ Read the status correctly.** A uwsgi access line ends with the real status in
   `(HTTP/1.1 NNN)`. The `req: 503/1521` field near the *start* of the line is uwsgi's
   request counter — **not** an HTTP 503. Don't be fooled by grepping for `503`.
   - request appears with `(HTTP/1.1 5xx)` → the app (or a backend it proxied to)
     produced it → go to step 2.
   - request is **absent** (its neighbours are logged, it isn't) → **Toolforge's front
     proxy** returned the 5xx (usually 503) because the webservice pod was momentarily
     unavailable/saturated. The app never saw it. Transient; if frequent, raise the
     uwsgi `processes`/`threads` in `~/www/python/uwsgi.ini`.
2. **Proxy or upstream?** The Particiapi proxy returns **502** on any upstream failure
   (`abort(502)` on `requests.RequestException`) and **never** emits 503. So a logged
   502 + a `Particiapi proxy error` traceback (timestamp must match the incident!) means
   the proxy couldn't reach Particiapi; a logged 503 that *did* reach the app was relayed
   from upstream Polis/Particiapi → check the backend.
3. **Backend (VPS).** SSH to `wiki-polis-backend`; `docker ps` — anything restarting /
   unhealthy / OOMKilled? For staging remember the project flag:
   `docker-compose -p wiki-polis-staging logs --since 30m particiapi`.
4. **Reproduce.** `v2/synthetic_traffic.py` drives the real proxy under load and exits
   non-zero on any 5xx — use it to confirm a fix or to decide a one-off 5xx was noise.

## Inspecting Polis data (votes & statements)

**Statement votes live only in the Polis Postgres on the VPS — never in the wiki-polis
Flask DB.** (The Flask ToolsDB holds `participation`/pseudonyms and *argument* votes
(`argument_vote`); a statement vote goes browser → proxy → Particiapi → Polis PG.) So to
verify a vote, query Polis PG directly. Connect with `docker exec` (no password needed)
— note the role/db is **`polis`**, *not* `postgres`:

```bash
CID=wiki-polis-staging_postgres_1        # prod: particiapp-docker_postgres_1
docker exec -it $CID psql -U polis -d polis -c '\d votes'
```

Key tables (Polis schema):
- `zinvites(zinvite, zid)` — maps the conversation's zinvite string (the `polis_id` shown
  on the admin page) to the numeric `zid`.
- `comments(zid, tid, txt, mod, active)` — the statements (`tid` = statement id).
- `votes(zid, pid, tid, vote, created, …)` — **append-only** vote history. `vote` is
  **−1 = agree, 0 = pass, 1 = disagree**; `created` is **epoch-millis** (`to_timestamp(created/1000.0)`
  to read it). There is **no `modified` column** here.
- `votes_latest_unique(zid, pid, tid, vote, modified)` — **the authoritative current vote**
  per (participant, statement). An INSERT rule on `votes` upserts this table on every vote,
  so a re-vote flips `vote` and bumps `modified` here while leaving a second history row in
  `votes`.

> ⚠️ **The raw vote sign is inverted vs the Polis CSV export — don't "correct" it.**
> In these raw tables (and in our app's vote API) `vote = -1` is **agree**, `+1` is
> **disagree**, `0` is pass — matching the web component's `Vote` enum (`Agree:-1,
> Disagree:1`). Polis's **official `participants-votes` export flips the sign** to the
> intuitive `agree = +1, disagree = -1`: it negates every vote in
> `math/src/polismath/darwin/export.clj` (`get-corrected-conversation-votes` →
> `(partial * -1)`), with the comment *"Flip the signs on the votes XXX (remove when we
> switch)"*. So both are "right" at different layers: reading raw PG, **`-1` = agree**.
> The flip is undocumented upstream and flagged as tech-debt, so it could change in a
> future Polis bump — re-check after upgrades.

```bash
# Current (authoritative) vote per participant+statement in a conversation:
docker exec -it $CID psql -U polis -d polis -c \
  "SELECT pid, tid, vote, to_timestamp(modified/1000.0) AS modified_at
     FROM votes_latest_unique
    WHERE zid = (SELECT zid FROM zinvites WHERE zinvite='<ZINVITE>')
    ORDER BY modified DESC LIMIT 20;"

# Full vote history (a vote *change* shows as two rows for the same pid+tid):
docker exec -it $CID psql -U polis -d polis -c \
  "SELECT pid, tid, vote, to_timestamp(created/1000.0) AS voted_at
     FROM votes
    WHERE zid = (SELECT zid FROM zinvites WHERE zinvite='<ZINVITE>')
    ORDER BY created DESC LIMIT 20;"
```

## Diagnosing empty results

The Results tab shows "Results will appear here once enough votes have been cast."
when Particiapi returns all-empty arrays (`{"groups":[],"majority":{"agree":[],"disagree":[]}}`).
This is normal Polis behaviour — clustering only runs once there is enough data.

**Check the vote count for a conversation:**

```bash
# Staging
CID=wiki-polis-staging_postgres_1
# Production
CID=particiapp-docker_postgres_1

docker exec -it $CID psql -U polis -d polis -c \
  "SELECT COUNT(*) FROM votes WHERE zid = (SELECT zid FROM zinvites WHERE zinvite='<ZINVITE>');"
```

Polis typically requires **≥ 7 participants** and a reasonable spread of votes before
the math worker produces clusters. A conversation with only 2–4 participants will
always return empty results.

**Check `vis_type`** — Polis gates `/results/` on `vis_type <> 0`. If results are empty
even with plenty of votes, `vis_type` may be 0 (not set). Fix: open the admin Phases
form for that conversation and hit **Save** — this triggers `set_vis_type(1)`.

```bash
docker exec -it $CID psql -U polis -d polis -c \
  "SELECT vis_type FROM conversations WHERE zinvite = '<ZINVITE>';"
```

Expected: `1`. If `0`, re-save Phases in the admin UI.

**Auto-recompute trigger** — when the Results tab shows "Results will appear here once enough votes have been cast." but votes clearly exist, the app automatically inserts a `worker_tasks` row to wake the polismath worker (rate-limited to once per 10 minutes per conversation). This requires `POLIS_DATABASE_URL` to be set correctly on the Toolforge tool. If the admin stats panel is blank, `POLIS_DATABASE_URL` is misconfigured — the most common cause is using the WMCS hostname instead of the numeric IP. Toolforge pods cannot resolve `*.wikimedia.cloud` hostnames; the DSN must use the private IP directly (e.g. `172.16.19.44`). For staging, same IP, port `5442`.

Verify a recompute was queued:

```bash
CID=wiki-polis-staging_postgres_1   # or particiapp-docker_postgres_1 for prod
docker exec -it $CID psql -U polis -d polis -c \
  "SELECT task_type, task_data, created, finished_time, attempts
   FROM worker_tasks
   WHERE task_data->>'zid' = (SELECT zid::text FROM zinvites WHERE zinvite='<ZINVITE>')
   ORDER BY created DESC LIMIT 5;"
```

If `finished_time` is set, the worker processed it. If rows are absent and the admin stats panel is blank, fix `POLIS_DATABASE_URL` first.

## Backups & restore

- **Backups:** a nightly `pg_dump` of the Polis Postgres DB → offsite. **⚠️ not live
  yet — not confirmed running in production.** For a live service this is the top
  hardening priority: set it up (see `guide_deployment.md`), confirm it produces a recent,
  non-empty dump, then rehearse the restore below. A backup you've never checked is a
  hope, not a backup.
- **Restore drill** (rehearse before you need it) — **⚠️ not live yet: never rehearsed
  against production.**
  1. Copy the latest dump to the VPS and `gunzip` it.
  2. Restore into a scratch database first (`createdb polis_restore_test`; `psql -U polis polis_restore_test < dump.sql`) and sanity-check row counts against production.
  3. Only then restore into the live DB, with the stack stopped.

## Staging environment

`wiki-polis-dev.toolforge.org` is a **permanent** staging tool (decision D-MON) with its
own backend stack — **fully isolated from production**. Validate changes here before
deploying to the `wiki-polis` production tool.

**Topology.** One VPS host (`wiki-polis-backend`) runs **two complete particiapp stacks**
side by side; staging and production never share a database:

| Stack | particiapi | polis-server | postgres | compose project |
|---|---|---|---|---|
| **production** | 8000 | 8001 | 5432 | `particiapp-docker` (dir default) |
| **staging** | 8010 | 8011 | 5442 | `wiki-polis-staging` |

`wiki-polis-dev`'s `PARTICIAPI_BASE_URL` points at `…:8010` (the staging particiapi), so
staging conversation/vote data lives in the **staging** Polis Postgres. Mutating staging —
e.g. synthetic traffic on the `test` conversation — never touches production.

**⚠️ Gotcha — the staging compose project name.** The staging stack was brought up under
project name **`wiki-polis-staging`**, not its directory name (`particiapp-docker-staging`).
So `docker-compose ps` *inside that directory shows nothing*. Manage it with the project
flag (or `docker ps`, which always shows the truth — staging containers are
`wiki-polis-staging_*`):

    docker-compose -p wiki-polis-staging ps
    docker-compose -p wiki-polis-staging logs --since 30m <service>
    # or export COMPOSE_PROJECT_NAME=wiki-polis-staging

**Logging in to staging (headless or browser).** Toolforge deployments do not register
the fake-login routes, even on a dev tool. Browser checks should use Wikimedia OAuth.
Headless checks such as `synthetic_traffic.py` must pass `--session-cookie` from an
authenticated staging browser session. Both `/dev/login/<username>` and the single-user
`/dev-login` variant are local-debug-only paths.

**Deploying to staging.** `become wiki-polis-dev`, then
`bash ~/wiki-polis/deploy.sh <branch>` (add `--migrate` only for schema changes). Confirm
the printed commit hash is what you intended; it also appears in the page footer.

**Load note.** Under sustained synthetic load (~6 req/s) staging occasionally returns a
single ingress `503` (~1 in 3000) — Toolforge's front proxy when the pod is briefly
saturated, **not** the app (see [Investigating a 5xx](#investigating-a-5xx)). For a
prototype this is harmless; raise uwsgi `processes`/`threads` only if real bursty traffic
is expected.

**Cold-pod latency.** Staging receives little traffic so its Kubernetes pod is frequently
reaped by Toolforge. The first request after a cold start pays ~30 s while the pod
schedules, the container starts, and the Django app boots. Subsequent requests are fast.
Production is unaffected as long as it receives regular traffic. There is no fix short of
a keepalive cron job (`curl -s -o /dev/null https://wiki-polis-dev.toolforge.org/ ` every
10 min from a Toolforge cron).


## Secrets rotation

`toolforge envvars` has no `update` — rotate by delete + recreate:
`toolforge envvars delete <NAME>` then `toolforge envvars create <NAME>` (use the
interactive prompt; never pass a secret as a CLI argument). Restart the webservice
afterward. Candidates to rotate on a schedule or on suspected compromise: `SECRET_KEY`,
`OAUTH_CLIENT_SECRET`, `RATELIMIT_IDENTITY_SECRET`, `POLIS_ADMIN_PASSWORD`, and the
`wiki_polis_ro` Postgres password. *(pending — rotation cadence)*

## Responding to an outage

**⚠️ not live yet:** these steps are standard but have not been exercised against a real
production incident — treat them as a starting point, not a tested procedure.

- **App down (Toolforge):** check `/health`; `tail` the uwsgi log; restart from the
  home directory — `cd ~ && toolforge webservice restart`.
- **Particiapi / Polis unreachable:** SSH to the VPS; `docker ps` (are all services
  healthy?); restart with `docker-compose restart polis-server` or the whole stack.
  While Particiapi is unreachable the Flask proxy returns 502 and voting fails.
- **Postgres trouble:** see Backups & restore above; check disk space on the VPS data
  volume first (`df -h`).
