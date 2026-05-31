# wiki-polis v2 — Runtime Writes Audit

Audit date: 2026-05-31.
Baseline: `auditbranch/202605` @ `eaa47a9` (Merge PR #86 fix/proxy-next-url-after-login).
App: Flask dev server, port 5001, `FLASK_DEBUG=1`, `DEV_FAKE_LOGIN=1`.
DB: `v2/instance/dev.db` (SQLite, disposable).
Particiapi: `http://127.0.0.1:8002` (Docker, healthy). Polis server: `http://127.0.0.1:8003`.
Non-admin participant: `dev-user-1` (mw_user_id=-1, id=2, is_global_admin=0).
Admin participant: `DevUser` (id=1, listed in ADMIN_USERS env var).

---

## HEAD verification

```
Resolved HEAD: eaa47a97a343ee05142a5a369a1693f72087efda  eaa47a9
Subject: Merge pull request #86 from lgelauff/fix/proxy-next-url-after-login
```

`main` was 3 commits ahead; stashed `v2/app.py`, `v2/templates/admin_featured.html`,
`v2/templates/admin_statements.html` before checkout.

---

## Startup observations

Flask log on start:
```
[WARNING] DEV MODE: SQLALCHEMY_DATABASE_URI forced to sqlite:///dev.db
  (ignoring database-url secret / DATABASE_URL env)
[WARNING] POLIS_PUBLIC_URL is not https:// — ignoring
[UserWarning] Using the in-memory storage for tracking rate limits ...
  not recommended for production use.
```

The DB isolation guard at `v2/app.py:392-402` fires correctly; dev.db in `instance/` is the
live path (`sqlite:///dev.db` resolves relative to `v2/` → `v2/instance/dev.db`).
Rate limiter state is in-process-memory only (default).

---

## Identifier map

| Identifier | Column | Example value | Used by |
|---|---|---|---|
| URL slug | `conversations.slug` | `cats-vs-dogs-rtyhvm0czb` | Flask routes `/accept/<slug>`, `/c/<slug>` |
| Polis zinvite | `conversations.polis_id` | `rtyhvm0czb` | Web component `conversation-id=`, proxy URL, Polis/Particiapi API calls |
| Pseudonym | `participations.pseudonym` | `dainty-coot` | Template `data-my-pseudonym=`, argument `proposer` display |
| xid | `participants.xid` | `4bc1ca6…` (sha256 of mw_user_id) | Passed to Particiapi as participant token; stored in session |

**The URL slug and polis_id are distinct.** `/accept/<slug>` and `/c/<slug>` both resolve via
`Conversation.query.filter_by(slug=slug)` (`v2/app.py:710`, `v2/app.py:905`). The web
component on the conversation page receives `conversation-id="rtyhvm0czb"` (the `polis_id`),
not the URL slug. The URL slug for the test conversation (`cats-vs-dogs-rtyhvm0czb`) embeds
the polis_id as a suffix, but this is a naming convention in the test data, not a structural
constraint — the slug field has its own unique constraint and value.

---

## Step 1 — POST /accept/\<slug\>

**Request:** `POST /accept/cats-vs-dogs-rtyhvm0czb`, form fields:
`csrf_token=<valid>`, `pseudonym=dainty-coot`, `notify_email=`, `notify_talk_page=`.

**HTTP status:** 302 → `/c/cats-vs-dogs-rtyhvm0czb`.

**DB write — `participations` table:**
```
id=3, participant_id=2, conversation_id=1,
pseudonym="dainty-coot",
accepted_at="2026-05-31 13:43:47.924365",
notify_email=0, notify_talk_page=0,
new_stmt_ids=[]
```

Tables written: `participations` (1 INSERT). No other tables.

**First failed attempt (HTTP 400):** Initial `curl` attempt with `-c`/`-b` flags used
stale CSRF token from a prior non-redirect GET. The second GET with `-L` follow-redirects
produced a page with the session cookie active and a valid CSRF token. Observation: CSRF
validation fires before pseudonym validation — an invalid CSRF returns 400 regardless of
other field values.

**No outbound calls** made for this route.

**Side effect on `/c/<slug>` load:** Calling `GET /c/<slug>` after accept triggers
`_build_featured_data` (`v2/app.py:811`), which creates `ArgumentSideState` rows as a side
effect — one per (participant, featured_statement, side) combination. For 10 featured
statements on conv_id=1, this created **20 rows** in `argument_side_states` (ids 21–40),
all with `skipped=0` and `argument_order` pre-populated from existing arguments. This
write occurs on the first GET of the conversation page, before any user action.

---

## Step 2 — Argument gate mechanics

**Gate condition** (verified against `v2/app.py:1089-1095`):
```
pro_gate = bool(pro_proposed or (pro_state and pro_state.skipped))
con_gate = bool(con_proposed or (con_state and con_state.skipped))
if not (pro_gate and con_gate): → 403, reason="gate"
```

The gate is checked at the **vote** action, not on page load. Participants can see arguments
but cannot vote until BOTH sides are unlocked for a given featured statement.

**A side is unlocked by either:**
1. Submitting an argument on that side (`pro_proposed` or `con_proposed` is set), or
2. Explicitly skipping that side (`ArgumentSideState.skipped = True`).

**Gate does NOT depend on Polis votes** (votes through the web component proxy). Polis voting
and argument gating are completely independent state machines.

**Verified gate state transitions:**

| Action | pro_gate | con_gate | Vote attempt HTTP |
|---|---|---|---|
| Neither side done | False | False | 403 `reason="gate"` |
| Pro skipped only | True | False | 403 `reason="gate"` |
| Both sides skipped | True | True | 200 (vote succeeds) |

**DB writes for skip (`v2/app.py:1038-1066`):**

`POST /c/<slug>/arguments/<fs_id>/pro/skip` → HTTP 200 `{"ok":true}`
DB: `argument_side_states` row for `(participant_id=2, fs_id=1, side='pro')` updated:
`skipped: 0 → 1`. Idempotent: second skip call returns 200 with no change.

**`ArgumentSideState` rows are created on page-load** (`_build_featured_data`), not on
first skip. The skip endpoint finds the existing row and sets `skipped=True`.

---

## Step 3 — Argument writes

### Argument submit (`v2/app.py:982-1036`)

`POST /c/<slug>/arguments/<fs_id>/submit` with `side=pro`, `body=<text≤280 chars>`
Headers: `X-Requested-With: fetch` (JSON path).

**HTTP 200**, response shape: `{"ok": true, "id": <int>, "body": "<text>"}`.

**DB writes:**
1. `arguments` table: 1 INSERT — `(id=23, featured_statement_id=1, proposer_id=2, side='pro', hidden=0, body="Cats are low maintenance companions")`.
2. `argument_side_states` table: UPDATE to `argument_order` for `(participant=2, fs=1, side='pro')` — new arg_id inserted at random position: `[23, 1]`.

**Duplicate submit** (same participant, same FS, same side): returns existing argument without
INSERT — `{"ok": true, "id": 23, "body": "..."}`. The `UNIQUE(featured_statement_id, proposer_id, side)` constraint on `arguments` is the enforcement point; the route checks with `.first()` before inserting (`v2/app.py:993-1001`).

### Argument vote (`v2/app.py:1068-1131`)

`POST /c/<slug>/arguments/<arg_id>/vote` with `X-Requested-With: fetch`.

**HTTP 200**, response: `{"ok": true}`.

**DB write:** `argument_votes` table: 1 INSERT — `(argument_id, participant_id, value=NULL)`.

**`value` column confirmed NULL.** All 9 `argument_votes` rows for participant_id=2 have `value=''` (NULL). The ranking path (`value = rank position`) is never exercised; `argument_vote_data` has only `{"K": 2}` — no `vote_method: "ranking"` key in any conversation. Dead path confirmed at runtime.

**Gate check fires at vote time** (`v2/app.py:1076-1095`): reads `ArgumentSideState` and
`Argument` rows to compute `pro_gate`, `con_gate`. Aborts 403 `reason="gate"` if either is
False.

**Own-argument vote:** HTTP 403 `{"ok": false, "reason": "own"}`. DB not written.

### K-cap enforcement (`v2/app.py:1097-1109`)

K=2 (from `conv.argument_vote_data.get('K', 2)`). With 2 existing pro votes on fs_id=3
(arg_ids 25, 26), voting on a 3rd pro argument (arg_id=27):

**HTTP 409**, response: `{"ok": false, "reason": "cap"}`. DB not written.

The cap is per-side per-FS, counted by querying all arguments for that (FS, side) and
counting existing votes by this participant against those arg_ids.

### Argument unvote (`v2/app.py:1133-1147`)

`POST /c/<slug>/arguments/<arg_id>/unvote`.

**HTTP 200**, response: `{"ok": true}`.

**DB write:** `argument_votes` table: 1 DELETE matching `(participant_id, argument_id)`. If no
vote existed, returns 200 silently (no-op).

### Argument hide/unhide (`v2/app.py:1149-1173`)

`POST /c/<slug>/arguments/<arg_id>/hide` — **mod-only** (checks `_can_moderate(conv)`).

- Admin (DevUser): HTTP 302, `arguments.hidden` set `0→1` or `1→0`.
- Non-mod with valid CSRF: HTTP 403. No DB write.
- Non-mod with invalid/cross-session CSRF: HTTP 400 (CSRF check fires first).

---

## Step 4 — Statement submit + quota

### Route: `POST /c/<slug>/statements/new` (`v2/app.py:1177-1254`)

Decorated `@csrf.exempt`, validated via `_validate_same_origin()` (Sec-Fetch-Site /
Origin header check).

**Quota config:** `conv.argument_vote_data.get('new_stmt_max', 3)` — default 3. The test
conversation has `argument_vote_data={"K": 2}` (no `new_stmt_max` key), so quota is 3.

**Outbound calls per submission:**
1. `POST http://127.0.0.1:8002/api/session?create=true` — gets `csrf_token` from Particiapi.
2. `POST http://127.0.0.1:8002/api/conversations/rtyhvm0czb/statements/` with
   `{"text": "..."}` and the Particiapi session cookie.

Both calls made inside a single request handler; the Flask `with_for_update()` lock on the
`participations` row (`v2/app.py:1195-1197`) spans both outbound calls and the DB update.

**Response shape from Particiapi (passed through):**
```json
{"id": 34, "is_meta": false, "is_seed": false, "last_modified": "Sun, 31 May 2026 14:27:17 GMT"}
```
The `text` key is NOT returned in the passthrough response.

**DB writes per successful submission:**
`participations.new_stmt_ids` updated: `[] → [34] → [34,35] → [34,35,36]`.
Each successful submission appends the Particiapi statement ID. No other table written.

**Quota exceeded (4th submission):**
HTTP 403, `{"error": "quota_exceeded"}`. DB not written. The quota check fires BEFORE
the outbound Particiapi calls (`v2/app.py:1199-1201`).

**HTTP status codes:**
- Successful: 201 (Flask passes through Particiapi's 201).
- Quota exceeded: 403 (Flask, before hitting Particiapi).
- Particiapi unreachable: 502 (not exercised).

---

## Step 5 — Identity reveal

### Route: `POST /c/<slug>/reveal` (`v2/app.py:1293-1322`)

Requires: `conversation.closed_at` set, `age >= REVEAL_COOLDOWN_DAYS (30)`,
`age < REVEAL_COOLDOWN_DAYS + REVEAL_NULLIFY_DAYS (60)`, `participation.public_username` is
NULL, `confirm=1` in form.

**Setup:** `closed_at` set to 35 days ago via direct DB write (window: [30, 60] days).

**HTTP 302** on success → `/c/<slug>`.

**DB write — `participations`:**
```
public_username: NULL → "dev-user-1"   (mw_username of the participant)
revealed_at:     NULL → "2026-05-31 14:34:20.888256"  (naive UTC datetime)
```

`revealed_at` is written as a naive datetime via `datetime.now(timezone.utc)` but stored
without timezone metadata — consistent with the rest of the schema (`v2/db.py:7-9`).

**Edge cases verified:**

| Condition | HTTP |
|---|---|
| `public_username` already set (double reveal) | 400 |
| `age < REVEAL_COOLDOWN_DAYS` (1 day ago) | 400 |
| `age >= COOLDOWN + NULLIFY` (65 days ago) | 400 |
| `confirm` field absent | 302 → GET /c/<slug>/reveal (no reveal written) |

All 400s are `abort(400)` — no response body. No DB write on any failed path.

---

## Step 6 — Proxy cookie rename

### Route: `POST /proxy/particiapi/api/session` (`v2/app.py:1258-1263`, calls `_proxy_to_particiapi`)

**Request direction (browser → Flask → Particiapi):**
Code at `v2/app.py:303-305`:
```python
pa_cookie = request.cookies.get('pa_session')
if pa_cookie:
    forwarded_cookies['session'] = pa_cookie
```
Browser sends `pa_session=X`; Flask extracts the value and forwards as `session=X` to
Particiapi. Verified by code; not observable directly in curl response headers from Flask.

**Response direction (Particiapi → Flask → browser):**
Code at `v2/app.py:350-357`:
```python
if 'session' in upstream.cookies:
    flask_resp.set_cookie('pa_session', upstream.cookies['session'], ...)
```
Confirmed at runtime: response headers include:
```
Set-Cookie: pa_session=<value>; HttpOnly; Path=/; SameSite=Lax
```
No `Secure` flag — correct, since `secure=not current_app.debug` and debug=True.

Flask's own session cookie is also set in the same response:
```
Set-Cookie: session=<value>; Expires=…; HttpOnly; Path=/; SameSite=Lax
```

**Two `Set-Cookie` headers coexist** in the response: `pa_session` (Particiapi's renamed
session) and `session` (Flask's own session). These have different names and values and
serve distinct purposes.

**Response body shape** (from `POST /api/session`):
```json
{"authenticated": false, "csrf_token": "<token>"}
```
The csrf_token is Particiapi's token, used in `X-CSRF-Token` headers on subsequent
Particiapi API calls through the proxy.

---

## Admin routes — additional observations

### `POST /admin/conversations/<id>/strict-moderation` / `/moderate` / `/seed`

All three routes reach Polis server at `http://127.0.0.1:8003`. The dev Polis server
returned HTTP 403 for moderate and strict-moderation:
```
PolisServerError: Polis moderation failed (HTTP 403): polis_err_update_comment_auth
PolisServerError: Polis conversation settings update failed (HTTP 403): polis_err_update_conversation_permission
```
The Flask routes return **302** in all error cases (flash message + redirect). The 403
from Polis is **silently swallowed** from the user's perspective — the redirect goes to
the admin page which shows a flash error. HTTP 302 is returned to the browser regardless
of whether the Polis operation succeeded or failed.

### `POST /admin/conversations/new`

Created conversation `audit-test-conv` with polis_id `2fn6tfpfdy` (Polis server was
reachable and created the conversation). Response: 302.

Tables written: `conversations` (1 INSERT).

Outbound call: `POST http://127.0.0.1:8003/api/v3/auth/login` (login), then
`POST http://127.0.0.1:8003/api/v3/conversations` (create). Both logged in Flask error
output (exception trace visible for failed calls).

---

## POST-route reachability table

All 29 POST routes in `v2/app.py` at `eaa47a9`. Routes requiring Polis server are marked;
403s from Polis do not prevent the Flask route from being reached.

| Route | Exercised | HTTP returned | Notes |
|---|---|---|---|
| `POST /accept/<slug>` | ✓ | 302 | CSRF required |
| `POST /c/<slug>/arguments/<fs_id>/submit` | ✓ | 200 | JSON response with `X-Requested-With: fetch` |
| `POST /c/<slug>/arguments/<fs_id>/<side>/skip` | ✓ | 200 | Idempotent |
| `POST /c/<slug>/arguments/<arg_id>/vote` | ✓ | 200, 403, 409 | gate/own/cap reasons |
| `POST /c/<slug>/arguments/<arg_id>/unvote` | ✓ | 200 | No-op if not voted |
| `POST /c/<slug>/arguments/<arg_id>/hide` | ✓ | 302, 403 | Mod-only |
| `POST /c/<slug>/arguments/<arg_id>/unhide` | ✓ | 302 | Mod-only |
| `POST /c/<slug>/statements/new` | ✓ | 201, 403 | CSRF-exempt; Particiapi outbound |
| `POST /proxy/particiapi/<path>` | ✓ (POST) | 200 | PUT not exercised |
| `POST /c/<slug>/reveal` | ✓ | 302, 400 | Window + double-reveal checks |
| `POST /logout` | ✓ | 302 | Session cleared |
| `POST /admin/conversations/new` | ✓ | 302 | Polis server creates conv |
| `POST /admin/conversations/<id>/edit` | ✓ | 302 | |
| `POST /admin/conversations/<id>/pause` | ✓ | 302 | Toggles paused flag |
| `POST /admin/conversations/<id>/close` | ✓ | 302 | Sets active=0, closed_at |
| `POST /admin/conversations/<id>/phases` | ✓ | 302 | |
| `POST /admin/global-admins/add` | ✓ | 302 | |
| `POST /admin/global-admins/<id>/remove` | ✓ | 302 | |
| `POST /admin/roles/add` | ✓ | 302 | |
| `POST /admin/roles/<id>/remove` | ✓ | 302 | |
| `POST /admin/conversations/<id>/invites/add` | ✓ | 302 | Bulk (newline-separated) |
| `POST /admin/conversations/<id>/invites/<id>/remove` | ✓ | 302 | |
| `POST /admin/conversations/<id>/statements/<tid>/moderate` | ✓ | 302 | Polis 403 in test env |
| `POST /admin/conversations/<id>/statements/seed` | ✓ | 302 | Polis outbound |
| `POST /admin/conversations/<id>/strict-moderation` | ✓ | 302 | Polis 403 in test env |
| `POST /admin/conversations/<id>/featured/confirm` | ✓ | 302 | |
| `POST /admin/conversations/<id>/featured/add` | ✓ | 302 | |
| `POST /admin/conversations/<id>/featured/<fs_id>/remove` | ✓ | 302 | |
| `POST /admin/conversations/<id>/arguments/<arg_id>/delete` | ✓ | 302 | Admin-only |

**Not exercised:** `PUT /proxy/particiapi/<path>` — this is the same `proxy_particiapi`
route handler but via PUT method. No app UI element was observed to trigger a PUT; the
`_proxy_to_particiapi` handler is generic and would pass it through if called.

---

## DB tables written during audit

| Table | Operations | Notes |
|---|---|---|
| `participations` | INSERT (1), UPDATE (new_stmt_ids 3x, reveal 1x) | |
| `argument_side_states` | INSERT (20, on page load), UPDATE (skipped flag) | Side effect of GET /c/<slug> |
| `arguments` | INSERT (3 submitted, 3 seed inserted directly) | |
| `argument_votes` | INSERT (9), DELETE (2) | value=NULL for all inserts |
| `conversations` | INSERT (1 audit-test), UPDATE (phases, pause, close, closed_at manipulation) | |
| `conversation_invites` | INSERT (2), DELETE (1) | 1 remaining after audit |
| `admin_roles` | INSERT (1), DELETE (1) | |
| `participants` | UPDATE (is_global_admin 1x) | |

---

## Verified gate state machine (plain language)

The argument gate is per-participant per-featured-statement. For each featured statement:

1. **On first `GET /c/<slug>`:** `ArgumentSideState` rows are created for both `pro` and
   `con` sides, with `skipped=False` and `argument_order` populated from current visible
   arguments.

2. **Gate locked** (neither side done): voting on any argument for this FS returns
   403 `reason="gate"`.

3. **One side unlocked:** Either (a) participant submits an argument on a side, or (b)
   calls `POST .../skip` for that side. The other side remains locked.

4. **Both sides unlocked** (gate open): participant may vote on arguments. Gate state is
   checked on every vote request; it does not require a page reload.

5. **Voting rules once gate is open:**
   - Cannot vote on own argument → 403 `reason="own"`.
   - Cannot vote on hidden argument → 403 `reason="hidden"`.
   - Cannot exceed K votes per side (K from `conv.argument_vote_data["K"]`, default 2)
     → 409 `reason="cap"`.
   - All votes are binary row-presence (kApproval); `ArgumentVote.value` is always NULL.

6. **Gate persists:** After closing and re-opening a conversation page, gate state is read
   from DB — it does not reset on navigation.

The gate does NOT interact with Polis voting (votes through the web component proxy go to
Particiapi independently; those votes have no effect on `ArgumentSideState` or the gate).
