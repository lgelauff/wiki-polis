# Next Steps

Ordered by dependency. Each step is independently testable before the next begins.

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

## Step 2 — Deploy VPS stack

- [ ] Provision a VPS (~$6/month, any provider)
- [ ] Install Docker + Docker Compose
- [ ] Deploy stock particiapp-docker stack (Polis + Particiapi with `PARTICIAPI_AUTHENTICATION_DISABLED=True`)
- [ ] Configure HTTPS (reverse proxy); Particiapi must not be publicly exposed
- [ ] Set up nightly `pg_dump` → offsite backup (Swift or equivalent)
- [ ] Confirm production stack reachable from Flask

**Deliverable:** Polis + Particiapi running in production, internal only.

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
- [x] `polis_admin.py` PolisAdminClient rewritten to use correct Particiapi paths (`api/conversations/<id>/statements/`, `/results/`); raises `PolisAdminError` for unsupported operations (moderate, seed, strict-moderation)
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
- [x] Reveal routes (`GET/POST /c/<slug>/reveal`) with cooldown gate, nullification gate, irreversible-warning form
- [x] Lazy nullification in conversation view: clears identity links at `cooldown + window` days post-close
- [x] Minimum-N warning on results (< 25 participants): shown above public results, does not hide results
- [x] Consent copy on accept page updated to reflect platform-wide pseudonym uniqueness and operator data retention

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

## Step 5 — Featured statements + argument mapping tab (defer until Step 4 is community-tested)

### Design decisions (agreed 2026-05-13)

**Featured statement curation:** system suggests group-representative statements (high within-group agree rate, cross-group variance) + seed proposals always surfaced. Admin confirms. Falls back to manual-by-tid when `POLIS_DATABASE_URL` unavailable.

**Argument submission:** one pro + one con per participant per featured statement (DB-enforced via `UniqueConstraint('featured_statement_id', 'proposer_id', 'side')`). Two-column Pro | Con layout. Joined participants only (must have pseudonym for this conversation).

**Importance voting mechanic (threshold-gated, K-approval):**
- Voting method stored on `Conversation.argument_vote_method` (default `'kApproval'`) + `argument_vote_data` JSON (default `{'K': 2}`)
- Unlocks per-side when that side reaches ≥ 5 arguments
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
