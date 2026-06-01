# wiki-polis — Codebase Audit (read-only, external)

Audit date: 2026-05-31. Scope: entire `wiki-polis/` tree including gitignored
folders and `.claude/`. Method: direct reading + `ruff` + `vulture` + `pytest`
+ `git`. Facts and evidence only; no recommendations.

## Tooling detected

- **Stack:** Python 3 / Flask. Two parallel Flask apps (root + `v2/`), SQLAlchemy
  + Flask-SQLAlchemy, Flask-Migrate/Alembic, Flask-Session, Flask-WTF (v2 only),
  Flask-Limiter (v2 only). Dependency manager: `uv` (`uv.lock` present in root and `v2/`).
- **DB drivers:** `pymysql` (MariaDB/ToolsDB), `psycopg2-binary` (Polis Postgres, v2 only).
- **Front end:** server-rendered Jinja2 + a vendored web-component bundle
  (`v2/static/particiapp-web-components.js`, `particiapp-web-client.js`).
- **Tests:** `pytest`, with `playwright` listed as a v2 dev dep.
- **Audit tools available locally:** `ruff` (installed), `vulture` (run via `uvx`).
  `knip`, `ts-prune`, `depcheck`, `madge`, `jscpd`, `pydeps` are **not installed**
  (no JS/TS build graph to analyze anyway — the JS is a single vendored bundle).
- **Vendored / non-source trees present in the working dir:** `.venv/`,
  `v2/.venv/` (Python 3.14 site-packages), `tmp/node_modules/` (puppeteer +
  deps), `__pycache__/`. These dominate the raw file counts
  (2435 `.py`, 1507 `.js`, 1456 `.ts`) but are dependencies, not project code.
  Non-vendored project Python totals ~6,167 lines.

---

## 1. What it actually does

There are **two complete, independent Flask applications** in this repo.

### Root app (`app.py` 618 lines, `db.py` 99 lines, `templates/`, `static/`)
`app.py:1-6` describes itself as "Flask application for wiki-polis." It is a thin
wrapper around a **hosted pol.is** conversation behind Wikimedia OAuth:
- OAuth2 PKCE login against `meta.wikimedia.org` (`app.py:347-434`).
- Conversation/Participation/Invite management; admin UI with participant search
  + pagination (`app.py:444-464`), role grants (`admin`/`moderator`/`curator`,
  `app.py:521`), per-conversation invite lists.
- The conversation page (`app.py:289-306`) renders `index.html` and passes a raw
  `xid` to the template — voting happens in an embedded hosted pol.is widget.
- DB models: `Participant`, `Conversation`, `Participation`, `AdminRole`,
  `ModAction`, `ConversationInvite` (`db.py`). `ModAction` is defined but never
  used in `app.py` (imported, then unused — see §3).

### v2 app (`v2/app.py` 1,897 lines, `v2/db.py` 226, `v2/polis_admin.py` 434)
`v2/app.py:1-3` "Flask application for wiki-polis v2." A much larger system that
**self-hosts** Polis via Particiapi and proxies voting through Flask:
- Same OAuth2 PKCE login (`v2/app.py:1326-1417`).
- A **statement-voting + argument-mapping** workflow: participants accept a
  conversation under a generated pseudonym (`coolname`), vote via a proxied
  Particiapi web component, optionally submit new statements under a quota, and
  on "featured" statements propose/skip/vote pro-and-con arguments behind a gate
  (`_build_featured_data` `v2/app.py:811-898`; argument routes `982-1173`).
- A **browser↔Flask↔Particiapi reverse proxy** (`_proxy_to_particiapi`
  `v2/app.py:278-359`) that renames the session cookie to `pa_session`, filters
  query params, and rewrites a 403-on-`/results/` into an empty 200.
- **Server-side Polis admin** (`v2/polis_admin.py`): conversation creation,
  statement moderation, strict-moderation toggle, seed statements via Polis
  `/api/v3` (`PolisServerClient`), plus **direct Postgres reads** for stats and
  featured-statement candidates (raw SQL, `_STATEMENTS_SQL` etc.).
- An **opt-in identity reveal** mechanism with a cooldown/nullify timeline
  (`_REVEAL_COOLDOWN_DAYS=30`, `_REVEAL_NULLIFY_DAYS=30`, `v2/app.py:58-78`,
  `919-964`, `1267-1322`).
