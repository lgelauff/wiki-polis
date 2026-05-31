# wiki-polis v2 — Refactor Plan

Generated 2026-05-31 from `codebase-audit.md` and `runtime-writes-audit.md`.
Decision: **refactor, not rewrite** — the hard problems (OAuth PKCE, proxy cookie
rename, argument gate, quota row-lock, reveal timeline) are solved and tested.

Steps 1–4 landed in PR #88. Steps 5–9 are the structural blueprint decomposition.

---

## Steps 1–4 — Complete (PR #88)

### Step 1 — Green test suite ✓

Fixed 5 drifted tests, no production code changes.

- `test_auth`: state-mismatch now asserts 302 → `/login` (code changed in `a46905f`)
- `test_arguments`: delete route moved to `/admin/conversations/<id>/arguments/<id>/delete`
- `test_admin`: mock `PolisServerClient.create_conversation`; replace stale
  `invalid_polis_id_rejected` test with `polis_failure_redirects`

**Result:** 108 passed, 0 failed (was 5 failed).

### Step 2 — Dead locals and redundant imports ✓

In `v2/app.py`:
- 6 `except ... as exc:` bindings where `exc` was never read (lines 334, 1481, 1673,
  1699, 1716, 1728 in baseline)
- `fs =` in `argument_submit` — `first_or_404()` side effect is the point
- `participant =` in `admin_conversation_detail` — never read
- `import random` inside two functions + `from sqlalchemy.orm import joinedload` inside
  one function — all already imported at module top

### Step 3 — Collapse single-caller indirection ✓

`update_conversation_settings(**kwargs)` in `polis_admin.py` had exactly one caller:
`set_strict_moderation`. Inlined and deleted the generic wrapper.

### Step 4 — Deduplicate psycopg2 boilerplate ✓

`get_statements`, `get_featured_candidates`, `get_polis_stats` each duplicated the
same `import psycopg2 / connect / cursor / fetchall / finally-close / except-log-return-None`
block. Extracted to `_pg_query(sql, params, label)` on `PolisServerClient`.

---

## Step 5 — Lift non-route helpers to module level

**GitHub issue:** #89  
**Risk:** Medium | **Size:** M (~200 lines relocated, no logic change)

`_register_routes` (`app.py:546`) is a 1,300-line closure with C901 = 177. It contains
five functions that are not Flask route handlers and do not close over any local
variable of `_register_routes`:

| Function | Line (baseline) | Used by |
|---|---|---|
| `_get_or_create_side_state` | 772 | `_build_featured_data`, `argument_submit` |
| `_build_featured_data` | 811 | `conversation` |
| `_require_arg_participation` | 968 | all `argument_*` routes |
| `_backfill_statement_texts` | 1735 | `admin_conversation_featured` |
| `_fetch_statement_text` | 1776 | `admin_featured_confirm`, `admin_featured_add` |

**Action:** Move all five to module level above `create_app`. No call-site edits
needed — module-level names are in scope inside the closure.

**Acceptance:** `ruff check app.py --select C901` shows complexity of `_register_routes`
drops materially; full test suite stays green.

---

## Step 6 — Consolidate statement-text fetch blocks

**GitHub issue:** #90  
**Risk:** Medium | **Size:** S-M (~40 lines)

Three near-duplicate blocks each instantiate `PolisParticipantClient`, call
`get_statements`, and build a `tid → text` map:

- `_build_featured_data` (`app.py:829-833`): uses `s.get('txt', '')`
- `_backfill_statement_texts` (`app.py:~1742`): uses `s.get('text') or s.get('txt', '')`
- `_fetch_statement_text` (`app.py:~1779`): uses `s.get('text') or s.get('txt', '')`

The key convention is inconsistent between them. After Step 5 all three are at module
level and can share one helper.

**Action:** Add `_statement_text_map(conv_polis_id) -> dict[int, str]` at module level,
using `s.get('text') or s.get('txt', '')` as the unified key rule. Rewrite the three
callers to use it. Add a unit test asserting both `txt`-only and `text`-only payloads
resolve correctly.

