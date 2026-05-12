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

## Step 5 — Featured statements + argument mapping tab (defer until Step 4 is community-tested)

- [ ] Cluster analysis query to surface featured statement suggestions
- [ ] Admin confirms / dismisses suggestions
- [ ] Argument mapping tab: pro/con submission, usefulness voting, sorted display
- [ ] Phase toggle 3 (argument mapping) wired to show/hide the tab