- Phase toggles per conversation (`phase_submission`, `phase_personal_results`,
  `phase_argument_mapping`, `phase_public_results`, `v2/db.py:59-62`).
- `/health` endpoint (`v2/app.py:1872-1891`).

### Which app actually runs in production
Despite `README.md:40` labelling root `app.py` as "Flask app (v1, live)" and
`README.md:30`/`v1/README.md:3` calling v1 "the current live deployment," the
**deploy path runs v2**:
- `wsgi.py:5-7` inserts `v2/` onto `sys.path` and does `from app import app` —
  i.e. it loads `v2/app.py`, not root `app.py`.
- `deploy.sh:2` "Deploy wiki-polis v2"; `deploy.sh:36` `pip install -e ~/wiki-polis/v2`;
  `deploy.sh:59-60` runs migrations from `~/wiki-polis/v2`.
- `v2/deployment.md:270` `ln -s ~/wiki-polis/v2 ~/www/python/src`.

No deploy artifact references root `app.py`. (See §6 for the README/reality drift.)

---

## 2. Competing implementations

### 2a. Two whole apps implementing the same concerns
Root and `v2/` define **28 identically-named functions** (`comm` on the two files):
`_read_secret`, `_sanitise_text`, `_valid_polis_id`, `_valid_slug`,
`_parse_conversation_form`, `_current_participant`, `_is_emailable`,
`login_required`, `admin_required`, `_check_conversation_access`,
`create_app`, `_register_routes`, `_inject_globals`, `index`, `login`, `logout`,
`oauth_callback`, `accept`, `accept_post`, `admin`, `admin_conversation_new`,
`admin_conversation_edit`, `admin_conversation_invites`, `admin_invite_add`,
`admin_invite_remove`, `dev_login`, `conversation`, `wrapper`.
The two implementations differ (e.g. `_read_secret` path is
`/run/secrets/{TOOL_NAME}/` in root `app.py:59` vs hard-coded
`/run/secrets/wiki-polis/` in `v2/app.py:49`; `_current_participant` caches on `g`
in v2 `v2/app.py:129-137` but not in root `app.py:95-100`).

### 2b. Authorization: global decorator vs per-conversation check
- `@admin_required` (global admin only) — 10 occurrences in `v2/app.py`
  (e.g. `1429`, `1468`, `1500`, `1517`, `1528`, `1541`, `1553`, `1569`, `1578`, `1607`).
- `_require_mod_for_conv(conv_id)` (per-conversation moderator-or-global) — 14
  occurrences (e.g. `1447`, `1617`, `1628`, `1649`, `1661`, `1699`, `1726`, `1742`,
  `1777`, `1809`, `1828`, `1847`, `1862`).
  Several admin POST routes (invites add/remove `1625/1646`, statement moderate
  `1696`, featured add/remove `1825/1844`) use **only** `@login_required` +
  `_require_mod_for_conv`, while conversation new/edit/pause/close/phases use
  `@admin_required`.
- A third variant is the inline `_can_moderate(conv)` check inside
  `argument_hide`/`argument_unhide` (`v2/app.py:1153`, `1166`).
- Root `app.py` uses a different role model again: `_is_admin()`
  (`app.py:183-188`) reads `participant.is_admin`; v2 uses `is_global_admin`.

### 2c. CSRF protection: global token vs origin check
- Most v2 POST routes rely on Flask-WTF global CSRF (`csrf.init_app`, `v2/app.py:463`).
- Two endpoints are `@csrf.exempt` and instead call `_validate_same_origin()`
  (Sec-Fetch-Site / Origin check): `conversation_statement_new` (`1179-1184`)
  and `proxy_particiapi` (`1261`). `_proxy_to_particiapi` also calls it inline
  (`294`).

### 2d. Data access to Polis statements — two clients, two shapes
The same "get statements" concern has two implementations returning the same
`(pending, approved, hidden)` tuple shape but different dict keys:
- `PolisParticipantClient.get_statements` (HTTP, `v2/polis_admin.py:128-141`):
  all statements forced into `approved`; dict key `txt`; pending/hidden always `[]`.
- `PolisServerClient.get_statements` (raw Postgres, `v2/polis_admin.py:327-368`):
  real `mod` state into pending/approved/hidden; dict has `txt`, `mod`,
  `agree_count`, etc.
