# Route authorization matrix

> **Class: tracks-code reference.** Verified against `bf07842` (2026-09-28) by enumerating
> the live `app.url_map` and reading the app-layer function each endpoint delegates to.
> Every `app.py:<line>` below was checked to point at the `def` it names.
>
> **Planned:** a generator that walks `app.url_map` and fails with a non-zero exit on a
> route it cannot classify, so drift is a red build rather than a stale paragraph. Until it
> exists, this file is hand-maintained and the stamp above is the only thing that makes it
> trustworthy.

This is the security reference for reviewing route additions and authorization
changes. It is a *reference to the code*, not a design document — for why the system
is shaped this way see [`../spec_architecture.md`](../spec_architecture.md) and
[`../adr/0004-versioned-browser-api-and-spa.md`](../adr/0004-versioned-browser-api-and-spa.md).

---

## How authorization works in this codebase

The thing to know before reading the tables: **there are no per-view authorization
decisions left in the route layer.** The React SPA owns every page, so Flask serves
three kinds of thing, and only two of them carry an authorization decision:

1. **The SPA shell.** 22 canonical paths (`_SPA_ROUTE_PATTERNS`, `app.py:2362`) plus the
   `/app/*` mirror are answered by the `_serve_canonical_spa_request` before-request hook
   (`app.py:5671`) and the `spa_shell` view (`app.py:5970`). The shell is **public** —
   it is one static document with no user data in it. The `before_request` hook touches
   `request.host` on purpose, so `TRUSTED_HOSTS` validation still applies.
2. **The JSON API.** All 61 `/api/v1/*` routes. This is where authorization actually
   happens. `v2/api/v1.py` and `v2/api/admin_routes.py` are **thin adapters**: they
   validate the request body and translate exceptions into the error envelope, and they
   contain no authorization logic at all. Every decision is made by the app-layer
   function each adapter delegates to, wired by keyword in `create_app`
   (`app.py:5744-5813`).
3. **A handful of non-API routes** — OAuth, health, logout, and the voucher entry form.
   These do carry their own checks, and they are listed separately below.

The consequence worth internalising: **adding a shell path grants no access.** A page at
`/admin/conversations/1/statements` is reachable by anyone; what is not reachable is the
data on it, because the SPA has to call `GET /api/v1/admin/conversations/1/statements`,
and that route requires a conversation role. The `before_request` SPA table is therefore
not an authorization surface, and it is checked by a different mechanism —
`tests/test_spa_canonical_routes.py` parses every `<Route path=…>` out of the SPA's
`frontend/src/**/*.tsx` and asserts the allowlist covers it, so a React route with no
server counterpart fails the suite.

### The five authorization helpers

Every classification in the tables reduces to one of these. They are defined in
`app.py` and are the only places an authorization decision is made.

| Helper | Location | Grants |
|---|---|---|
| `_is_global_admin()` | `app.py:2228` | `Participant.is_global_admin`, or a username in `ADMIN_USERS` |
| `_require_organizer_for_conv(conv_id)` | `app.py:3399` | the above, or `AdminRole(role='organizer')` for **that** conversation |
| `_require_mod_for_conv(conv_id)` | `app.py:3391` | the above, or any `AdminRole` for **that** conversation |
| `_check_conversation_access(conv, participant)` | `app.py:4531` | passes when the conversation's own access policy allows this participant; raises `AccessRequired` (403 `access_required`) otherwise |
| `_require_{explore,argument,informed_voting}_api_context(slug)` | `app.py:2744`, `3108`, `2861` | access policy **plus** a current participation **plus** the phase being open, **plus** not banned |

Two properties these preserve, both worth keeping in mind when reviewing a change:

- **Roles are conversation-scoped and non-transitive.** `_require_mod_for_conv` looks up
  `AdminRole` filtered on `conversation_id`, so a moderator of conversation A gets 403 on
  conversation B. There is no "moderator of a conversation can see the admin index" path:
  the admin catalog is `_is_global_admin()` only (`app.py:3492`).
