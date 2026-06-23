# wiki-polis security review: steps 1-5

Review base: `remove-v1-archive` at `e658b99` (`Remove archived v1 app`).

Scope requested: steps 1-5 of the 360 review plan:

1. Baseline and scope
2. Threat model
3. Route and authorization matrix
4. Authentication and session review
5. Authorization and multi-tenant data access

The retired `v1/` archive is out of scope because this branch removes it. The live in-scope application is `v2/`, plus the root Toolforge entrypoints and deployment scripts that load `v2`.

## Executive summary

No critical issue was found in the requested review slice. The current app has several strong controls: Wikimedia OAuth with state and PKCE, server-side sessions, CSRF protection on normal Flask form routes, CSP/security headers, conversation-scoped moderator checks, and database uniqueness constraints for participation and roles.

The main recommendations are hardening items around authentication safety, stable identity resolution, scoped moderator data exposure, CSRF-exempt proxy boundaries, production rate limiting, and privacy-contract consistency. Each recommended change is listed below as a granular clean commit.

## Automated checks

| Check | Result | Notes |
|---|---:|---|
| `POLIS_SERVER_URL=http://127.0.0.1:8003 POLIS_ADMIN_EMAIL=test@example.org POLIS_ADMIN_PASSWORD=test .venv/bin/python -m pytest` | Pass | 134 passed, 29 warnings |
| Production-like Flask route map | Pass | No dev-login route when `FLASK_DEBUG=0`, `DEV_LOGIN_USER=`, `DEV_FAKE_LOGIN=` |
| `bandit -r v2` | Review needed | Mostly low/dev findings; one high warning for direct `app.run(debug=True)` |
| `pip-audit` | Pass | No known vulnerabilities found in installed environment; local package skipped as not on PyPI |
| `detect-secrets scan` | Review needed | Flags placeholders, migration hashes, tests, and ignored local `v2/.env`; no obvious tracked production secret |

Dependency-audit limitation: `uv` is not available in this shell, so `pip-audit` ran against the installed venv, not an exact `uv.lock` export.

## System model

Evidence:

- Root `wsgi.py` inserts `v2/` into `sys.path` and imports `app` from there (`wsgi.py:4-7`).
- Deployment docs describe `Browser -> Toolforge Flask app -> Cloud VPS Particiapi/Polis/Postgres` (`v2/guide_deployment.md:3-13`).
- Toolforge deployment installs `~/wiki-polis/v2` and restarts the Python webservice (`deploy.sh:35-66`).
- The live app uses Flask, SQLAlchemy, Flask-Session, Flask-WTF CSRF, Flask-Limiter, Wikimedia OAuth, Requests, Particiapi, and Polis (`v2/pyproject.toml`, `v2/app.py:16-27`).

### Assets

| Asset | Why it matters |
|---|---|
| Wikimedia OAuth identity | Source of real user identity and admin eligibility |
| Flask session | Browser credential for logged-in users/admins |
| `Participant` rows | Stable Wikimedia user id, username, xid, global admin bit |
| `Participation` rows | Conversation membership, pseudonym, reveal mapping |
| Admin roles | Conversation-scoped moderation authority |
| Invite list | Access-control list for private conversations |
| Particiapi `pa_session` cookie | Browser credential bridged to Particiapi |
| Polis admin credentials | Conversation creation and moderation API access |
| ToolsDB/MariaDB | Identity and authorization store |
| Polis Postgres | Deliberation/vote/statement data |

### Trust boundaries

