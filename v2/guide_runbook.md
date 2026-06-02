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

**Logging in to staging (headless or browser).** `DEV_FAKE_LOGIN=1` is set on the
`wiki-polis-dev` tool, enabling `GET /dev/login/<username>` for three fixed identities —
`dev-user-1`, `dev-user-2`, `dev-user-3` (distinct xids, negative user-ids that cannot
collide with real accounts). This is how `synthetic_traffic.py` and headless tests
authenticate. **This path is OFF on production** (`/dev/login/...` → 404 there) — never
set `DEV_FAKE_LOGIN` on the `wiki-polis` tool. (The single-user `/dev-login` variant is
local-only; it never registers on Toolforge.)

**Deploying to staging.** `become wiki-polis-dev`, then
`bash ~/wiki-polis/deploy.sh <branch>` (add `--migrate` only for schema changes). Confirm
the printed commit hash is what you intended; it also appears in the page footer.

**Load note.** Under sustained synthetic load (~6 req/s) staging occasionally returns a
single ingress `503` (~1 in 3000) — Toolforge's front proxy when the pod is briefly
saturated, **not** the app (see [Investigating a 5xx](#investigating-a-5xx)). For a
prototype this is harmless; raise uwsgi `processes`/`threads` only if real bursty traffic
is expected.

## Secrets rotation

`toolforge envvars` has no `update` — rotate by delete + recreate:
`toolforge envvars delete <NAME>` then `toolforge envvars create <NAME>` (use the
interactive prompt; never pass a secret as a CLI argument). Restart the webservice
afterward. Candidates to rotate on a schedule or on suspected compromise: `SECRET_KEY`,
`OAUTH_CLIENT_SECRET`, `POLIS_ADMIN_PASSWORD`, and the `wiki_polis_ro` Postgres
password. *(pending — rotation cadence)*

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