**Acceptance:** New test passes; featured-data and backfill tests stay green.

---

## Step 7 — Extract proxy + statement-submit into a blueprint

**GitHub issue:** #91  
**Risk:** High | **Size:** M (~120 lines relocated + new tests)

`_proxy_to_particiapi` is a module-level function with a single thin route caller
(`proxy_particiapi`). The CSRF-exempt `conversation_statement_new` shares the same
same-origin-check and `pa_session` cookie machinery. This is the highest-security
cluster and benefits from being reviewed in isolation.

**Affected routes:**
- `POST/GET/PUT /proxy/particiapi/<path>`
- `POST /c/<slug>/statements/new`

**Key constraints:**
- Both routes are `@csrf.exempt` with `_validate_same_origin()` as the compensating
  control. Must be explicitly exempted on the blueprint.
- The `pa_session` ↔ `session` rename is documented in `runtime-writes-audit.md` Step 6.
  Behaviour must be byte-identical after extraction.
- `SET-Cookie: pa_session=…` (Particiapi rename) and `session=…` (Flask session) must
  both appear in the response.

**Acceptance:** `test_security.py` green with no assertion changes; new direct tests
for the 403→200 `/results/` rewrite and cookie rename pass.

---

## Step 8 — Extract admin routes into a blueprint

**GitHub issue:** #92  
**Risk:** High | **Size:** L (~400 lines relocated)

All `/admin/…` routes (`app.py:1427-1844`, ~17 route handlers) into `Blueprint('admin')`.

**Key constraints:**
- Two auth conventions coexist and must not be merged in this step:
  - `@admin_required` (global admin only): conversation new/edit/pause/close/phases,
    global-admin add/remove, role add/remove
  - `_require_mod_for_conv` (per-conversation moderator or global): invites, statements,
    featured, argument-delete
- `url_for` targets must not change. Use explicit `endpoint=` on each route or name the
  blueprint to preserve the existing endpoint namespace.

**Acceptance:** `test_admin.py` (18 tests) green with zero assertion changes.

---

## Step 9 — Extract participant-facing routes into a blueprint

**GitHub issue:** #93  
**Risk:** High | **Size:** L (~450 lines relocated)

Routes: `accept`/`accept_post`/`accept_pseudonyms`, `conversation`, the full
`argument_*` cluster, `reveal_identity`/`reveal_identity_post`.

Auth/OAuth/`index`/`logout`/`health`/dev-login routes stay in `app.py` — they are
tied to `_dev_login_user`/`_on_toolforge` closure variables in `_register_routes` and
cannot be moved without a larger refactor.

**Key constraints:**
- The argument routes redirect with `url_for('conversation', slug=...) + '#tab-arguments'`
  — preserve the `conversation` endpoint name.
- The gate state machine (pro_gate/con_gate), K-cap (409), own/hidden (403) logic in
  `argument_vote` must move verbatim. Covered by `test_arguments.py` (32 tests).
- The `with_for_update()` row-lock in `conversation_statement_new` must be preserved.

**Acceptance:** `test_arguments.py` (32), `test_conversations.py` (15), `test_reveal.py`
(13) all green with zero assertion changes.

---

## Step 10 — Fix k/K comment in db.py

**GitHub issue:** N/A — fold into any nearby PR  
**Risk:** Low | **Size:** S (1 line)

`v2/db.py:65` comment shows `vote_data={'k': 2}` (lowercase) but the column default
and every reader use `'K'` (uppercase). The lowercase path is never read.

**Action:** Correct the comment to `{'K': 2}`.

---

## Scope guard

This plan does **not**:
- Touch the data model (`db.py` models), migrations, or the `ArgumentVote.value` /
  `ranking` dead path
- Unify the two authorization conventions (`@admin_required` vs `_require_mod_for_conv`)
- Unify the two CSRF conventions (the proxy's origin-check exemption is intentional)
- Touch the retired root `app.py` / `db.py` / `templates/`
- Reconcile naive vs aware datetime storage

Each of those is a behaviour or product question, not a structure question.