| Boundary | Evidence | Security expectation |
|---|---|---|
| Browser to Flask | Flask routes and templates in `v2/app.py`, `v2/templates/` | OAuth/session auth, CSRF, CSP, authorization |
| Flask to Wikimedia OAuth | OAuth login/callback at `v2/app.py:1770-1861` | State, PKCE, timeout, no token persistence |
| Flask to ToolsDB | SQLAlchemy config at `v2/app.py:1457-1467` | Secret DB URL, ORM queries, migration discipline |
| Flask to Particiapi | Proxy at `v2/app.py:279-360`, statement submit at `v2/app.py:569-645` | Path allowlist, cookie rename, origin checks, CSRF scheme |
| Flask to Polis admin API/Postgres | `v2/app.py:216-229`, deployment docs `v2/guide_deployment.md:207-213` | Strong credentials, read-only Postgres role for stats |
| Toolforge to VPS | Firewall/docs `v2/guide_deployment.md:55-67`, private bind docs `v2/guide_deployment.md:120-152` | Private-network exposure only |

## Route and authorization matrix

Production-like route inventory, grouped by policy.

| Route group | Routes | Current policy |
|---|---|---|
| Public | `GET /`, `GET /login`, `GET /oauth-callback`, `GET /health`, static files | Public; login/callback rate-limited; health rate-limit exempt |
| Authenticated participant | `GET/POST /accept/<slug>`, `GET /accept/<slug>/pseudonyms`, `GET /c/<slug>`, `GET/POST /c/<slug>/reveal`, `POST /logout` | `@login_required`; accept/conversation/reveal check participation or invite state where relevant |
| Participant argument flow | `POST /c/<slug>/arguments/...` submit/skip/vote/unvote | `@login_required`; `_require_arg_participation()` enforces active, unpaused, phase enabled, and current user's participation (`v2/app.py:521-533`) |
| Participant moderator actions | `POST /c/<slug>/arguments/<arg_id>/hide`, `.../unhide` | `@login_required`; `_can_moderate(conv)` check (`v2/app.py:1346-1369`) |
| Global admin only | `GET /admin`, conversation create/edit/pause/close/phases, global admin add/remove, role add/remove | `@login_required` and `@admin_required` (`v2/app.py:658-842`) |
| Conversation moderator or global admin | conversation detail, invites, statements, strict moderation, featured statements, argument delete | `@login_required`; `_require_mod_for_conv(conv_id)` enforces scoped moderator/global admin (`v2/app.py:232-237`) |
| Particiapi bridge | `GET/POST/PUT /proxy/particiapi/<path>`, `POST /c/<slug>/statements/new` | `@login_required`; whole `proxy_bp` is CSRF-exempt; unsafe requests use `_validate_same_origin()` (`v2/app.py:266-295`, `v2/app.py:1596-1602`) |
| Dev-only route | `GET /dev-login` | Only registered when `app.debug`, `DEV_LOGIN_USER`, and not Toolforge (`v2/app.py:1611-1655`) |

## Findings and recommendations

### SEC-01: `DEV_FAKE_LOGIN` is not fail-closed on Toolforge or non-debug environments

- Severity: High
- Location: `v2/app.py:1657-1692`, `v2/guide_local-dev.md:198-214`
- Evidence: `DEV_LOGIN_USER` is gated by `app.debug` and `not _on_toolforge` (`v2/app.py:1637`), but `DEV_FAKE_LOGIN` only checks whether the env var is set to `1` (`v2/app.py:1668-1672`). The guide documents setting it through Toolforge envvars for a dev tool (`v2/guide_local-dev.md:207-214`).
- Impact: If `DEV_FAKE_LOGIN=1` is accidentally set in production, anyone can bypass Wikimedia OAuth and log in as one of the hardcoded dev users. That may be enough to join public conversations, exercise participant-only actions, or gain more access if a dev user was invited or given a role.
- Fix: Register fake-login routes only when `app.debug and not _on_toolforge`, matching the `DEV_LOGIN_USER` guard. Add a production-mode test asserting `/dev/login/dev-user-1` is absent or 404 when `TOOL_TOOLFORGE_API_URL` is set.
- Clean commit: `security: gate fake login to local debug only`

### SEC-02: Current participant lookup uses mutable username instead of stable session `xid`