- **A participation is not an access shortcut.** `app.py:4532-4537` states this
  explicitly: the access decision is made from the conversation's policy, and an existing
  participation is checked separately by the `_require_*_api_context` helpers.

### Error codes

`401 unauthorized` means no Flask session. `403 forbidden` means a role check failed.
`403 access_required` means the conversation's access policy refused you. `409 conflict`
means you passed the checks but the conversation is not in a phase that permits the
action. The distinction between the two 403s is deliberate and the SPA depends on it:
`access_required` is what triggers the join flow rather than an error.

**Ordering caveat for security review:** the API blueprints validate the request body
*before* delegating, so on a malformed body an unauthenticated caller gets
`400 validation_failed` rather than `401`/`403`. This is visible on 20 of the write
endpoints. It leaks nothing beyond "this request shape is or is not well formed", but it
does mean a naive "does an anonymous caller get 401?" probe returns a misleading answer
on those routes — send a schema-valid body when sweeping.

---

## Participant API — `/api/v1/conversations/*`

22 routes. All are same-origin JSON, CSRF-protected by the global `CSRFProtect`
(`app.py:1706`), and the SPA passes the token it reads from `GET /api/v1/session`.

| Route | Method | Authorization | Enforced by |
|---|---|---|---|
| `/api/v1/conversations` | GET | public; personalised when logged in | `_conversation_lane_api_payload` (app.py:2395) |
| `/api/v1/conversations/<slug>/about` | GET | conversation access policy + logged-in participant | `_conversation_about_api_payload` (app.py:2531) |
| `/api/v1/conversations/<slug>/workspace` | GET | conversation access policy + logged-in participant | `_conversation_workspace_api_payload` (app.py:2421) |
| `/api/v1/conversations/<slug>/moderation-log` | GET | conversation access policy + logged-in participant | `_moderation_log_api_payload` (app.py:2542) |
| `/api/v1/conversations/<slug>/outputs/<output_key>` | GET | conversation access policy + logged-in participant | `_conversation_output_api_payload` (app.py:2574) |
| `/api/v1/conversations/<slug>/participation-entry` | GET | conversation access policy + logged-in participant | `_participation_entry_api_payload` (app.py:2694) |
| `/api/v1/conversations/<slug>/pseudonym-suggestions` | GET | conversation access policy + logged-in participant | `_pseudonym_suggestions_api_payload` (app.py:2703) |
| `/api/v1/conversations/<slug>/participation` | POST | conversation access policy; runs the join-eligibility check | `_join_conversation_api_payload` (app.py:2710) |
| `/api/v1/conversations/<slug>/results` | GET | conversation access policy; **no login needed once `phase_public_results` is set** — 401 only while the conversation is personal-results-only, 409 before results are published | `_results_report_api_payload` (app.py:3023) |
| `/api/v1/conversations/<slug>/intermediate-results` | GET | conversation access policy; **no login needed once `phase_public_results` is set** — 401 only while the conversation is personal-results-only, 409 before results are published | `_intermediate_results_api_payload` (app.py:3065) |
| `/api/v1/conversations/<slug>/flags` | POST | conversation access policy + logged-in participant | `_submit_content_flag_api_payload` (app.py:3200) |
| `/api/v1/conversations/<slug>/identity-reveal` | GET | conversation access policy + logged-in participant | `_identity_reveal_api_payload` (app.py:2659) |
| `/api/v1/conversations/<slug>/identity-reveal` | POST | conversation access policy + logged-in participant | `_reveal_identity_api_payload` (app.py:2663) |
| `/api/v1/conversations/<slug>/explore` | GET | participation + explore phase open | `_explore_api_payload` (app.py:2817) |
| `/api/v1/conversations/<slug>/statements/<int:statement_id>/vote` | PUT | participation + explore phase open | `_explore_vote_api_payload` (app.py:2828) |
| `/api/v1/conversations/<slug>/statements` | POST | participation + explore phase open | `_statement_api_payload` (app.py:3253) |
| `/api/v1/conversations/<slug>/arguments` | GET | participation + argument phase open | `_argument_mapping_api_payload` (app.py:3085) |
| `/api/v1/conversations/<slug>/featured-statements/<int:featured_statement_id>/arguments` | POST | participation + argument phase open | `_submit_argument_api_payload` (app.py:3133) |
| `/api/v1/conversations/<slug>/featured-statements/<int:featured_statement_id>/contributions/<side>/skip` | PUT | participation + argument phase open | `_skip_argument_api_payload` (app.py:3161) |
| `/api/v1/conversations/<slug>/arguments/<int:argument_id>/priority` | PUT | participation + argument phase open | `_set_argument_priority_api_payload` (app.py:3180) |
| `/api/v1/conversations/<slug>/informed-voting` | GET | participation + informed-voting phase open | `_informed_voting_api_payload` (app.py:2952) |
| `/api/v1/conversations/<slug>/featured-statements/<int:featured_statement_id>/informed-vote` | PUT | participation + informed-voting phase open | `_informed_vote_api_payload` (app.py:2989) |

