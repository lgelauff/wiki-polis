# Operator runbook

> **Status — operational.** Production is **live** at `wiki-polis.toolforge.org` (VPS
> backend up). This is the day-2 operations guide — people follow it to actually run
> things, so anything **not yet live or unverified in production is flagged inline with
> ⚠️ not live yet**. Unmarked procedures are live. First-time provisioning lives in
> [`deployment.md`](deployment.md); env vars are in its Environment variables reference.

## Routine procedures

These already live in the deployment guide; this runbook is the day-2 entry point to
them:

- **Deploy a new version** → [Ongoing deploys](deployment.md#ongoing-deploys) (or `bash ~/wiki-polis/deploy.sh`).
- **Run a database migration** → [Database migrations](deployment.md#database-migrations) (must run inside the webservice shell).
- **Toolforge quirks** → [Toolforge gotchas](deployment.md#toolforge-gotchas).

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

- **Toolforge (Flask):** `/data/project/wiki-polis/uwsgi.log` — filter the rotation
  noise: `tail -50 /data/project/wiki-polis/uwsgi.log | grep -v lseek`.
- **VPS (Polis / Particiapi / Postgres):** `docker logs <container>` or
  `docker-compose logs <service>` from the `particiapp-docker` directory.

## Backups & restore

- **Backups:** a nightly `pg_dump` of the Polis Postgres DB → offsite. **⚠️ not live
  yet — not confirmed running in production.** For a live service this is the top
  hardening priority: set it up (see `deployment.md`), confirm it produces a recent,
  non-empty dump, then rehearse the restore below. A backup you've never checked is a
  hope, not a backup.
- **Restore drill** (rehearse before you need it) — **⚠️ not live yet: never rehearsed
  against production.**
  1. Copy the latest dump to the VPS and `gunzip` it.
  2. Restore into a scratch database first (`createdb polis_restore_test`; `psql -U polis polis_restore_test < dump.sql`) and sanity-check row counts against production.
  3. Only then restore into the live DB, with the stack stopped.

## Staging environment

`wiki-polis-dev.toolforge.org` is a **permanent** staging tool (decision D-MON). It
differs from production: dev-login / `DEV_FAKE_LOGIN` enabled, a separate ToolsDB
database, and it may point at a dev backend. Validate changes here before deploying to
the `wiki-polis` production tool. *(pending — document the exact prod-vs-staging config once both are settled)*

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
