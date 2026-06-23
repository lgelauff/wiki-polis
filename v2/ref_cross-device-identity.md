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
clean):

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
Recreate only that service, scoped to the staging project (never touches prod):
```
docker compose -p wiki-polis-staging \
  -f docker-compose.yaml -f docker-compose.staging.yaml -f docker-compose.patch.yaml \
  up -d particiapi
```
Roll back by deleting the override and re-running without it. (Staging
`wiki-polis-staging_particiapi_1` and prod `particiapp-docker_particiapi_1` are separate
containers / projects / databases.)

A durable deploy (prod) should instead build the fork into an image off-VPS (e.g. ghcr)
and pull it, rather than rely on the bind-mount.

## Verify (the case no unit test covers)
On a second device that **already holds a stale anonymous `pa_session`**, log in and
confirm you land on the **same uid/pid with the prior votes** — not a fresh anonymous
split. Check `particiapi_issuers` has the `wiki-polis` issuer resolving one uid for the xid.

## Not addressed
- **Backfill** of already-fragmented data (e.g. zid 9) — the fix is **prospective only**;
  there is no anon-uid → Wikimedia-identity mapping to merge pre-cutover votes.
- **Keyed subject** `HMAC(server_secret, mw_user_id)` instead of the brute-forceable bare
  sha256 xid — defence-in-depth, tracked on [#96](https://github.com/lgelauff/wiki-polis/issues/96).
