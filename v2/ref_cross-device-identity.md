# Cross-device participant identity (xid → Particiapi)

How a logged-in Wikimedia user keeps **one stable Polis participant** across devices,
browsers, and sessions — and why it didn't before.

## The bug (found 2026-06-23, on production)

Particiapi identifies a participant by the per-browser `pa_session` cookie. The Flask
proxy forwarded only that cookie and **never told Particiapi who the user was**, so every
new session — a second device, another browser, a cleared cookie — became a *brand-new
anonymous Polis participant* (`create_uid()`). One human fragmented into many participants,
which silently corrupts the clustering the whole tool depends on.

Reproduced on conversation `66zmvkuner` (zid 9): one person voting laptop → phone produced
**5 separate participants** with split vote counts; the Polis `xids` table was empty (the
xid never reached Polis).

### Root cause, precisely
- `xid = sha256(mw_user_id)` is stable per user and stored in our app DB, but was **never
  forwarded** to Particiapi.
- **Particiapi has no `xid` concept.** It is *not* vanilla Polis — it's a separate Flask
  API in front of Polis Postgres. It identifies participants only via **Keycloak/OIDC**
  (`get_or_create_uid(issuer, subject)`) or, when `AUTHENTICATION_DISABLED=true`, an
  **anonymous** path that mints a fresh uid per session (`create_uid()`). wiki-polis used
  the anonymous path.