Two rows carry a clarification a table of routes cannot know. `…/results` and
`…/intermediate-results` are **not** participant-gated: both abort 401 only when
`phase_personal_results` is set *and* `phase_public_results` is not
(`app.py:3029`, `app.py:3071`), so a published report is world-readable. That is the
normal state — `_publish_final_report` sets `phase_public_results = True` on every
publish (`app.py:1374`). Both abort 409 when neither flag is set.

The public bootstrap routes — `/api/v1/session`, `/api/v1/i18n/<locale>`,
`/api/v1/openapi.json` — are listed under "Public routes" below. 22 + 3 + 36 = the 61
`/api/v1/*` routes.

---

## Admin API — `/api/v1/admin/*`

36 routes. Note the tiering: this is **not** a flat "admin" surface. Site-wide acts are
global-admin-only, conversation-scoped acts are moderator-or-better, and three settings
routes are organizer-or-better. Publishing the final report, pausing, archiving,
scheduling a transition and setting the phase set are deliberately *not* available to a
conversation organizer — a conversation-scoped organizer cannot end a consultation.

Two rows carry a clarification a table of routes cannot know: role *grant* is
global-admin-only even though role *listing* is moderator-gated
(`_replace_admin_roles_api_payload` calls `_require_mod_for_conv` and then
`_is_global_admin()` itself, `app.py:4428-4429`), and `POST …/participation`
additionally runs the join-time eligibility check.