`admin_conversation_statements` (`v2/app.py:1665-1672`) tries the Postgres one,
then falls back to the HTTP one. Statement text is read with **two different key
conventions** across call sites: `s.get('txt','')` (`v2/app.py:833`) vs
`s.get('text') or s.get('txt','')` (`v2/app.py:1761`, `1801`).

### 2e. Statement-text retrieval, three call sites
`_build_featured_data` (`v2/app.py:829-833`), `_backfill_statement_texts`
(`v2/app.py:1753-1772`), and `_fetch_statement_text` (`v2/app.py:1795-1804`) each
independently instantiate `PolisParticipantClient`, call `get_statements`, and
build a tid→text map — three near-duplicate blocks.

### 2f. AJAX vs form response handling
Argument routes branch on `request.headers.get('X-Requested-With') == 'fetch'`
to return JSON vs redirect, repeated in `argument_submit`, `argument_skip`,
`argument_vote`, `argument_unvote` (`v2/app.py:999-1001`, `1064-1066`,
`1091-1131`, `1145-1147`). `conversation_statement_new` uses a different
convention (always JSON, `1201`, `1245-1249`).

### 2g. Postgres connection boilerplate, three copies
`get_statements`, `get_featured_candidates`, `get_polis_stats`
(`v2/polis_admin.py:340-350`, `385-395`, `406-421`) each repeat the same
`import psycopg2 / connect / cursor / finally: close / except: log+return None`
block verbatim.

### 2h. `import` style: top-level vs in-function re-import
`import random` at `v2/app.py:10` is **re-imported inside functions** at
`v2/app.py:779` and `1014`; `from sqlalchemy.orm import joinedload` at top
(`:29`) is re-imported at `:820`. (`subprocess` `:366` and `pathlib` `:552` are
function-local imports with no top-level counterpart.)

### 2i. DB-write idempotency / commit-error handling
Variants coexist: bare `db.session.commit()` (most routes);
`try/except IntegrityError → rollback + re-render` (`accept_post`
`v2/app.py:753-760`); `try/except Exception → rollback` silently
(`admin_invite_add` `v2/app.py:1640-1644`); `with_for_update()` row lock
(`conversation_statement_new` `v2/app.py:1195-1197`).

### 2j. Datetime handling
`v2/db.py:7-9` documents storing **naive UTC**; code mixes
`datetime.now(timezone.utc)` (aware) for writes and re-attaches tzinfo on read
via `conv.closed_at.replace(tzinfo=timezone.utc)` (`v2/app.py:67`, `937`, `1284`,
`1309`). `revealed_at` is written aware (`v2/app.py:1320`).

---

## 3. Dead / abandoned code

### 3a. Broken/stale test module (uncollectable)
`v2/tests/test_polis_admin.py:6` imports `PolisAdminClient, PolisAdminError,
get_polis_stats` from `polis_admin` — **none of these names exist** (the module
defines `PolisServerClient`, `PolisServerError`, `PolisParticipantClient`, and
`get_polis_stats` is a *method*, not a module function). Pytest aborts collection:
`ImportError: cannot import name 'PolisAdminClient'`. All 14 tests in this file
are dead.

