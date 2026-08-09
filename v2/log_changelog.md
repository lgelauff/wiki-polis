# Build log

> **Append-only history** of what has been built, in roughly the order it happened.
> Entries are a record — not edited retroactively. For what's *next*, see
> [`plan_roadmap.md`](plan_roadmap.md); for how the app is *meant to work*, see
> [`spec_functional-design.md`](spec_functional-design.md).

---

## Step 1 — Run Polis + Particiapi locally ✓ (in progress)

**Goal:** Validate the approach before touching any infrastructure.

- [x] Clone with `--recurse-submodules`; fix PostgreSQL 18 volume path; set auth disabled + dev mode
- [x] Base stack running: Polis + Particiapi + PostgreSQL
- [x] Particiapi API responding; conversation creation and retrieval confirmed
- [x] Statement submission and voting confirmed end-to-end via API
- [x] Web components evaluated from source — events, CSS parts, integration pattern documented

**Setup notes:** `v2/cache/local-setup.md`, `v2/reference/particiapi-api.md`, `v2/reference/web-components.md`

**Deliverable:** ✓ Approach confirmed. Particiapi API works, voting loop works, web components provide sufficient styling and event hooks for our integration.

---

## Step 4 — Build Flask app v2 ✓

- [x] Start fresh Flask app (builds on v1 structure)
- [x] Clean data model: Conversation (with 4 phase toggle fields), Participant, Participation, ConversationInvite, AdminRole, FeaturedStatement, Argument, ArgumentVote
- [x] Replace PolisClient with session-cookie proxy (browser ↔ Flask ↔ Particiapi; `pa_session` cookie rename pattern)
- [x] Wikimedia OAuth flow (port from v1); dev-login bypass when OAuth not configured
- [x] Conversation listing: active / archived / available / moderating sections
- [x] Accept flow with coolname pseudonym selection (5 options + re-roll)
- [x] Conversation page: `<pa-conversation>` + `<pa-statement>` + `<pa-vote-button>`; "propose alternative" prompt after each vote
- [x] Admin panel: conversations, phase toggles (S/P/A/R), roles, invites
- [x] Confirmed end-to-end locally: dev-login → accept → statement submission → vote → Polis recorded `{"value": -1}`
- [x] `polis_admin.py` split into `PolisParticipantClient` (Particiapi HTTP reads) and `PolisServerClient` (Polis admin API + direct Postgres); raises `PolisParticipantError` / `PolisServerError`
- [x] Test suite (74 tests) green: unit, integration, security, reveal, polis_admin

**Particiapi vote API:** `PUT /api/conversations/<id>/votes/<tid>` with `{"value": <int>}` (AGREE=-1, NEUTRAL=0, DISAGREE=1). Requires `@session_required` (web component handles session creation via `POST /api/session?create=true`).

**Deliverable:** ✓ End-to-end confirmed locally against particiapp-docker stack.

**Next:** Deploy to VPS (Step 2) then wire Flask to it (Step 4 → prod).

---

## Step 4b — Security & privacy hardening ✓

Security, code quality, and computational social science reviews conducted (2026-05-12); all approved items implemented.

**Security**
- [x] CSRF protection (Flask-WTF) on all HTML forms; proxy route exempt with Sec-Fetch-Site / Origin validation as compensating control
- [x] Rate limiting (Flask-Limiter) on login, accept, and pseudonym endpoints; mid-flow requests never interrupted
- [x] Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) via `after_request`
- [x] Open redirect fixed in `redirect_to` form fields (`urllib.parse` host comparison)
- [x] Dev login triple-guarded: `app.debug` AND `DEV_LOGIN_USER` env var AND not on Toolforge

**Code quality**
- [x] `get_polis_stats` rewritten with direct psycopg2 connection (replaces `docker exec`; no string-interpolated SQL)
- [x] `_current_participant()` cached on Flask `g` (one DB hit per request)
- [x] `_is_emailable()` cached in session at OAuth callback time (not on every accept page load)
- [x] N+1 query in index view eliminated with `joinedload`
- [x] Pseudonym race condition handled with `IntegrityError` catch instead of pre-check