| Route | Method | Authorization | Enforced by |
|---|---|---|---|
| `/api/v1/admin` | GET | **global admin only** | `_admin_catalog_api_payload` (app.py:3492) |
| `/api/v1/admin/conversations` | POST | **global admin only** | `_create_admin_conversation_api_payload` (app.py:3507) |
| `/api/v1/admin/global-admin-grants` | POST | **global admin only** | `_grant_global_admin_api_payload` (app.py:3559) |
| `/api/v1/admin/global-admins/<int:participant_id>` | PUT | **global admin only** | `_set_global_admin_api_payload` (app.py:3580) |
| `/api/v1/admin/conversations/<id>` | DELETE | **global admin only** | `_delete_admin_conversation_api_payload` (app.py:4206) |
| `/api/v1/admin/conversations/<id>/termination` | GET | **global admin only** | `_admin_termination_api_payload` (app.py:3776) |
| `/api/v1/admin/conversations/<id>/pause` | PUT | **global admin only** | `_set_admin_pause_api_payload` (app.py:4332) |
| `/api/v1/admin/conversations/<id>/archive` | PUT | **global admin only** | `_set_admin_archive_api_payload` (app.py:4347) |
| `/api/v1/admin/conversations/<id>/schedule` | PUT | **global admin only** | `_set_admin_schedule_api_payload` (app.py:4363) |
| `/api/v1/admin/conversations/<id>/phases` | PUT | **global admin only** | `_set_admin_phases_api_payload` (app.py:4387) |
| `/api/v1/admin/conversations/<id>/publication` | POST | **global admin only** | `_publish_admin_report_api_payload` (app.py:4407) |
| `/api/v1/admin/conversations/<id>/phase` | PUT | conversation **organizer** or global admin | `_advance_admin_phase_api_payload` (app.py:4295) |
| `/api/v1/admin/conversations/<id>/recommendation-tier` | PUT | conversation **organizer** or global admin | `_update_admin_recommendation_tier_api_payload` (app.py:4264) |
| `/api/v1/admin/conversations/<id>/settings` | PUT | conversation **organizer** or global admin | `_update_admin_settings_api_payload` (app.py:4230) |
| `/api/v1/admin/conversations/<id>/settings` | GET | moderator or global admin; the demo-access switch is global-admin only | `_admin_settings_api_payload` (app.py:3758) |
| `/api/v1/admin/conversations/<id>` | GET | moderator or global admin | `_admin_lifecycle_api_payload` (app.py:3622) |
| `/api/v1/admin/conversations/<id>/roles` | GET | moderator or global admin; role grant/revoke is global-admin only | `_admin_role_roster_api_payload` (app.py:3600) |
| `/api/v1/admin/conversations/<id>/roles/<int:participant_id>` | PUT | moderator **and** global admin | `_replace_admin_roles_api_payload` (app.py:4425) |
| `/api/v1/admin/conversations/<id>/participants` | GET | moderator or global admin | `_admin_participant_roster_api_payload` (app.py:3420) |
| `/api/v1/admin/conversations/<id>/participants/<int:participant_id>/access` | PUT | moderator or global admin | `_set_admin_participant_access_api_payload` (app.py:3432) |
| `/api/v1/admin/conversations/<id>/invitations` | GET | moderator or global admin | `_admin_invitation_roster_api_payload` (app.py:3476) |
| `/api/v1/admin/conversations/<id>/invitations` | PUT | moderator or global admin | `_add_admin_invitations_api_payload` (app.py:4456) |
| `/api/v1/admin/conversations/<id>/invitations/<int:invite_id>` | DELETE | moderator or global admin | `_remove_admin_invitation_api_payload` (app.py:4479) |
| `/api/v1/admin/conversations/<id>/statements` | GET | moderator or global admin | `_admin_statements_api_payload` (app.py:3812) |
| `/api/v1/admin/conversations/<id>/statements` | POST | moderator or global admin | `_add_admin_seed_statement_api_payload` (app.py:3975) |
| `/api/v1/admin/conversations/<id>/statements/<int:statement_id>/moderation` | PUT | moderator or global admin | `_moderate_admin_statement_api_payload` (app.py:3895) |
| `/api/v1/admin/conversations/<id>/statement-moderation-policy` | PUT | moderator or global admin | `_set_admin_statement_policy_api_payload` (app.py:3884) |
| `/api/v1/admin/conversations/<id>/statement-imports` | POST | moderator or global admin | `_import_admin_seed_statements_api_payload` (app.py:3939) |
| `/api/v1/admin/conversations/<id>/featured-statements` | GET | moderator or global admin | `_admin_featured_api_payload` (app.py:4011) |
| `/api/v1/admin/conversations/<id>/featured-statements/<int:statement_id>` | PUT | moderator or global admin | `_select_admin_featured_api_payload` (app.py:4062) |
| `/api/v1/admin/conversations/<id>/featured-selections/<int:featured_id>` | DELETE | moderator or global admin | `_remove_admin_featured_api_payload` (app.py:4106) |
| `/api/v1/admin/conversations/<id>/featured-arguments/<int:argument_id>` | PUT | moderator or global admin | `_set_admin_featured_argument_api_payload` (app.py:4153) |
| `/api/v1/admin/conversations/<id>/featured-arguments/<int:argument_id>` | DELETE | moderator or global admin | `_delete_admin_featured_argument_api_payload` (app.py:4179) |
| `/api/v1/admin/conversations/<id>/flags` | GET | moderator or global admin | `_admin_flag_queue_api_payload` (app.py:4811) |
| `/api/v1/admin/conversations/<id>/flags/<int:flag_id>/resolution` | PUT | moderator or global admin | `_resolve_admin_flag_api_payload` (app.py:4824) |
| `/api/v1/admin/conversations/<id>/phase6-initialization` | POST | moderator or global admin | `_initialize_admin_phase6_api_payload` (app.py:4323) |