- The xid-JWT mechanism that *does* exist in upstream Polis (`server/src/auth/`, e.g.
  compdemocracy/polis #2540) lives in the Polis server layer wiki-polis does **not** use
  for voting — so "upgrade the Polis engine" would not have fixed it.

## The fix

Give Particiapi a **stable subject** for the logged-in user so it uses
`get_or_create_uid("wiki-polis", xid)` instead of `create_uid()`.

**wiki-polis proxy** (`v2/app.py`, `_proxy_to_particiapi`) — on **`POST /api/session`**
only, when the user is logged in and `PARTICIAPI_SUB_SECRET` is set:
- sends `X-Particiapi-Sub: <xid>` + `X-Particiapi-Sub-Secret: <secret>`, and
- **drops any forwarded `pa_session` cookie** so a stale anonymous session can't pin the
  user to a throwaway uid (forces a clean re-bind to the xid).

**Particiapi** (companion change, on the fork — see below) — in `session_()`, when an
unauthenticated request presents `X-Particiapi-Sub` and `X-Particiapi-Sub-Secret` matches
`TRUSTED_SUB_SECRET` (constant-time compare):
`session["uid"] = get_or_create_uid("wiki-polis", trusted_sub)`. It warns (no false
positives — browsers can't set the header) when a sub is presented but rejected, so a
mis-set secret can't silently re-fragment participants.

Net: every device for the same user resolves to **one stable uid** (issuer `"wiki-polis"`,
subject = xid) via Particiapi's `particiapi_issuers` + `users` tables → one participant,
votes follow the user.

### Properties
- **No-op until the shared secret is configured on both sides.** Safe to merge/deploy the
  code before enabling.
- **Gated by the shared secret** + the existing network restriction (only the proxy can
  reach Particiapi). The proxy builds request headers fresh and never forwards client
  headers, so a browser cannot inject `X-Particiapi-Sub`.

## Configuration

| Side | Var | Notes |
|---|---|---|
| wiki-polis (Flask) | `PARTICIAPI_SUB_SECRET` | Toolforge secret/envvar. Unset → old anonymous behaviour. |
| Particiapi | `PARTICIAPI_TRUSTED_SUB_SECRET` | `from_prefixed_env("PARTICIAPI")` → config `TRUSTED_SUB_SECRET`. Unset (`None`) → feature off. |

Both must hold the **same** value (`python3 -c "import secrets; print(secrets.token_hex(32))"`).
A one-sided/mismatched secret degrades silently to anonymous — Particiapi logs a WARN when
a sub is presented but rejected, which is the signal to check.

## The Particiapi fork

Particiapi upstream is `gitlab.com/particiapp/particiapi`. The change is **not upstreamed**;
it lives on a fork: **`github.com/lgelauff/particiapi`**, branch `feat/trusted-sub-identity`
(PR lgelauff/particiapi#1). Two files: `particiapi/api.py` (`session_()`),
`particiapi/config_defaults.py` (`TRUSTED_SUB_SECRET = None`).

## Deploying to staging (no source build)

The VPS runs Particiapi from the **registry image**
`registry.gitlab.com/particiapp/particiapi/particiapi:latest` (not a local source build),
and the box is memory-tight (no swap, shared with prod) — so **do not build on the VPS**.
For a staging test we **bind-mount the two patched files over the image's copies** (the
running `:latest` image was verified byte-identical to the patch base, so the overlay is
clean).

### How we actually got the patched image running (the working recipe)
The image installs the package at `/app/particiapi` and runs it via
`uwsgi --module=particiapi:create_app()` (see the Particiapi `Dockerfile`). So overlaying
two files and recreating the container is enough — no rebuild.

0. **Confirm capacity first** — `df -h /`, `docker system df`, `free -h`. Disk was fine;
   memory was the constraint (no swap, prod on the same box) → which is *why* we don't build.
1. **Version gate** — confirm the running image's files match the patch base, so the overlay
   doesn't clobber newer upstream code:
   `docker exec wiki-polis-staging_particiapi_1 sed -n '40,62p' /app/particiapi/api.py`
   and `… cat /app/particiapi/config_defaults.py`. They were byte-identical → safe to mount.
2. **Copy the patched files to the VPS** (`scp` the fork's `api.py` + `config_defaults.py`
   into `~/particiapi-patch/`).
3. **Override file** `docker-compose.patch.yaml` (below) — bind-mounts the two files
   read-only over `/app/particiapi/...` and adds `PARTICIAPI_TRUSTED_SUB_SECRET`.
4. **Recreate only the staging particiapi** with all three `-f` files + `-p wiki-polis-staging`
   (command below). Scoped to the staging project → prod is untouchable.
5. **Apply the auth-table DDL** to the staging Polis Postgres (the `particiapi_issuers` /
   `particiapi_users` + trigger — see the prerequisite below; the bind alone 500s without it).
6. **Verify in-container**: patched code present + secret set + healthy:
   `docker exec … grep -c trusted_sub /app/particiapi/api.py` (>0),
   `docker exec … sh -c '[ -n "$PARTICIAPI_TRUSTED_SUB_SECRET" ] && echo set'`,
   `docker ps --filter name=wiki-polis-staging_particiapi_1` (`healthy`), and no tracebacks in
   `docker logs`.

The override and the two files:

In `~/particiapp-docker-staging`, an extra override `docker-compose.patch.yaml`:
```yaml
services:
  particiapi:
    environment:
      PARTICIAPI_TRUSTED_SUB_SECRET: "<secret>"
    volumes:
      - /home/<user>/particiapi-patch/api.py:/app/particiapi/api.py:ro
      - /home/<user>/particiapi-patch/config_defaults.py:/app/particiapi/config_defaults.py:ro
```
Recreate only that service, scoped to the staging project (never touches prod). The VPS has
**Compose v1**, so it's `docker-compose` (hyphenated), not `docker compose`:
```
docker-compose -p wiki-polis-staging \
  -f docker-compose.yaml -f docker-compose.staging.yaml -f docker-compose.patch.yaml \
  up -d particiapi
```
Roll back by deleting the override and re-running without it. (Staging
`wiki-polis-staging_particiapi_1` and prod `particiapp-docker_particiapi_1` are separate
containers / projects / databases.)

A durable deploy (prod) should instead build the fork into an image off-VPS (e.g. ghcr)
and pull it, rather than rely on the bind-mount.

### Prerequisite: Particiapi auth tables must exist in Polis Postgres
`get_or_create_uid` writes to `particiapi_issuers` / `particiapi_users` and relies on the
`insert_new_uid` trigger → `create_user()`. A stack that has only ever run the **anonymous**
path (`AUTHENTICATION_DISABLED=True`) **never created these** — `session_()` will 500 with
`relation "public.particiapi_issuers" does not exist`. Apply the DDL from the Particiapi
`schema.sql` (function + two tables + trigger) to the Polis Postgres before enabling the
secret. This was missing on staging and is **almost certainly missing on prod too**.

## Verify (the case no unit test covers)
On a second device that **already holds a stale anonymous `pa_session`**, log in and
confirm you land on the **same uid/pid with the prior votes** — not a fresh anonymous
split. Check `particiapi_users` has the `wiki-polis` issuer resolving **one** uid for the xid,
and that a second browser's votes accrue to that uid's single `participant` (no new pid).

## Staging validation — PASSED (2026-06-23)
Verified live on `wiki-polis-dev` against the `wiki-polis-staging` Particiapi.
- Same Wikimedia user across incognito-Chrome + phone-Chrome → **one** Polis identity
  (`particiapi_users` uid 24, issuer `wiki-polis`) → **one** participant (`pid 12`), votes
  accumulating on it across browsers (no fragmentation). Pre-fix, each session was a new pid.
- **Gotchas found (now in this doc):** (1) the missing `particiapi_*` auth tables (above);
  (2) testing on the **`#236` branch** (which bundles the #96 HMAC xid change) while a browser
  still held a session from a **main-based** deploy → the xid differed across the two schemes
  and produced a transient second identity (uid 23). Not a flaw in the binding — it's the
  xid-version transition (see below). Clearing sessions / re-login resolved it.
- Note: staging had to run the proxy change **on top of `#236`** (`test/identity-on-236`),
  because the staging DB was already migrated to `#236`'s schema and main-based code 500s on
  the dropped `arguments.proposer_id`.

## Production rollout prerequisites
1. **Particiapi image** — build the fork (`lgelauff/particiapi` `feat/trusted-sub-identity`)
   into an image **off-VPS** (memory is tight, no swap, shared with prod) and pull it; don't
   bind-mount or build on the box.
2. **DDL** — create `particiapi_issuers` / `particiapi_users` + trigger in the **prod** Polis
   Postgres (see prerequisite above).
3. **Secrets** — set `TRUSTED_SUB_SECRET` on prod Particiapi and `PARTICIAPI_SUB_SECRET` on the
   prod tool to the **same** value.
4. **xid-version transition** — see below; decide before flipping the secret on.

## The xid-version transition (#96) — read before enabling on real data
Because the xid is now the **Polis identity key**, **any change to the xid derivation makes
every existing user a brand-new Polis participant** (their prior votes orphan under the old
uid). The bare-`sha256` → HMAC change (#96) is exactly such a change. Two options:
- **Simple (testing / pre-launch, disposable data):** flip the scheme and **log everyone out**
  — clear the Flask `sessions` table so all sessions re-derive under the new scheme. Do **not**
  rotate `SECRET_KEY` to log people out: it's the xid HMAC fallback key, so rotating it changes
  every xid *again*. Old votes are abandoned; everyone restarts as a fresh participant.
- **Preserving (real deliberation data):** keep both xid versions resolvable (a mapping or a
  dual-lookup) so a user's old and new xids resolve to the same Polis uid. Larger change; tracked
  with [#96](https://github.com/lgelauff/wiki-polis/issues/96).

## Not addressed
- **Backfill** of already-fragmented data (e.g. prod zid 9) — the fix is **prospective only**;
  there is no anon-uid → Wikimedia-identity mapping to merge pre-cutover votes.
- The xid (even HMAC-keyed) is stored in Polis (`particiapi_users.subject`) — the store now
  holds a per-deployment-stable link to the user; the brute-force exposure is reduced by the
  key but not eliminated. Coordinate with [#96](https://github.com/lgelauff/wiki-polis/issues/96).