- Severity: Medium
- Location: `v2/app.py:130-138`, `v2/app.py:1845-1859`, `v2/db.py:20-25`
- Evidence: Login stores both username and `xid` in the session (`v2/app.py:1855-1859`), and `Participant.xid` is unique (`v2/db.py:25`), but `_current_participant()` resolves the active user by `mw_username` (`v2/app.py:133-138`).
- Impact: Wikimedia usernames can change. A stale session that resolves by username rather than stable user id hash can produce account confusion after rename/reuse scenarios, and can also make authorization behavior inconsistent until the user logs in again.
- Fix: Resolve `_current_participant()` by session `xid` first, then update username from OAuth on login as the code already does. Keep a temporary username fallback only for old sessions if needed, and test rename/stale-session behavior.
- Clean commit: `security: resolve participant sessions by stable xid`

### SEC-03: Conversation-scoped moderators can see the global participant list in the role form

- Severity: Medium
- Location: `v2/app.py:675-683`, `v2/templates/admin_conversation.html:258-271`, `v2/app.py:806-842`
- Evidence: `admin_conversation_detail()` is accessible to conversation-scoped moderators via `_require_mod_for_conv()` (`v2/app.py:675-678`) and loads all participants (`v2/app.py:682`). The template renders all participants in the "Add moderator" select (`v2/templates/admin_conversation.html:258-271`), even though role mutation endpoints are global-admin-only (`v2/app.py:806-842`).
- Impact: A moderator for one conversation can enumerate all platform participants. This is unnecessary data exposure and the form is misleading because the POST is restricted to global admins.
- Fix: Only query/render the global participant list and add/remove role controls when `_is_global_admin()` is true. For scoped moderators, render only the current conversation's moderator list or no role-management controls.
- Clean commit: `security: hide global role controls from scoped moderators`

### SEC-04: CSRF-exempt Particiapi bridge relies on permissive same-origin header checks

- Severity: Medium
- Location: `v2/app.py:266-295`, `v2/app.py:569-645`, `v2/app.py:1596-1602`, `v2/tests/test_proxy_blueprint.py:56-65`
- Evidence: The whole proxy blueprint is explicitly CSRF-exempt (`v2/app.py:1596-1602`). Unsafe proxy and statement-submission requests call `_validate_same_origin()` (`v2/app.py:293-295`, `v2/app.py:574-575`), but `_validate_same_origin()` allows requests with neither `Sec-Fetch-Site` nor `Origin` (`v2/app.py:269-276`). Tests assert that both blueprint routes remain CSRF-exempt (`v2/tests/test_proxy_blueprint.py:56-65`).
- Impact: SameSite cookies and modern browser headers reduce practical CSRF risk, and the statement route uses JSON. Still, the control is weaker than Flask-WTF CSRF for a cookie-authenticated state-changing boundary, especially through clients or intermediaries that omit both headers.
- Fix: Split `/c/<slug>/statements/new` out of the CSRF-exempt blueprint or manually validate Flask CSRF for that route. For the Particiapi proxy, make `_validate_same_origin()` fail closed for unsafe methods when both `Sec-Fetch-Site` and `Origin` are absent, unless an explicit trusted custom header/token is present. Add regression tests for missing-header unsafe requests.
- Clean commit: `security: harden csrf-exempt particiapi bridge`

### SEC-05: Production rate limiting is warning-only and may be per-worker

- Severity: Medium
- Location: `v2/app.py:82-85`, `v2/app.py:1520-1523`, `v2/guide_deployment.md:300-337`
- Evidence: Limiter defaults to no global limits and warns when `RATELIMIT_STORAGE_URI` is not set in non-debug mode (`v2/app.py:82-85`, `v2/app.py:1520-1523`). Deployment envvar setup does not list `RATELIMIT_STORAGE_URI` (`v2/guide_deployment.md:300-337`).
- Impact: Login, OAuth callback, reveal, accept, and dev-auth endpoints can be rate-limited only per worker/in memory. On multiple workers or replicas, limits are easier to bypass and less useful during credential stuffing, scripted probing, or availability attacks.
- Fix: Add `RATELIMIT_STORAGE_URI` to deployment docs/env examples and either fail closed in production when it is missing or explicitly mark the deployment as single-worker with accepted risk. Add a smoke test for production config warnings/failures.
- Clean commit: `security: require distributed rate-limit storage in production`

