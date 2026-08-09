# Route authorization matrix

This matrix describes the production routes served by `v2/app.py`. It is a
security reference for reviews and route changes; update it when routes move
between blueprints or authorization policy changes.

## Public routes

| Routes | Methods | Authorization |
|---|---|---|
| `/` | GET | Public. Shows public active conversations when logged out; shows participant-specific dashboard when logged in. |
| `/login` | GET | Public, rate-limited. Starts Wikimedia OAuth or local dev login when explicitly configured. |
| `/oauth-callback` | GET | Public, rate-limited. Requires matching OAuth state and PKCE verifier from the browser session. |
| `/health` | GET | Public, limiter-exempt. Returns DB and Particiapi reachability only. |
| `/c/<slug>/moderation-log` | GET | Public. Shows conversation-level ban/unban events with pseudonyms and moderator names, excluding private reasons. |
| `/help/statements`, `/help/arguments` | GET | Public. Static statement/argument writing-guidance pages (no auth). |
| `/static/*` | GET | Public static assets. |

## Participant routes

| Routes | Methods | Authorization |
|---|---|---|
| `/accept/<slug>` | GET, POST | `login_required`; invite-only conversations require an invite, existing participation, or moderator access. POST is rate-limited and creates one participation. |
| `/accept/<slug>/pseudonyms` | GET | `login_required`, rate-limited. Conversation must exist. |
| `/c/<slug>` | GET | `login_required`; invite-only access check; redirects non-participants to the accept flow. |
| `/c/<slug>/statements/new` | POST | `login_required`; Flask-WTF CSRF-protected participant route. Also requires same-origin browser provenance headers, active/unpaused submission phase, current participation, and per-participant quota. |
| `/c/<slug>/reveal` | GET, POST | `login_required`; current participant must have joined the closed conversation. POST is rate-limited, requires confirmation, and is only accepted during the reveal window. |
| `/c/<slug>/outputs/<output_key>` | GET | `login_required`; `_check_conversation_access` plus current participation (non-participants are redirected to the accept flow). |
| `/c/<slug>/report` | GET | **No `@login_required` decorator.** Only reachable once `conv.closed_at` is set (otherwise redirects to the results tab); `_check_conversation_access` applies. Login is required when `phase_personal_results` is set; public when `phase_public_results` is set. |
| `/c/<slug>/phase6/vote` | POST | **Hand-rolled auth (not `@login_required`):** active/unpaused conversation; either a demo session bound to this demo conversation, or `username` in session; current participation; not banned. Rate-limited; CSRF-validated (participant_bp). |
| `/logout` | POST | `login_required`; clears the Flask session. |

## Participant argument routes

| Routes | Methods | Authorization |
|---|---|---|
| `/c/<slug>/featured-statements/<fs_id>/arguments` | POST | `login_required`; `_require_arg_participation()` requires active, unpaused, argument phase enabled, and current participant membership. |
| `/c/<slug>/featured-statements/<fs_id>/skip/<side>` | POST | Same as submit; side must be `pro` or `con`. |
| `/c/<slug>/arguments/<arg_id>/vote` | POST | Same as submit; also enforces side gates, vote cap, not hidden, and not own argument. |
| `/c/<slug>/arguments/<arg_id>/unvote` | POST | Same as submit; argument must belong to a featured statement in the same conversation. |
| `/c/<slug>/arguments/<arg_id>/hide` | POST | `login_required`; current participant must be able to moderate the conversation. |
| `/c/<slug>/arguments/<arg_id>/unhide` | POST | Same as hide. |
| `/c/<slug>/arguments/<fs_id>/submit` | POST | Legacy compatibility redirect to `/c/<slug>/featured-statements/<fs_id>/arguments` using HTTP 307. |
| `/c/<slug>/arguments/<fs_id>/<side>/skip` | POST | Legacy compatibility redirect to `/c/<slug>/featured-statements/<fs_id>/skip/<side>` using HTTP 307. |
| `/c/<slug>/arguments/<arg_id>/flag` | POST | Same as submit; category is allowlisted and optional note is HTML-stripped before creating an open moderation flag. |
| `/c/<slug>/statements/<tid>/flag` | POST | `login_required`; current participant must have joined the active, unpaused conversation and must not be banned. Category is allowlisted and optional note is HTML-stripped. |

## Global-admin routes