**Conversation lifecycle**
- [x] `active` toggle split into **Pause** (reversible, no reveal clock) and **Close permanently** (irreversible, starts clock) with confirmation dialog and prominent warning
- [x] `Conversation.paused` column added (migration applied)
- [x] Paused conversations hidden from available / public listings; conversation page shows "temporarily paused"

**Privacy & pseudonymity**
- [x] `link_based` access policy removed from code and UI
- [x] Opt-in identity reveal: `Participation.public_username` + `revealed_at` columns (migration applied)
- [x] `Conversation.closed_at` set on permanent close; drives reveal timeline
- [x] Reveal routes (`GET/POST /c/<slug>/reveal`) with cooldown gate, opt-in window gate, irreversible-warning form
- [x] Voluntary public reveals are permanent; app no longer nullifies `public_username` / `revealed_at` after the opt-in window
- [x] Minimum-N warning on results (< 25 participants): shown above public results, does not hide results
- [x] Consent copy on accept page updated to reflect platform-wide pseudonym uniqueness and operator data retention
- [ ] **TODO: open GitHub issue** — audit consistency of pseudonymity / vote privacy messaging across all user-facing surfaces (accept page, conversation view, results page, reveal flow). Ensure the platform's promises (votes are private, pseudonym is per-platform, identity reveal is opt-in post-close) are communicated clearly and consistently everywhere a participant might wonder.

---

## Step 4c — Frontend fixes (2026-05-13)

Web component integration bugs found and fixed during browser testing:

**Fixed**
- [x] `base="/proxy/particiapi"` relative URL crashed `new URL()` in `ConversationClient` — changed to `{{ request.url_root }}proxy/particiapi`
- [x] `#fetchConversation` missing `credentials: "include"` — session cookie not sent, proxy returned login redirect, JSON parse crashed
- [x] `urlWithPath()` replaced entire pathname, discarding the `/proxy/particiapi` prefix from all API URLs
- [x] Importmap placed in `<body>` inside conditional block — moved to `<head>` via `{% block head %}`, spec-compliant
- [x] CSS selector typo `pa-statement:state(no-statements)` → `no-statement` (singular)
- [x] `<pa-vote-button type="pass">` is not a valid type (silently fell back to neutral) — changed to `type="neutral"`
- [x] Vote buttons stayed visible while propose-prompt was active — user could accidentally vote on next statement; now hidden during propose step
- [x] "Skip" button relabelled "Next →"; submit button relabelled "Submit & next"

**Open**
- [x] **Bug 4 (high):** `particiappstatechange` listener added to conversation.html — shows a visible error message when state is `error`, hides vote UI. `unauthenticated` state handled implicitly (proxy prevents it in normal flow).
- [ ] **Bug 8 (low):** The `<pa-login-button>` popup flow opens `loginURL = base + /auth/login` which is not a valid Flask route through the proxy. The popup auth flow is incompatible with the proxy architecture. Remove or hide `<pa-login-button>` if it ever gets added, or document that Wikimedia OAuth fully replaces it.

---

## Step 4d — UX improvements + documentation screenshots ✓ (2026-05-14)

**Voting flow redesign**
- [x] Agree/Pass/Disagree now select-and-highlight rather than immediately submitting; Submit button activates once a choice is made
- [x] "Have a better way to put this?" propose box is always visible alongside the vote selection (not a post-vote interstitial), with a full-width amber-bordered textarea
- [x] If propose box has content on Submit, shows inline confirm: "Also share alternate phrasing?" → **Yes, suggest it** (submits statement + vote) / **No, just my vote**
- [x] Hidden `pa-vote-button` / `pa-submit-button` elements handle actual API submission via programmatic `.click()`