### SEC-06: Voluntary reveal retention behavior conflicts with the stated privacy model

- Severity: Medium
- Location: `v2/app.py:63-79`, `v2/db.py:91-95`, `v2/tests/test_reveal.py:138-157`, `v2/pub_privacy.md:52-74`, `v2/docs/plan_doc-improvement.md:373`
- Evidence: Code nullifies `public_username` and `revealed_at` after the reveal window (`v2/app.py:63-79`), and tests assert that behavior (`v2/tests/test_reveal.py:138-157`). The draft privacy doc says a voluntary public connection is permanent (`v2/pub_privacy.md:52-74`), and the doc-improvement decision register says current code still needs reconciliation (`v2/docs/plan_doc-improvement.md:373`).
- Impact: This is a privacy and data-integrity risk: participants and operators can receive conflicting promises about whether public reveal links are permanent or later removed.
- Fix: Pick one model and make code, tests, UI copy, privacy doc, and functional spec agree. If the permanent reveal model is intended, remove `_nullify_expired_reveals()` for `public_username` and implement a separate internal-link retention mechanism.
- Clean commit: `privacy: reconcile voluntary reveal retention model`

### SEC-07: Production host allowlist is not configured in Flask

- Severity: Low
- Location: `v2/app.py:96-103`, `v2/app.py:1432-1512`
- Evidence: `_safe_redirect()` trusts `request.host_url` to decide same-host redirects (`v2/app.py:96-103`), but app initialization does not configure Flask `TRUSTED_HOSTS` or an equivalent host allowlist (`v2/app.py:1432-1512`).
- Impact: Toolforge may enforce host routing before Flask sees requests, but that control is not visible in repo code. If a permissive edge passes attacker-controlled Host headers, redirects and URL generation can be confused.
- Fix: Set `TRUSTED_HOSTS` in production config, for example `['wiki-polis.toolforge.org']` plus explicit staging host(s). Document the env var for staging/prod.
- Clean commit: `security: configure trusted hosts`

### SEC-08: Direct script entrypoint runs Flask with `debug=True`

- Severity: Low
- Location: `v2/app.py:1893-1896`, `wsgi.py:1-10`, `deploy.sh:64-66`
- Evidence: Direct execution of `v2/app.py` runs `app.run(debug=True)` (`v2/app.py:1895-1896`). Production uses Toolforge/uWSGI via `wsgi.py` and `deploy.sh`, so this is not the documented production path.
- Impact: If someone starts the app directly on an exposed interface or host, the Werkzeug debugger can expose code execution. Current deployment docs reduce likelihood.
- Fix: Remove `debug=True` from the direct entrypoint, or gate it with explicit local-only env checks and host binding. Prefer using `flask --app app run` for local dev.
- Clean commit: `security: remove debug direct app runner`

### SEC-09: Flash toast rendering uses `innerHTML`

- Severity: Low
- Location: `v2/templates/base.html:61-76`, `v2/app.py:785-792`
- Evidence: Flash messages are serialized with `tojson`, then concatenated into `innerHTML` (`v2/templates/base.html:61-73`). One flash message includes admin-supplied `mw_username` (`v2/app.py:785-792`).
- Impact: This is outside requested steps 1-5, but it is worth fixing before a full browser-security pass. The immediate attacker path appears admin-only, but `innerHTML` should not be used for untrusted strings.
- Fix: Build the toast DOM with `createElement()` and `textContent` for the message.
- Clean commit: `security: render flash toasts without innerHTML`

## Granular clean commit plan