### 3b. Six failing tests on current HEAD (test⇄code drift)
Running `pytest --ignore=tests/test_polis_admin.py` from `v2/`:
`6 failed, 87 passed, 24 warnings`.
- `test_auth.py::test_oauth_callback_state_mismatch_returns_400` — asserts 400,
  code now returns 302 (changed by commit `a46905f` "redirect to login instead
  of 400"). `assert 302 == 400`.
- `test_admin.py::test_create_conversation` and
  `::test_create_conversation_invalid_polis_id_rejected` — fail because the test
  config has Polis server vars set, so creation now attempts a live login to
  `127.0.0.1:8001` and raises `PolisServerError` (Connection refused);
  `assert None is not None`.
- `test_arguments.py::test_moderator_can_delete_argument`,
  `::test_participant_cannot_delete_argument`, `::test_admin_featured_remove` —
  argument delete moved to admin panel (commit `64df218`); old routes/expectations
  no longer hold.

### 3c. Root app (`app.py`, `db.py`, `templates/`, `static/`)
Not loaded by any deploy artifact (§1). `db.py:75` `ModAction` is **imported but
unused** in `app.py:39` (ruff `F401`: "unused import 'ModAction'"; vulture 90%).
Root templates `welcome.html`, `landing.html`, `index.html` are referenced only
by root `app.py` (no references in `v2/`).

### 3d. Unused locals (ruff `F841`, real positives in v2/app.py)
`exc` assigned-but-unused in 6 `except ... as exc:` blocks that only call
`logger.exception()`: lines `334`, `1481`, `1673`, `1717`, `1734`, `1746`.
`fs` assigned-but-unused at `986`. `participant` assigned-but-unused at `1448`.
(Plus 5 in `simulate_cats_vs_dogs.py`: `249-251`, `433`, `436`.)

### 3e. Unimplemented vote method ("ranking") — schema present, code absent
`v2/db.py:64-67` documents `argument_vote_method='kApproval'|'ranking'` and
`ArgumentVote.value` (`v2/db.py:179-182`) is documented for ranking (rank
position). No code ever sets `value` or branches on `'ranking'`; only `kApproval`
(row-presence) is implemented. `value` is dead today.

### 3f. Comment/default mismatch
`v2/db.py:65` comment shows `vote_data={'k': 2}` (lowercase `k`), but the column
default and all readers use uppercase `'K'` (`v2/db.py:67`,
`v2/app.py:891`, `1098`, `1199`). The lowercase-`k` path is never read.

### 3g. Vulture false positives (recorded for completeness)
Vulture flags ~40 "unused function" in `v2/app.py` (all Flask route handlers
registered by decorator) and ~25 "unused variable" in `v2/db.py` (SQLAlchemy
columns/relationships). These are **not** dead — they are accessed via
framework machinery, not direct references.

### 3h. Working DB files committed-ignored but present on disk
`v2/dev.db`, `v2/instance/dev.db`, `instance/dev.db`, `v2/screenshot.db` exist in
the tree (gitignored via `*.db`). `instance/` is the root app's; `v2/instance/`
is v2's.

---

## 4. Premature abstraction

- **`update_conversation_settings(**kwargs)`** (`v2/polis_admin.py:247-269`) is a
  generic Polis settings updater documenting many accepted fields, but its only
  caller is `set_strict_moderation` (`v2/polis_admin.py:271-272`), which passes a
  single field. `set_strict_moderation` in turn has one caller
  (`v2/app.py:1745`). Two indirection layers for one concrete operation.
- **`_proxy_to_particiapi`** (`v2/app.py:278-359`) is a module-level function with
  a single caller, the one-line route `proxy_particiapi` (`v2/app.py:1262-1263`).
- **`_backfill_statement_texts`** (`v2/app.py:1753-1772`): single caller
  (`admin_conversation_featured` `1784`).
- **`_git_version`** (`v2/app.py:364-373`): called once at import
  (`_GIT_VERSION = _git_version()` `:375`).
- **`_short_title`** (`v2/app.py:87-92`): single caller (`:881`).
- `ADMIN_ROLES` is a one-element tuple `('moderator',)` (`v2/db.py:12`) used as if
  extensible (Enum, membership checks `v2/app.py:1584`) but has exactly one value.

---

## 5. Test reality

- **Suite:** `v2/tests/` — 9 files, 107 `def test_` functions total
  (admin 18, arguments 32, polis_admin 14, conversations 15, reveal 13, auth 7,
  security 8). Tests import `from app import create_app` / `from db import ...`,
  i.e. they exercise **v2 only**. **The root app has no tests at all.**
- **Current result:** `test_polis_admin.py` (14) is uncollectable (§3a); of the
  rest, **87 pass, 6 fail** (§3b).
- **Covered:** auth/session helpers, OAuth happy + several failure paths, access
  policy (public/invite_only), pseudonym validation, argument gate/cap/hidden/own
  rules (`test_arguments.py` is the largest, 32 tests), reveal-window state
  transitions, several security checks (`test_security.py`: dev-DB isolation,
  CSRF-exempt origin checks, path-traversal in proxy).
- **Riskiest behavior with no/!broken coverage:**
  - `polis_admin.py` Postgres reads and the raw SQL (`_STATEMENTS_SQL`,
    `_FEATURED_CANDIDATES_SQL`, `_POLIS_STATS_SQL`) — the only test file targeting
    this module (`test_polis_admin.py`) cannot import and references a removed API,
    so the SQL/parse paths are effectively untested.
  - `_proxy_to_particiapi` cookie-rename / 403→200 rewrite / param-filter logic
    is exercised only indirectly (origin/traversal asserts in `test_security.py`);
    the cookie mapping and upstream-error branches are not directly asserted.
  - `conversation_statement_new` quota + `with_for_update` race path (`v2/app.py:
    1177-1254`) — no concurrency test.
  - `_nullify_expired_reveals` time-based nullification (`v2/app.py:62-78`) beyond
    state labels.
  - The `create_conversation`/moderation HTTP paths against the real Polis server
    are unmocked in the failing admin tests (they hit `127.0.0.1:8001`).
- **Deprecation noise:** tests emit `LegacyAPIWarning` for `Query.get()`
  (SQLAlchemy 2.0) and `SESSION_FILE_DIR`/`FileSystemSessionInterface`
  deprecations from Flask-Session.

---

## 6. Drift signal (git history)

History: 141 commits total. Churn on core files:
`v2/app.py` 42 commits, `v2/polis_admin.py` 16, `v2/db.py` 6;
root `app.py` 6, root `db.py` 3 (root last touched 2026-05-10; v2 `app.py`
2026-05-29).

- **Argument/voting subsystem rewritten repeatedly.** 16 of the 42 `v2/app.py`
  commits touch triad/vote/argument/statement/quota/phase/reveal, including a
  visible back-and-forth: `7632efc` "Replace propose affordance with V2
  three-option triad," `48b9a77` "Fix V2 triad regressions," `82eb9ec`/`a0dfe2a`
  "Refine voting state machine," `f3dc972`/`d1d0851` quota/unlock formula,
  `90b4f46` "Fix own-statement appearing in vote queue." The state machine and
  gate logic (`v2/app.py:811-1254`) are the most-rewritten region.
- **OAuth callback behavior flipped recently.** `a46905f` (HEAD) changed the
  state-mismatch response from 400 to a 302 redirect; the test was not updated
  (§3b) — a fresh drift between code and its test.
- **API rename left a stale test.** `polis_admin.py` was reorganized into
  `PolisParticipantClient` / `PolisServerClient`; `test_polis_admin.py` still
  targets the pre-rename `PolisAdminClient` / `get_polis_stats` function (§3a).
- **README vs reality (largest doc drift).** `README.md:9` "Architecture (v2, in
  development)", `README.md:30` "`v1/` | Current live deployment",
  `README.md:40` "app.py — Flask app (v1, live)", and `v1/README.md:3` "The
  current live deployment" all assert root/v1 is live and v2 is unreleased —
  while `wsgi.py`, `deploy.sh`, and `v2/deployment.md` all deploy **v2** (§1).
  `v2/architecture.md:136` ("...working in v1") similarly frames v1 as the
  shipped baseline.