**Voting flow — design handoff (2026-05-14/15)**
- [x] Two screen modes: **idle** (full card: header + pa-statement + vote buttons + dashed propose inside) and **propose** (slim card: voted badge + compose form below)
- [x] Vote is a single click — no Submit step; immediately fires API vote and switches to propose mode
- [x] Voted badge in propose header: ✓ YOU VOTED [AGREE/PASS/DISAGREE] + change link; color-keyed to vote type
- [x] Compose form below card: starts open; submit disabled until textarea has content; submitted state uses amber/spot palette
- [x] Clicking idle propose affordance also enters propose mode (compose form, no voted badge)
- [x] Propose affordance inside idle card: dashed amber button, margin-top 18px from vote buttons

**Voting flow — remaining from design handoff**
- [x] **Progress row not populated**: Fixed in PR #21. Listens to `particiappstatementschange` (poll cycles) and `particiappstatechange` `'loaded'` (initial load via `conv.client.statements`); builds `.vote-seg` elements and shows done/total counts.
- [x] **Statement number removed**: `STATEMENT · #N` was dropped — statement order is session-specific and random (Fisher-Yates shuffle in `particiapp-web-client.js` → `#fetchStatements`, then re-sorted meta → seed → user-submitted), so a sequence number is meaningless across users. Label stays as plain `STATEMENT`. No information-gain routing is implemented yet (described aspirationally in `spec_functional-design.md`).

**Accept / join page**
- [x] Rewritten as plain-English "how it works" intro — less legalistic
- [x] Privacy & data handling moved into a foldable `<details>` section with placeholder text (to be replaced before public launch)
- [x] Notification preferences section clarifies these are best-effort and delivery is not guaranteed

**Admin**
- [x] Grant global admin: dropdown replaced with free-text Wikimedia username input; error shown if account not found

**Visual**
- [x] v2 badge removed from header
- [x] `FeaturedStatement.statement_text` nullable field added — Particiapi fallback when API is unavailable; used by screenshot seed

**Documentation screenshots**
- [x] `.claude/screenshot.py`: seeds isolated DB, starts Flask in dev mode, takes 7 retina screenshots via Playwright, saves to `docs/screenshots/`
- [x] Screenshots committed: home (logged-out + in), accept, vote, arguments, results, reveal

**Bug fixes**
- [x] Jinja2 `len()` → `|length` filter in `conversation.html` (Python built-ins not available in Jinja2 sandbox)
- [x] Reveal consent label: wrapped text in `<span>` so `<strong>` elements don't become separate flex items

**Simulation**
- [x] `simulate_cats_vs_dogs.py`: Flask registration now uses SQLAlchemy directly (no HTTP dev-login needed); `--flask-url` CLI argument added

---

## Step 4f — Bug fixes and local dev improvements (2026-05-15)