| Order | Commit title | Findings | Files likely touched | Test expectation |
|---:|---|---|---|---|
| 1 | `security: gate fake login to local debug only` | SEC-01 | `v2/app.py`, `v2/tests/test_security.py`, `v2/guide_local-dev.md` | production-like app does not register `/dev/login/<user>` |
| 2 | `security: resolve participant sessions by stable xid` | SEC-02 | `v2/app.py`, `v2/tests/test_auth.py`, `v2/tests/test_conversations.py` | stale username session resolves by `xid`; rename test still passes |
| 3 | `security: hide global role controls from scoped moderators` | SEC-03 | `v2/app.py`, `v2/templates/admin_conversation.html`, `v2/tests/test_admin.py` | scoped moderator cannot enumerate all participants; global admin still can grant roles |
| 4 | `security: harden csrf-exempt particiapi bridge` | SEC-04 | `v2/app.py`, `v2/templates/conversation.html`, `v2/tests/test_proxy_blueprint.py` | unsafe missing-header proxy requests fail; statement submit has CSRF or fail-closed origin checks |
| 5 | `security: require distributed rate-limit storage in production` | SEC-05 | `v2/app.py`, `v2/.env.example`, `v2/guide_deployment.md`, tests | production config documents or enforces `RATELIMIT_STORAGE_URI` |
| 6 | `privacy: reconcile voluntary reveal retention model` | SEC-06 | `v2/app.py`, `v2/db.py` if needed, `v2/tests/test_reveal.py`, `v2/pub_privacy.md`, `v2/spec_functional-design.md` | code/tests/docs agree on permanent reveal vs nullification |
| 7 | `security: configure trusted hosts` | SEC-07 | `v2/app.py`, `v2/.env.example`, `v2/guide_deployment.md`, `v2/tests/test_security.py` | unexpected Host header rejected in production-like config |
| 8 | `security: remove debug direct app runner` | SEC-08 | `v2/app.py`, `v2/guide_local-dev.md` | Bandit no longer reports `B201` for live app |
| 9 | `security: render flash toasts without innerHTML` | SEC-09 | `v2/templates/base.html`, optional frontend smoke test | malicious-looking flash text renders as text, not HTML |
| 10 | `docs: add route authorization matrix` | Cross-cutting | `v2/docs/` or root security docs | Route matrix documents public/auth/admin/moderator boundaries |

## Existing controls worth keeping

- OAuth uses state and PKCE (`v2/app.py:1778-1796`, `v2/app.py:1801-1827`).
- OAuth login clears the prior session before writing authenticated identity (`v2/app.py:1855-1859`).
- Sessions are server-side via Flask-Session/SQLAlchemy, with `HttpOnly`, `SameSite=Lax`, bounded lifetime, and `Secure` when not debug (`v2/app.py:1481-1487`).
- Normal Flask form routes are covered by Flask-WTF CSRF; templates include `csrf_token()` on POST forms.
- Conversation-scoped moderator routes mostly use `_require_mod_for_conv()` (`v2/app.py:232-237`).
- Participant argument routes enforce active/unpaused/phase-enabled and participation via `_require_arg_participation()` (`v2/app.py:521-533`).
- Invite-only access allows invited users or already-joined participants and blocks others (`v2/app.py:240-261`, tests at `v2/tests/test_conversations.py:133-168`).
- CSP and response security headers are set on every response (`v2/app.py:1575-1592`, test at `v2/tests/test_security.py:8-17`).
- Particiapi proxy rejects `..` path segments and non-API paths (`v2/app.py:297-299`) and has regression tests (`v2/tests/test_proxy_blueprint.py:126-140`).

## Assumptions and residual risk

- Assumption: production is served through Toolforge/uWSGI using root `wsgi.py`, not by directly running `python v2/app.py`.
- Assumption: Toolforge or upstream routing restricts Host headers; repo code does not currently prove that.
- Assumption: Particiapi and Polis are private-network only as described in `v2/guide_deployment.md`; runtime firewall state was not verified.
- Residual risk: dependency CVE review did not audit exact `uv.lock` versions because `uv` is not installed in this shell.
- Residual risk: browser-side XSS review was not fully completed because the requested slice was steps 1-5; SEC-09 is an early browser-security observation to fix before the next phase.