`/phase6-initialization` is the highest-consequence moderator route: it creates a second
Polis conversation and seeds the confirmed featured statements into it. It has dedicated
integration coverage in `tests/test_admin_lifecycle_api.py` (three tests, including the
unknown-outcome path); a change here should keep it.

Route parameters are abbreviated in the table above (`<int:conversation_id>` → `<id>`,
`<int:participant_id>` → `<pid>`) purely to fit the page.

---

## Public routes

| Route | Method | Authorization | Notes |
|---|---|---|---|
| `/api/v1/session` | GET | **public** | Login state, the CSRF token, enabled locales, `capabilities.administerSite`, the `developerLogins` list and the build's `gitVersion`. Served `no-store`. |
| `/api/v1/i18n/<locale>` | GET | **public** | Message catalogue. Rate-limited 120/min. Any locale may be requested, not only enabled ones — `?uselang=` is the deliberate translator/QA door. Cacheable for a week when the caller pins `?v=<gitVersion>`, `no-store` otherwise. |
| `/api/v1/openapi.json` | GET | **public** | The contract at `v2/openapi.json`, `servers[0].url = /api/v1`. 19 `test_openapi*` tests assert parts of it; none of them is an exhaustive route-vs-spec diff, so a new route with no spec entry would not fail the suite. |
| `/health` | GET | **public**, limiter-exempt | Reports only `SELECT 1` and a Particiapi reachability probe. No version, no config, no secrets. |
| `/login` | GET | **public**, rate-limited 20/min + per-site unauthenticated limit | Starts PKCE (S256) OAuth. The `state` and `code_verifier` are written to the Flask session here. |
| `/oauth-callback` | GET | **public**, rate-limited 30/min | Compares `?state=` against the session value, then exchanges the code with the session's verifier. |
| `/logout` | POST | `@login_required` | Clears the session. |
| `/c/<slug>/v` | GET, POST | **public** | Voucher redemption. 404s unless the conversation exists, is gated, and is `gating_type='voucher'`. Rate-limited on a per-session failure budget; POST is CSRF-protected. A linked code arrives as `?v=<code>` and is redeemed on open. |
| `/static/*` | GET | **public** | `Cache-Control: public, max-age=604800` on 200s. The SPA bundle's own URLs carry Vite's content hash, so a new build changes them; the git SHA is shown in the SPA footer and served by `/api/v1/session`. |

---

## SPA shell paths — no authorization decision

Served by `_serve_canonical_spa_request` (`app.py:5671`) from `_SPA_ROUTE_PATTERNS`
(`app.py:2362`), plus the `/app/*` mirror served by `spa_shell` (`app.py:5970`).
Anchored with `fullmatch`, so nothing else 404s into the shell.

```
/  /demo  /consultations  /help/statements  /help/arguments
/accept/<slug>  /c/<slug>  /c/<slug>/about  /c/<slug>/moderation-log
/c/<slug>/outputs/<output_key>  /c/<slug>/report  /c/<slug>/reveal
/admin  /admin/conversations/<id>  .../settings  .../termination  .../statements
.../featured  .../participants  .../flags  .../invites  .../roles
/app  /app/<path>
```