**Voting flow fixes (PRs #15, #17)**
- [x] Propose mode: statement text now stays visible and pre-fills textarea after voting (#1)
- [x] Removed "You'll vote first →" promise — Particiapi 403s self-votes so it could never be fulfilled (#16)
- [x] Button labels: "Nothing to propose" → "The current wording is good as it is"; "Submit & next" → "Submit my version as alternative"
- [x] Submit button greyed out until textarea differs from original text

**Admin fixes (PR #18)**
- [x] Featured statements admin: confirmed table now shows statement text (fetched from Particiapi on add/confirm; backfilled on page load for older rows) (#8)

**Local dev setup (PR #20)**
- [x] `v2/guide_local-dev.md`: full setup guide for native Flask + Docker backend
- [x] `particiapp-docker/docker-compose.local.yaml` (gitignored): exposes postgres to host on configurable port (`POSTGRES_HOST_PORT`)
- [x] `POLIS_DATABASE_URL` set in `v2/.env`; system suggestions and Polis stats now work locally (#9 / #19)
- [x] SQL scope bug in `get_featured_candidates` fixed (mixed comma + explicit JOIN) (#19)

---

## Step 5 — Featured statements + argument mapping tab (defer until Step 4 is community-tested)

### Design decisions (agreed 2026-05-13)

**Featured statement curation:** system suggests group-representative statements (high within-group agree rate, cross-group variance) + seed proposals always surfaced. Admin confirms. Falls back to manual-by-tid when `POLIS_DATABASE_URL` unavailable.

**Argument submission:** one pro + one con per participant per featured statement (DB-enforced via `UniqueConstraint('featured_statement_id', 'proposer_id', 'side')`). Two-column Pro | Con layout. Joined participants only (must have pseudonym for this conversation).

**Importance voting mechanic (threshold-gated, K-approval):**
- Voting method stored on `Conversation.argument_vote_method` (default `'kApproval'`) + `argument_vote_data` JSON (default `{'K': 2}`)
- Before a participant can cast importance votes they must complete a "contribute-or-skip" gate:
  - For each side (pro and con), they either submit an argument OR click "nothing to add"
  - Must complete both sides before voting on either
  - Gate state stored in `ArgumentSideState` (`skipped=True` for "nothing to add"; proposed state derived from `Argument` table directly)
- Once gated in: participant casts **K votes per side** (K=2 by default) on the arguments they find **most important** (terminology settled: "most important" — matches Citizens' Assembly practice; avoids persuasion framing of "convincing" and subjectivity of "meaningful")
- Votes are whole (1 per argument, row presence = approval) — spending both votes on the same argument is not allowed
- `ArgumentVote.value` is nullable: `NULL` for kApproval (presence = vote), integer rank for future ranked voting

**Data model (current — all tables already in db.py):**
- `Argument`: `proposer_id` nullable (NULL = seeded, no human author). `UniqueConstraint('featured_statement_id', 'proposer_id', 'side')` — SQL NULL semantics exempt seeds from uniqueness, allowing multiple seeds per (FS, side).
- `ArgumentVote`: `UniqueConstraint('argument_id', 'participant_id')`. `value` nullable integer (NULL for kApproval, rank for ranking). 2-per-side cap enforced at app level, not DB level.
- `ArgumentSideState`: one row per `(participant_id, featured_statement_id, side)`. Dual-purpose: `skipped` boolean (skip-gate) + `argument_order` JSON list of argument IDs (randomised display order, stable per participant, new arguments inserted at a random position on first encounter).

**Gate check per side** (proposed OR skipped):
```python
from db import Argument, ArgumentSideState

gate_passed = bool(
    Argument.query.filter_by(proposer_id=participant.id, featured_statement_id=fs.id, side=side).first()
    or
    ArgumentSideState.query.filter_by(
        participant_id=participant.id, featured_statement_id=fs.id, side=side, skipped=True).first()
)
```

### Checklist

- [x] Cluster analysis query (`get_featured_candidates`) — seeds first, then by agree rate; falls back gracefully when `POLIS_DATABASE_URL` absent
- [x] Admin page: `/admin/conversations/<id>/featured` — suggest + confirm + manual add + remove
- [x] Admin tile on conversation detail page
- [x] Argument tab read view: two-column Pro | Con per featured statement
- [x] Argument submission form (inline, one per side per FS)
- [x] "Nothing to add" skip button per side (creates/updates `ArgumentSideState` with `skipped=True`)
- [x] `ArgumentSideState` creation on first side view: randomise `argument_order`; append new arguments at random position on encounter
- [x] Importance voting UI: "Select the K most important arguments" prompt; unlocks when side ≥ K args AND participant gate-passed both sides
- [x] Importance vote POST route (K-cap enforced in app; unvote supported)
- [x] Moderator delete of arguments
- [x] Hash-aware tab restore (`#tab-arguments` after all argument form redirects)
- [x] Phrasing settled: **"most important"** (matches Citizens' Assembly practice)

---

## Codebase refactor — blueprint decomposition ✓ (2026-06-02)

Decomposed the ~1,300-line `_register_routes` closure in `app.py` into Flask blueprints,
per the audit's refactor plan (#94). Steps 1–4 landed earlier (PR #88); steps 5–9 completed
here. Every step was a **behavior-preserving** relocation — handler bodies verified
byte-identical (AST), zero test-assertion changes. `_register_routes` cyclomatic complexity
**177 → 33**.

- **#90 / #89** (PR #97) — lifted 5 non-route helpers to module level; deduped the three
  statement-text fetch blocks into one `_statement_text_map()`.
- **#91** (PR #98) — extracted the Particiapi proxy + statement-submit into `proxy_bp`
  (the `@csrf.exempt` + `_validate_same_origin` compensating control preserved). Also added
  `synthetic_traffic.py` (a proxy soak/load harness driving a deployed instance through the
  real Flask stack) and a runbook section documenting staging topology + a 5xx-investigation
  playbook.
- **#92** (PR #99) — extracted the ~23 `/admin/…` routes into `admin_bp` (both auth
  conventions — `@admin_required` vs `_require_mod_for_conv` — kept distinct; CSRF retained).
- **#93** (PR #100) — extracted the participant accept / conversation / argument / reveal
  routes into `participant_bp`. Auth / OAuth / index / logout / health / dev-login stay in
  `_register_routes` (they close over its locals).

Each step shipped alone with a senior + security review (cross-reviewed); #91 was soak-tested
and #91/#92/#93 staging-verified. Test suite grew 120 → 134 (promoted helper-characterization
tests + an admin-template smoke test).

---

## Phase 6 — Informed voting ✓ (2026-06-04, PR #115)

Second, independent voting round on the featured statements, shown with inline pro/con
arguments so participants deliberate before casting a clean vote.

**Data model**
- [x] `Conversation.phase_informed_voting` toggle (Boolean, default False)
- [x] `Conversation.phase6_polis_conversation_id` — dedicated Polis conversation for Phase 6 votes; UNIQUE constraint prevents double-init race
- [x] `FeaturedStatement.phase6_polis_statement_id` — Polis statement ID within the Phase 6 conversation; UNIQUE per conversation; `is not none` guard in template (Polis assigns tid=0 to first statement)
- [x] Alembic migration `3e86727dbcee` with indexes and constraints

**Admin**
- [x] `phase_informed_voting` checkbox in phase toggles form
- [x] Concurrent-phase warning when Phase 2 or argument mapping still on
- [x] "Informed voting — setup" section: "Initialise Phase 6" button creates dedicated Polis conversation and seeds all confirmed featured statements atomically (all-or-nothing; orphaned conv ID logged on failure)
- [x] Seeded-count display once initialised

**Participant UI**
- [x] "Informed voting" tab on conversation page (only for joined participants; only after init)
- [x] Cards per featured statement: statement text → top-3 pro arguments → top-3 con arguments → fold-out for arguments 4–10 → placeholder on empty side → Agree / Disagree / Pass
- [x] Vote route: `POST /c/<slug>/phase6/vote` on `participant_bp` (CSRF-protected, rate-limited 30/min, membership-checked, active/paused-guarded); resolves Polis IDs server-side from `fs_id` only; bootstraps Particiapi session + CSRF token before forwarding `PUT /api/conversations/{id}/votes/{tid}`

**Security (reviewed across 5 rounds by DB expert + security expert + senior engineer)**
- [x] Ballot stuffing via arbitrary pid/tid: closed — client sends only `fs_id`
- [x] Double-init race: UNIQUE constraint + IntegrityError handler
- [x] Partial seed failure: all-or-nothing commit
- [x] `add_seed` Phase 1 regression: restored independent implementation
- [x] `vote=True` (bool/int bypass): `isinstance(vote, bool)` guard
- [x] Wrong Polis vote endpoint: corrected to `PUT /api/conversations/{id}/votes/{tid}`
- [x] Active/paused guard on vote route
- [x] CSRF token forwarded to Particiapi on vote

## Step 7 — Admin phase control, CSV import, a11y (2026-06-08)

**Admin phase control** ([#140](https://github.com/lgelauff/wiki-polis/issues/140), [#156](https://github.com/lgelauff/wiki-polis/issues/156))
- [x] Guided "Move on" forward-transition box: consequence summary + per-phase readiness checklist (client-gated, server-re-validated); machine-checked "≥1 featured statement" precondition with met/not-met badge
- [x] "Advanced phase controls" (global admin only): independent per-phase toggles incl. backward moves; auto-opens in non-linear state
- [x] Phase-transition guard catalogue (hard + soft) documented in `spec_functional-design.md`

**Seed CSV import** ([#61](https://github.com/lgelauff/wiki-polis/issues/61))
- [x] Bulk import seed statements from a `text`-column CSV; 20-row / 100 KB caps; whole-file rejection over limit; UTF-8 + null-byte + formula-injection validation; per-row error reporting; duplicate-safe

**Accessibility** ([#150](https://github.com/lgelauff/wiki-polis/issues/150), [#166](https://github.com/lgelauff/wiki-polis/issues/166))
- [x] Participant-front WCAG 2.1/2.2 AA audit fixes (live regions, focus, contrast, reduced motion, skip link, headings)
- [x] Consultation listing: real list + heading semantics, pseudonym announced with context
- [x] Hidden pa-* API-proxy controls moved to `display:none` so they leave the a11y tree/tab order (interim; full de-dup tracked in [#159](https://github.com/lgelauff/wiki-polis/issues/159))

**Ops**
- [x] `deploy.sh --migrate` runs Alembic from the bastion via dynamic envvar loading + `MIGRATION_MODE=1` (skips web-server-only startup checks); documented in `guide_deployment.md`

## Phase-specific admin statistics (2026-06-09, [#165](https://github.com/lgelauff/wiki-polis/issues/165))

The admin conversation window's phase-hero stat block now shows numbers **scoped to the
current phase** instead of a fixed participants/votes/statements readout — they sit above
the guided "Move on" box and double as readiness signals (#156).

- [x] `_phase_stats(conv, polis_stats, phase6_stats)` builds per-phase tiles: Explore →
  participants / votes / statements + avg & median votes; Featured selection → selected vs
  recommended + candidate pool; Arguments & Cleanup → featured count, pro/con argument
  counts (human, visible — seeds and hidden excluded), distinct contributors & raters;
  Informed vote → statements seeded, round-2 participants/votes (from the Phase 6 Polis
  conversation) vs round-1 participants; Report → headline totals
- [x] Flask-derived tiles (featured, arguments) render even when Polis PG is down — only
  Polis-derived counts depend on it
- [x] **Loud warning banner** in the hero when `POLIS_DATABASE_URL` is configured but the
  stats DB is unreachable (`get_polis_stats` → None); stays silent when PG is intentionally
  not wired (local/dev), where None is expected
- [x] Tests: per-phase tile correctness (featured-selection, argument-mapping, informed-vote
  with mocked Phase 6 stats) + warning shown / not-shown by PG-configured state

**Review fixes (pr-check #183)**
- [x] Warning banner now also fires when the **round-2 (Phase 6) stats fetch fails** during
  informed voting — previously a phase-6 outage dropped the round-2 tiles silently
- [x] `n_raters` excludes raters whose only votes were on hidden/moderated arguments,
  matching the `Argument.hidden` filter the sibling tiles already apply
- [x] a11y: each stat tile carries an `aria-label` tying value→label→note together (screen
  readers read one phrase, not a stream of loose numbers); warning banner uses `role="status"`
  (not the render-time-inappropriate `role="alert"`); warning text darkened to clear AA
  contrast on the tinted panel

## Multi-phase statistics in the phase-control box (follow-up to #165)

In advanced mode an organizer can have several phase flags on at once. The phase-control
box previously collapsed that to the single furthest-along phase — showing one phase name
and only that phase's stats. It now reflects **every active phase**.

- [x] `_active_stage_indices(conv)` returns all on-flag stage indices (was: only the
  furthest via `_current_stage_index`)
- [x] `_phase_stats` split into `_phase_tiles(conv, key, …)` (per-phase tile builder) +
  `_phase_stat_groups(conv, …)` which returns one `{key, label, tiles}` group per active
  phase — addressing the long if/elif altitude nit from the #183 review
- [x] Phase-hero header: simple mode unchanged ("You are in phase N of M"); non-linear mode
  shows "Multiple phases active" + the active phase names joined
- [x] Stats render a labelled group per active phase; a single active phase still renders
  flat (no heading), identical to before
- [x] Phase-6 fetch + outage warning go back to gating on the `phase_informed_voting` flag
  (the round-2 tiles now render whenever that phase is active, not only when furthest), which
  supersedes the #183 narrowing coherently
- [x] Tests: group-per-active-phase rendering, single-phase stays flat, and the multi-phase
  phase-6-outage warning

**Review follow-up (#189):** reconcile the three "which phases are active" surfaces so the
box never contradicts itself in advanced mode.

- [x] Journey stepper now reflects multi-active state: in non-linear mode every active phase
  is marked *current* and none shown as *done* (was: driven by the single furthest-along
  stage, contradicting the "Multiple phases active" hero). `active_stage_indices` passed to
  the template.
- [x] Group labelling keys off the hero state (`not linear_phase_state`), not the tile count:
  a lone tiled group is still labelled when the header names ≥2 phases, so the reader can
  tell whose numbers they are.
- [x] The "...shown below" copy is reworded and omitted when no active phase currently has
  data (e.g. Polis-only phases while PG is down) — no dangling promise over an empty area.
- [x] a11y: each grouped `<dl>` is `aria-labelledby` its phase label, so a screen reader
  announces the group name rather than a flat number stream across phase boundaries.
- [x] Featured/argument DB aggregates memoized across phases in `_phase_stat_groups` (was:
  re-queried per active phase); dropped the duplicate `active_phase_labels` (header labels
  derive from the group list).
- [x] Tests: lone-tiled-group still labelled, all-Polis-only omits the copy, stepper marks
  every active step current.

## Step 8 — Phase 6 results report (2026-06-10)

**Phase 6 results — three surfaces** ([#122](https://github.com/lgelauff/wiki-polis/issues/122), [#165](https://github.com/lgelauff/wiki-polis/issues/165) partial)

- [x] `Phase6ResultsFilter` dataclass in `app.py`: `excluded_tids` (hidden Phase 6 statements) + `excluded_pids` (banned participants, empty until #60); applied uniformly across all result surfaces
- [x] Three new `PolisServerClient` Postgres methods (all query `votes_latest_unique`): `get_phase6_vote_counts(zinvite, allowed_tids, excluded_pids)`, `get_phase6_participant_count`, `get_personal_votes`
- [x] `_build_phase6_results` helper: per-statement Phase 2 vs Phase 6 comparison, shift calculation, personal vote lookup (deferred pending xid→pid mapping), source-divergence check between PG and Particiapi; graceful fallback when PG unavailable
- [x] **Surface A — preliminary** (`conversation.html` results tab): agree/disagree bar chart per statement, shift indicator (↑/↓), personal vote badge, preliminary banner; shown while round is live
- [x] **Surface B — final report** (`/c/<slug>/report`): new route + `report.html` template; aggregate only, opinion-shift table, cluster section from Particiapi, participation counts, moderation note, Final badge; public when `phase_public_results`, login-gated when `phase_personal_results` only
- [x] **Surface C placeholder** in final report: "Where did you land?" self-comparison section reserved, full implementation deferred
- [x] **Admin stats slice** (#165, informed voting only): Phase 6 participant count, statement count, largest-shift teaser in admin conversation stats panel
- [x] Done screen updated: closed-state links to final report
- [x] Docs: `ref_data-model.md` (two-conversation architecture, vote-sign, filter model, result surfaces), `ref_polis-data-model.md` (`votes_latest_unique` Phase 6 note), `guide_organizer.md` (new "Read the informed voting results" section)

---

## Parallel-lanes wave — admin, participant UX, phase model, privacy, ops (2026-06-13 → 2026-07-09)

Merged as [#236](https://github.com/lgelauff/wiki-polis/pull/236) (~50 issues across six work
lanes) plus follow-ups. This wave took the app from a few phase toggles to the current
7-phase model with an organizer role, in-app moderation, scheduled transitions, and an
embedding sidecar. (The lane names were an engineering branch-organization strategy, not a
product concept.)

**Lane 1 — admin & moderation**
- [x] Argument moderation queue in the admin panel (#84)
- [x] Ban conversation participants + public ban log (#60)
- [x] Community flag review queue — participants flag statements/arguments, moderators resolve (#138)
- [x] Conversation **organizer** role, distinct from global admin / moderator (#154)
- [x] Admin participants engagement tab (#42); admin interface visual-mode distinction; disabled-button greying; clearer flag-affordance copy

**Lane 2 — participant voting & arguments** (#57 #71 #82 #185 #202 #219 #220)
- [x] Participant writing guides (#57); mobile card tap affordance (#71); simplified pseudonym setup (#82); vote-progress label (#185)
- [x] Skip arguments from the list / easy-skip contribute row (#202); clearer arguments all-done copy and completed-side gating (#219, #220)

**Lane 3 — phase model, scheduling & outputs** (#160 #164 #173 #180 #186 #187 #194 #195 #214 #215 #216 #226)
- [x] The passive **Cleanup** phase between arguments and informed voting (`phase_cleanup`, #163)
- [x] Named **phase routes** — `default_7` / `no_informed_vote` / `short_results` via `phase_route` (#173)
- [x] **Scheduled phase transitions** (`scheduled_transition_*`), applied by the phase-scheduler Toolforge job (#164)
- [x] Recommended quantities per conversation size (#160); report-filter snapshot at close (#186)

**Lane 4 — privacy, anonymisation & provenance** (#96 #113 #143 #146 #207 #210 #223)
- [x] xid HMAC keying, versioned by `xid_key_version` (#96); `arguments.proposer_id` → `proposer_pseudonym` (#113)
- [x] Statement provenance + similarity-scoring tables (#143, #207); conversation eligibility gate (#146); demo participant marker (#223)

**Lane 5 — ops, infra & reliability** (#49 #55 #118 #129 #130 #139 #199 #208 #217)
- [x] Loki / fluent-bit log-aggregation stack, backup scripts, microservice smoke test + CI; embedding-sidecar similarity contract (#207/#208)

**Lane 6 — routing + particiapi proxy refactor** (#112 #159)

**Cross-cutting**
- [x] Heuristic statement advising module (#56); delete zero-vote conversations (#145); WCAG AA target-size + toast politeness (#157)
- [x] Alembic migrations linearized to a single head; internal Claude plan files removed from the repo (`v2/.claude` gitignored)

**Seed-import churn** — raised the bulk limit 20→200 (#227), then reversed: lowered it back 200→20, capped text-area paste at `MAX_FILE_BYTES` (#238), and removed the redundant CSV-upload route/parser/UI in favour of a text-area paste (tests migrated).

**Cross-device / conversation-scoped identity**
- [x] Pass the user xid to Particiapi for a stable cross-device participant (#245); don't follow upstream redirects, never bind identity on the unscoped route (#263); warn when the identity secret crosses a cleartext hop (#264)
- [x] **Conversation-scoped** participant identity — a different Polis uid per conversation, no cross-conversation chain (#246/#247)

**MariaDB migration correctness** — FK-before-index reorder for MySQL error 1553; SQLite-safe migration upgrades; a **MariaDB migration check** (local + CI) to catch MySQL-only bugs (#267).

**Post-merge stabilization**
- [x] Dedup admin per-statement vote counts — `votes_latest_unique` + `COUNT(DISTINCT pid)` (#269 / #271)
- [x] **Restore the phase-scheduler Toolforge job wiring dropped in the #236 merge (#272 / #274)** — a regression the merge itself introduced
- [x] Phase-6 auto-resync when featured statements change mid-round, and warn before a live-round featured edit (#276)