- **Access-policy model diverged between the two apps.** Root `db.py:11`
  `ACCESS_POLICIES = ('public','link_based','invite_only')`; v2 `db.py:11`
  `('public','invite_only')` — `link_based` was dropped in v2. Role sets also
  diverged: root `('admin','moderator','curator')` (`app.py:521`) vs v2
  `('moderator',)` (`v2/db.py:12`).
- **Uncommitted working changes at audit time** (git status): modified
  `v2/app.py`, `v2/templates/admin_featured.html`, `v2/templates/admin_statements.html`;
  untracked `v2/phase_model_extension.md`.
- **Structural growth without decomposition.** `_register_routes` in `v2/app.py`
  is a single ~1,300-line nested function; ruff `C901` reports its cyclomatic
  complexity at **182** (root `app.py`'s `_register_routes` is 46). `create_app`
  (16), `_proxy_to_particiapi` (11), and `argument_vote` (11) also exceed the
  threshold.

---

### Raw tool output references
- `ruff check ... --select F401,F811,F841,F541` → unused `exc`/`fs`/`participant`
  locals + unused `ModAction` import (details in §3c–3d).
- `ruff check ... --select C901` → complexity figures in §6.
- `uvx vulture --min-confidence 60` → route-handler/column false positives (§3g)
  + the genuine `ArgumentVote.value`/`ranking` dead path corroborated by reading.
- `pytest` (v2) → `1 error in collection` (test_polis_admin) + `6 failed, 87 passed`.