An allowlist rather than a catch-all, deliberately: a catch-all would make the branded
404 page unreachable for HTML and return 200 for every typo (`app.py:2344-2350`).
`tests/test_spa_canonical_routes.py` enforces the allowlist against the React router.

Note that a **linked voucher code** is handled before the shell is served:
`_linked_voucher_redirect()` (`app.py:389`) intercepts `/c/<slug>/v?v=<code>` and
`/c/<slug>?v=<code>` and redeems rather than serving the shell. The credential never
reaches the client bundle, and `Referrer-Policy: strict-origin` is applied on exactly
those paths.

---

## Dev-login routes (conditionally registered)

Neither route exists in a production deployment, and the conditions are `and`ed — not
`or`ed — so setting the env var alone on Toolforge does not register them.

| Route | Method | Registered when | Authorization |
|---|---|---|---|
| `/dev-login` | GET | Flask debug **and** `DEV_LOGIN_USER` set **and not** on Toolforge | debug-only; logs in as `DEV_LOGIN_USER`. 20/min |
| `/dev/login/<username>` | GET | `(debug and DEV_FAKE_LOGIN=1 and not on Toolforge)` **or** (on the staging Toolforge app **and** a `staging-dev-token` secret of ≥32 chars) | local path: open. Staging path: requires a per-username HMAC `?token=`, else 403. Rate-limited 30/min. |
| `/dev/error-page-check/<int:code>` | GET | same as `/dev/login/<username>` | `@login_required` **and** `@admin_required`; 403/404/500 only; 20/min |

The staging path is why `guide_testing-tiers.md` can say dev-login is "disabled on
staging" and still be accurate: it is disabled *for unauthenticated callers*, and the
token gate is what stands in for a real OAuth session. `_derive_xid`
(`app.py:591`) is called with a `dev-fake:` prefix for these accounts (`app.py:5908`) and
the `mw_user_id`s are negative, so they can never collide with a real Wikimedia account.

---

## What is no longer here

Recorded because the previous revision of this document described all of it, and
searching git history or an old branch should not be the way to discover that these
routes are gone. They were removed with the Jinja frontend (ADR 0004, #351).

- **The Particiapi proxy routes** `/proxy/particiapi/<path>` and
  `/c/<slug>/proxy/particiapi/<path>`. The SPA now talks to `/api/v1/*`, and Flask
  talks to Particiapi server-side. There is no browser-facing proxy to leave open.
- **Every HTML form route**: `/admin/conversations/new`, `/admin/roles/add`,
  `/c/<slug>/statements/new`, `/c/<slug>/featured-statements/<id>/arguments`,
  `/c/<slug>/reveal`, `/c/<slug>/outputs/<key>`, and the rest. All are SPA paths now.
- **`/c/<slug>/phase6/vote`** and its hand-rolled auth. The informed vote is
  `PUT /api/v1/conversations/<slug>/featured-statements/<id>/informed-vote`, with
  authorization via `_require_informed_voting_api_context`.
- **The legacy argument-vote and unvote POST routes**, and the 307 compatibility
  redirects to them.

---

## Coverage

The v2 audit probed all 36 admin `(method, path)` pairs — anonymous, as a
non-privileged participant, and as a global admin, with schema-valid bodies — and found
no route where a non-privileged caller is not denied (36/36 denied, 0 leaks). A separate
role-boundary probe confirmed an organizer of conversation A is denied on conversation B,
and that a moderator is denied the organizer- and global-admin-tier routes.

That probe is not in the suite. The 11 `tests/test_admin*.py` files contain 13 lines
that assert a 403, and two of them (`test_admin_featured_api.py`,
`test_admin_statements_api.py`) contain none, so a newly added admin route with no guard
would ship green. Adding the probe to `v2/tests/` is the highest-value follow-up to
this document.