| Routes | Methods | Authorization |
|---|---|---|
| `/admin` | GET | `login_required` and `admin_required`. |
| `/admin/conversations/new` | POST | `login_required` and `admin_required`. |
| `/admin/conversations/<conv_id>/edit` | POST | Conversation organizer or global admin. |
| `/admin/conversations/<conv_id>/pause` | POST | `login_required` and `admin_required`. |
| `/admin/conversations/<conv_id>/close` | POST | `login_required` and `admin_required`. |
| `/admin/conversations/<conv_id>/delete` | POST | `login_required` and `admin_required`; re-checks authoritative Polis latest-vote count and only deletes when it is exactly zero. |
| `/admin/conversations/<conv_id>/phases` | POST | `login_required` and `admin_required`. |
| `/admin/conversations/<conv_id>/phase/advance` | POST | Conversation organizer or global admin. |
| `/admin/global-admins/add` | POST | `login_required` and `admin_required`. |
| `/admin/global-admins/<participant_id>/remove` | POST | `login_required` and `admin_required`. |
| `/admin/roles/add` | POST | `login_required` and `admin_required`. |
| `/admin/roles/<role_id>/remove` | POST | `login_required` and `admin_required`. |
| `/admin/conversations/<conv_id>/recommendations` | POST | `login_required` and `admin_required`. Sets the recommended-quantities tier. |
| `/admin/conversations/<conv_id>/phase/schedule` | POST | `login_required` and `admin_required`. Sets or cancels a scheduled phase transition. |

## Conversation moderator routes

These routes allow either a global admin or a participant with an `AdminRole` for
the specific conversation. The shared authorization helper is
`_require_mod_for_conv(conv_id)`.

| Routes | Methods | Authorization |
|---|---|---|
| `/admin/conversations/<conv_id>` | GET | Conversation moderator or global admin. Global role controls are rendered only for global admins. |
| `/admin/conversations/<conv_id>/invites` | GET | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/invites/add` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/invites/<invite_id>/remove` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/participants` | GET | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/participants/<participant_id>/ban` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/participants/<participant_id>/unban` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/flags` | GET | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/flags/<flag_id>/resolve` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/statements` | GET | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/statements/<tid>/moderate` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/statements/seed` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/statements/seed/import-text` | POST | Conversation moderator or global admin (`_require_mod_for_conv`); rate-limited. Paste-text bulk seed import. |
| `/admin/conversations/<conv_id>/phase6/init` | POST | Conversation moderator or global admin (`_require_mod_for_conv`). Highest-consequence route: creates a dedicated Polis conversation and seeds the confirmed featured statements into it. |
| `/admin/conversations/<conv_id>/strict-moderation` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/featured` | GET | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/featured/confirm` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/featured/add` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/featured/<fs_id>/remove` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/arguments/<arg_id>/delete` | POST | Conversation moderator or global admin. |
| `/admin/conversations/<conv_id>/arguments/<arg_id>/moderate` | POST | Conversation moderator or global admin. Sets the local argument hidden/unhidden state. |

## Particiapi bridge

| Routes | Methods | Authorization |
|---|---|---|
| `/proxy/particiapi/<path>` | GET, POST, PUT | `login_required`. Path must stay under `api/` and reject `..` segments. Unsafe methods require same-origin browser provenance headers. |
| `/c/<slug>/proxy/particiapi/<path>` | GET, POST, PUT | Per-conversation scoped proxy (#246): conversation-scoped identity + path-scoped session cookie, so a participant gets a different Polis uid per conversation. Demo-aware auth via `_proxy_auth_response` (not `@login_required`, so demo sessions work); same `api/` path constraints as the global proxy. |

## Dev-login routes (gated)

Most of these run only in local debug, but `/dev/login/<username>` additionally has a
**token-gated path that runs on the staging Toolforge app** — see its row.

| Routes | Methods | Authorization |
|---|---|---|
| `/dev-login` | GET | Registered only when Flask debug mode is on, `DEV_LOGIN_USER` is set, and the app is **not** on Toolforge. |
| `/dev/login/<username>` | GET | Registered when **either** (a) local fake-login is on — Flask debug mode, `DEV_FAKE_LOGIN=1`, and **not** on Toolforge — **or** (b) staging dev-login is enabled: the app **is** the staging Toolforge app and a `staging-dev-token` secret of ≥32 chars is set. On path (b) the request must present a matching per-username HMAC `?token=` or it is rejected with `403`. Rate-limited. |
