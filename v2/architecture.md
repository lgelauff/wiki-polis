# Wiki-Polis v2 Architecture

Decisions finalised 2026-05-10.

---

## System diagram

```
                        ┌─────────────────────────────────────┐
                        │           Toolforge (our tool)       │
                        │                                       │
  Browser ─────────────▶│  Flask app (wiki-polis)              │
                        │  - Wikimedia OAuth (single login)     │
                        │  - All UI (conversation list,         │
                        │    voting page, argument tab,         │
                        │    accept flow)                       │
                        │  - Admin: conversations, roles,       │
                        │    invites, featured statements,      │
                        │    phase toggles                      │
                        │  - Proxies voting calls to VPS        │
                        │  - MariaDB (ToolsDB) — identity layer │
                        └──────────────┬──────────────────────┘
                                       │ internal proxy (xid only)
                        ┌──────────────▼──────────────────────┐
                        │      VPS — Docker Compose            │
                        │                                       │
                        │  Particiapi (internal only)           │
                        │  - Auth disabled                      │
                        │  - JSON API to Polis                  │
                        │                                       │
                        │  Polis (stock, Node.js)               │
                        │  - Statement routing                  │
                        │  - Voting storage (xid only)          │
                        │  - Clustering / PCA math              │
                        │  - Admin UI (moderation)              │
                        │                                       │
                        │  PostgreSQL + Redis                   │
                        │  — deliberation layer (pseudonymised) │
                        └─────────────────────────────────────┘
```

The VPS runs a standard Docker Compose stack. Same `docker-compose.yml` used locally and in production. Particiapi is not exposed publicly — Flask proxies all calls to it.

---

## Data separation

The two databases reflect a separation of concerns between identity management and deliberation data.

**Toolforge — MariaDB — identity layer**

| Data | Notes |
|---|---|
| Participants | mw_user_id, mw_username, xid |
| Conversations | metadata, access policy, phase toggles |
| Participation records | who joined what |
| Invites + roles | access control |
| Featured statements | curation metadata |
| Arguments + argument votes | argument layer |

**VPS — PostgreSQL — deliberation layer**
Polis receives only the xid (SHA-256 of the Wikimedia user ID), not the username or user ID directly.

| Data | Notes |
|---|---|
| Votes | attributed to xid |
| Statements | attributed to xid |
| Clusters + math results | aggregate |

Note: xid is not cryptographically anonymous — Wikimedia user IDs are enumerable. Vote data is kept separate during collection to support independent opinion formation (anti-herding), not to provide identity protection. Cluster positions become public when the admin enables full public results.

---

## Auth flow

Single login. Particiapi is on an internal Docker network — not publicly accessible.

1. User hits Flask (Toolforge) → Wikimedia OAuth → Flask session established
2. Flask looks up or creates the user's xid
3. User votes → browser calls Flask → Flask proxies the request to Particiapi with the xid as the participant identity
4. Particiapi records the vote against the xid in Polis

Particiapi runs with `PARTICIAPI_AUTHENTICATION_DISABLED=True`. It trusts requests from Flask. The browser never communicates with Particiapi directly.

**One Wikimedia OAuth client registration:** `wiki-polis` (Flask app) — already exists. No second registration needed.

---

## Particiapi

We use stock Particiapi with `PARTICIAPI_AUTHENTICATION_DISABLED=True`. No fork needed for auth — Flask handles Wikimedia OAuth entirely. The email_verified patch (in `v2/tmp/`) is still worth submitting upstream as a general improvement, but it is no longer a blocker for our deployment.

---

## Technology decisions

| Layer | Technology | Notes |
|---|---|---|
| Auth wrapper / admin | Python / Flask | Runs on Toolforge |
| Polis API abstraction | Particiapi (stock, auth disabled) | Runs on VPS via Docker Compose; Flask proxies all calls |
| Voting UI | Particiapp web components | `<pa-statement>`, `<pa-vote-button>` only |
| Everything else | Our Flask templates + vanilla JS | Argument tab, conversation list, accept flow |
| Database (our data) | MariaDB via SQLAlchemy | Toolforge ToolsDB |
| Database (Polis data) | PostgreSQL | VPS, managed by Polis Docker container |
| Polis runtime | Stock Polis (Node.js) | VPS via Docker Compose; no fork |
| Moderation | Polis admin UI | No in-app moderation UI |

---

## Data model

**Conversation** — slug, polis_id, title, intro_text, outro_text, active, access_policy, phase_submission, phase_personal_results, phase_argument_mapping, phase_public_results, created_at

**Participant** — mw_user_id, mw_username, xid, created_at

**Participation** — participant + conversation + pseudonym (unique across all participations) + notify_email + notify_talk_page

**ConversationInvite** — conversation + mw_username

**AdminRole** — participant + role (admin / moderator) + scope (global or per-conversation)

**FeaturedStatement** — conversation + polis_statement_id + suggested_by_system (bool) + confirmed_by_admin (bool)

**Argument** — featured_statement + author (Participant) + body (max 280 chars) + side (pro / con) + created_at

**ArgumentVote** — argument + participant + useful (bool)

Removed vs. old v2: `ModAction` (not needed), `featured` flag on Conversation (removed), `arguments_enabled` on FeaturedStatement (replaced by conversation-level `phase_argument_mapping` toggle).

---

## Phase plan

### Phase 0 — Complete ✓
Hosted pol.is working, xid integration working, Wikimedia OAuth working in v1.

### Phase 1 — Infrastructure + foundation
- Deploy Polis + Particiapi on VPS via Docker Compose (Particiapi with `PARTICIAPI_AUTHENTICATION_DISABLED=True`)
- Flask app: clean data model, replace PolisClient with ParticiapiClient
- Conversation page: remove alpha embed, add voting web components
- Flask proxies all voting calls to Particiapi with xid as participant identity
- Access policies enforced; admin can create conversations, manage roles and invites

### Phase 2 — Frontend
- Inline "propose a better alternative" prompt in voting loop
- Phase toggles in admin panel (submission, personal results, argument mapping, public results)
- Home page: active / archived / available / moderating sections
- Accept flow with intro/outro text
- Mobile-responsive layout

### Phase 3 — Featured statements + argument mapping
- Cluster-based system suggestions for featured statements
- Admin confirms/dismisses suggestions; can also manually feature
- Argument mapping tab: pro/con submission, usefulness voting, sorted display

### Phase 4 — Return engagement (deferred)
- "New since last visit" indicators
- Notifications (talk page or email)

### Phase 5 — Analytics export (deferred)
- Structured export of votes, clusters, arguments
- Anonymisation options

---

## What we do not build

- In-app moderation UI (Polis admin panel handles this)
- Clustering visualisation (Polis results page; custom viz deferred)
- Nested replies or threading
- Recommendation feeds
- Any AI features (out of MVP scope)
