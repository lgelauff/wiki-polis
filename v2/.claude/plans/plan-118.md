# Plan: #118 — Restore headless test access on Toolforge (dev-login disabled)

**Verdict: FITS — directly impacts automated staging tests and synthetic traffic runs on wiki-polis-dev.**

## Context

PR #106 correctly disabled `DEV_FAKE_LOGIN` on Toolforge (`_fake_login_enabled = bool(app.debug and _fake_login_requested and not _on_toolforge)`). This broke headless testing on `wiki-polis-dev`. The issue proposes three options:

- **Option A** — Remove `/dev/login/<username>` routes entirely; local dev uses `DEV_LOGIN_USER`
  (single-user `/dev-login`) only.
- **Option B** — HMAC-gated staging bypass token.
- **Option C** — Document `--session-cookie` workflow (minimum viable, no code changes).

**Recommended approach: Option A + Option C.**

Rationale:
- The `/dev/login/<username>` multi-user fake-login was only needed to test concurrent
  workers (multiple dev identities). That's still covered locally via `DEV_FAKE_LOGIN=1` in
  `.env`. On Toolforge/staging it adds attack surface with no benefit since tests can pass
  `--session-cookie`.
- Option B adds complexity (STAGING_DEV_TOKEN secret, HMAC validation) for a problem that
  is fully solved by a documented session-cookie workflow.
- The `--session-cookie` path already exists in `synthetic_traffic.py` and its preflight.

**What this plan delivers:**
1. Remove the multi-user `/dev/login/<username>` routes from `app.py`.
2. Update `guide_runbook.md` § Staging to document the session-cookie workflow.
3. Update `guide_local-dev.md` to reflect that `DEV_LOGIN_USER` (single-user `/dev-login`)
   is the only local auth bypass.
4. Update `synthetic_traffic.py` docstring to clarify the session-cookie path.

**What we keep:** `DEV_LOGIN_USER` / `/dev-login` (single-user local-only route) is
untouched — it's local-debug-only and already guarded by `not _on_toolforge`.

## Files to change

| File | Action |
|---|---|
| `v2/app.py` | Remove `DEV_FAKE_LOGIN` block + `/dev/login/<username>` route (lines ~3243–3269) |
| `v2/synthetic_traffic.py` | Remove `DEV_USERS` list; update auth() to require `--session-cookie`; update docstring |
| `v2/guide_runbook.md` | Document session-cookie workflow for staging headless tests |
| `v2/guide_local-dev.md` | Remove references to `/dev/login/<username>`; clarify `DEV_LOGIN_USER` |

## Implementation steps

### Step 1 — remove fake-login routes from `v2/app.py`

Locate the block `# ── Dev test users (DEV_FAKE_LOGIN=1) ──` (~lines 3232–3269). It contains:
- The `_DEV_TEST_USERS` list
- `_fake_login_requested` / `_fake_login_enabled` checks
- `app.config['DEV_FAKE_LOGIN']` and `app.config['DEV_TEST_USERS']` assignments
- The `@app.get('/dev/login/<username>')` route

**Delete this entire block.**

Also search for references to `DEV_FAKE_LOGIN` and `DEV_TEST_USERS` config keys used
elsewhere in `app.py` (e.g. rendering test-user badges on the home page) and remove them.

```bash
grep -n "DEV_FAKE_LOGIN\|DEV_TEST_USERS\|dev_fake_login\|dev/login" v2/app.py
```

Remove:
- The home-page template variable `dev_test_users` if it exists.
- Any template rendering of the fake-user badge list.

Check `v2/templates/` for any references to `dev_test_users` or fake-login UI:
```bash
grep -rn "dev_test_users\|dev/login\|DEV_FAKE" v2/templates/
```

Remove or conditionally guard any such template code.

### Step 2 — remove `DEV_FAKE_LOGIN` from env vars reference

In `guide_deployment.md` Environment variables reference table, remove the `DEV_FAKE_LOGIN`
row (or change it to a note: "removed in favour of `DEV_LOGIN_USER`").

### Step 3 — update `v2/synthetic_traffic.py`

The tool already supports `--session-cookie` fully. Changes needed:
- Remove `DEV_USERS = [...]` constant.
- In `auth()`: remove the `DEV_USERS` branch; if `args.session_cookie` is absent, print a
  clear error directing the user to pass `--session-cookie` and return `False`.
- In `parse_args()`: remove the `if not args.session_cookie and args.workers > len(DEV_USERS)`
  cap; remove the `DEV_USERS` reference.
- Update the module docstring to remove "1. auth GET /dev/login/dev-user-N" and note that
  all targets now require `--session-cookie`.
- Update `preflight()`: remove the `DEV_USERS` branch; if no `--session-cookie`, return
  `(False, "pass --session-cookie from an authenticated browser")`.

### Step 4 — update `v2/guide_runbook.md` § Staging environment

In the paragraph beginning "Logging in to staging (headless or browser).", expand with:

```
**Obtaining a session cookie for headless staging tests:**
1. Open https://wiki-polis-dev.toolforge.org in a browser and log in via Wikimedia OAuth.
2. Open DevTools → Application → Cookies → wiki-polis-dev.toolforge.org.
3. Copy the value of the `session` cookie.
4. Pass it to the soak harness:
   python v2/synthetic_traffic.py \
       --base-url https://wiki-polis-dev.toolforge.org \
       --slug test \
       --session-cookie "session=<value>" \
       --duration 60
The cookie expires with the browser session; obtain a fresh one for each soak run.
```

### Step 5 — update `v2/guide_local-dev.md`

Remove any mention of `/dev/login/<username>` and `DEV_FAKE_LOGIN`. Clarify that local auth
bypass uses `DEV_LOGIN_USER=<username>` in `.env`, which registers the `/dev-login` route
(single-user, local-debug-only, never on Toolforge).

## Tests

```bash
# Confirm the route is gone from app.py:
grep -n "dev/login\|DEV_FAKE_LOGIN" v2/app.py   # should return nothing

# Confirm synthetic_traffic no longer references DEV_USERS:
grep -n "DEV_USERS\|dev/login" v2/synthetic_traffic.py   # should return nothing

# Run the test suite:
cd v2 && python -m pytest tests/ -x -q
```

Also run the app locally (`DEV_LOGIN_USER=dev-user-1 FLASK_DEBUG=1 flask --app app run`)
and confirm:
- `/dev-login` still works (redirects to home with dev-user-1 session).
- `/dev/login/dev-user-1` now returns 404.
- The home page no longer shows fake-user badge links.

## Verification

- `GET /dev/login/dev-user-1` on local → 404.
- `DEV_FAKE_LOGIN=1 flask run` → warning logged that `DEV_FAKE_LOGIN` is unrecognised (or
  silently ignored since the block is removed).
- `synthetic_traffic.py --dry-run` without `--session-cookie` → exits 2 with a clear
  "pass --session-cookie" message.
- Test suite passes.
