# Wiki-Polis v2 Architecture

> **Status — current spec (architecture as built).** How wiki-polis is structured and
> why. Describes the system as it is *meant to work* today; where the build diverges,
> that's a tracked gap (`pending` marker). Product behaviour →
> [`spec_functional-design.md`](spec_functional-design.md); database schema →
> [`ref_data-model.md`](ref_data-model.md); what's built / what's next →
> [`log_changelog.md`](log_changelog.md) / [`plan_roadmap.md`](plan_roadmap.md).

---

## System diagram

```
                        ┌─────────────────────────────────────┐
                        │           Toolforge (our tool)       │
                        │                                       │
  Browser ─────────────▶│  Flask app (wiki-polis)              │
  (React SPA)           │  - Wikimedia OAuth (single login)     │
      │                 │  - Serves the SPA shell + a           │
      │  GET /api/v1/*  │    same-origin JSON API; all UI is   │
      └────────────────▶│    the SPA's (conversation list,      │
                        │    voting, arguments, accept flow)    │
                        │  - Admin: conversations, roles         │
                        │    (moderator/organizer), invites,     │
                        │    featured statements, phase          │
                        │    toggles, content-flag moderation    │
                        │    queue, conversation bans            │
                        │  - Calls Particiapi server-side       │
                        │  - Reads Polis Postgres directly       │
                        │    for admin moderation views         │
                        │  - MariaDB (ToolsDB) — identity layer │
                        └──────────────┬──────────────────────┘
                                       │ server-side only (xid only)
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
                        │  — deliberation layer                 │
                        └─────────────────────────────────────┘
```

The browser never talks to Particiapi and never holds a Polis session cookie: every call
is same-origin to `/api/v1/*`, and Flask carries the conversation-scoped identity forward.
The VPS runs a standard Docker Compose stack — the same `docker-compose.yml` locally and
in production. Particiapi is not exposed publicly; Flask calls it server-side.

**Two optional external integrations.** Flask calls these directly over outbound HTTP —
not proxied through Particiapi — and both degrade gracefully when unconfigured or
unreachable:

```
  Flask app (wiki-polis) ── optional, best-effort ──▶ ┌───────────────────────────────┐
                                                      │ Embedding sidecar (#208)      │
                                                      │ FastAPI · /similarity, /embed │
                                                      └───────────────────────────────┘
                                                      falls back to stdlib difflib if unset/unreachable

  Flask app (wiki-polis) ── optional, join-time ────▶ ┌──────────────────────────────┐
                                                      │ External eligibility service │
                                                      │ (event-keyed join gate)      │
                                                      └──────────────────────────────┘
                                                      gates join only when eligibility_event_id is set
```

- **Embedding sidecar** (`STATEMENT_SIMILARITY_URL`) — a small FastAPI service
  (`v2/embedding_sidecar/`), typically run on the same VPS next to Particiapi/Polis but
  reachable over plain HTTP, not the internal Docker network used for voting. `_semantic_similarity()`
  POSTs `{"left": ..., "right": ...}` and expects `{"similarity": <float>}`, with a short
  timeout; if the URL is unset or the call fails, statement-derivation similarity scoring
  falls back to a stdlib `difflib` ratio, so the app is fully functional without it.
- **Eligibility service** (`ACCOUNT_ELIGIBILITY_URL`) — an arbitrary external HTTP
  endpoint. `_check_join_eligibility()` only calls it for conversations that set an
  `eligibility_event_id`; it GETs the endpoint keyed by that event ID and the joining
  user, and fails closed (join denied) if the service is unconfigured or errors.

---

## Data ownership

**Two stores**, split by concern:

**1. App database — MariaDB (ToolsDB) in prod, SQLite in dev — the identity & argument layer.**
Conversations, participants, participations (pseudonyms, reveal state), invites, roles,
featured statements, arguments, argument votes, and side states. Full schema:
[`ref_data-model.md`](ref_data-model.md).

**2. Polis — PostgreSQL on the VPS — the deliberation layer.**
Votes, statements, and clustering/PCA results, attributed to the **xid** only — Polis
never receives the username or user ID. (The Redis alongside it is a cache/queue, not a
store of record.)

**Two routes to the Polis store — not a third store.** Particiapi is the JSON API *in
front of* Polis Postgres; it doesn't hold data of its own. The same deliberation data is
reached two ways depending on the surface (intended, decision **D-STORE**):
- *Participants* (the voting page) go Browser → `/api/v1/*` → Flask → **Particiapi
  (HTTP)** → Polis Postgres — the live, approved view.
- *Admins* (moderation and stats views) read **Polis Postgres directly** via raw SQL,
  because they need moderation buckets and vote counts the participant API doesn't
  expose. An HTTP fallback exists but doesn't fire while Postgres is up.

Same data, two routes; the two clients return slightly different shapes — a minor
cleanup, not a redesign.

**xid is an identity bridge, not anonymity.** The xid is now `HMAC(secret, mw_user_id)`
(versioned; forwarded conversation-scoped), which removed the brute-forceability of the
old plain `sha256(mw_user_id)`. The store split exists to support independent opinion
formation (anti-herding) during collection, **not** to provide identity protection.
Cluster positions become public when the admin enables full public results. *(#96: the
salt/HMAC half shipped; rotating/deleting the xid mapping at anonymisation is still open —
see [ADR 0002](adr/0002-auth-proxy-and-xid.md).)*

---

## Auth flow

Single login. Particiapi is on an internal Docker network — not publicly accessible.

1. User hits Flask (Toolforge) → Wikimedia OAuth → Flask session established
2. Flask looks up or creates the user's xid
3. User votes → browser calls `/api/v1/*` on this origin → Flask calls Particiapi
4. On session-create Flask asserts the user's stable identity to Particiapi (the xid,
   via a trusted-subject header) so the same user keeps **one** Polis participant across
   devices; Particiapi records votes against that uid in Polis

> **Note:** step 4 is gated on the `PARTICIAPI_SUB_SECRET` ↔ `TRUSTED_SUB_SECRET` shared
> secret being set on both sides. Without it, Particiapi mints a **new anonymous
> participant per session** (one person fragments into many). Mechanism, the bug it fixes,
> and deploy steps: [`ref_cross-device-identity.md`](ref_cross-device-identity.md).

Particiapi runs with `PARTICIAPI_AUTHENTICATION_DISABLED=True`. It trusts requests from
Flask. The browser never communicates with Particiapi directly.

**One Wikimedia OAuth client registration:** `wiki-polis` (Flask app) — already exists.
No second registration needed.

---

## Particiapi

We use stock Particiapi with `PARTICIAPI_AUTHENTICATION_DISABLED=True`. No fork needed for
auth — Flask handles Wikimedia OAuth entirely. (An `email_verified` patch was prepared as
a general upstream improvement; it is not a blocker for our deployment.)

---

## Technology decisions

| Layer | Technology | Notes |
|---|---|---|
| Auth wrapper / admin | Python / Flask | Runs on Toolforge |
| Polis API abstraction | Particiapi (stock, auth disabled) | Runs on VPS via Docker Compose; Flask calls it server-side, the browser never does |
| Browser UI | React 19 SPA (`v2/frontend/`) + Vite | The only browser surface. Flask serves the shell document and a same-origin JSON API at `/api/v1/*`; the SPA owns all client routing. See [ADR 0004](adr/0004-versioned-browser-api-and-spa.md) |
| Database (our data) | MariaDB via SQLAlchemy | Toolforge ToolsDB (SQLite in dev/tests) |
| Database (Polis data) | PostgreSQL | VPS, managed by the Polis Docker container |
| Polis runtime | Stock Polis (Node.js) | VPS via Docker Compose; no fork |
| Moderation | SPA admin panel + Polis admin UI | Statement moderation (approve/hide/seed) and argument moderation (hide/delete) in the SPA admin, reached through `/api/v1/admin/*`; Polis admin UI for clustering/math |
| Message catalogues | Translatewiki + `v2/i18n/*.json` | The SPA fetches `/api/v1/i18n/<locale>`; the server refuses translations whose markup signature or plural slots differ from English |
| Statement similarity (optional) | Embedding sidecar — FastAPI + sentence-transformers | `v2/embedding_sidecar/`; Flask calls it directly over HTTP, best-effort with a short timeout; falls back to stdlib `difflib` if unset/unreachable — no hard dependency |
| Join eligibility (optional) | External eligibility service (HTTP) | Arbitrary endpoint set via `ACCOUNT_ELIGIBILITY_URL`; only invoked for conversations with an `eligibility_event_id`; fails closed if unconfigured or erroring |

### How a request reaches Polis

There is no browser-facing proxy. The browser only ever talks to `/api/v1/*` on this
origin:

```
Browser ──▶ Flask /api/v1/*  ──▶ Particiapi (HTTP) ──▶ Polis Postgres
           (auth + shaping)      (server-side only)
```

Participant surfaces go out over HTTP to Particiapi; admin surfaces read Polis Postgres
directly via raw SQL because they need moderation buckets the participant API does not
expose. The two clients return slightly different shapes — a minor cleanup, not a
redesign. Route-by-route authorization is in
[`docs/route_authorization_matrix.md`](docs/route_authorization_matrix.md).

---

## Static assets

Static files (CSS, fonts, JS) are served directly by Flask from `v2/static/`. The SPA
bundle is built into `v2/static/spa/` by `npm run build` at deploy time; that directory is
gitignored, which is why the branded error pages in `error_pages.py` deliberately depend on
nothing — not the bundle, not a template, not a stylesheet.

**Caching strategy:** all `/static/` responses carry `Cache-Control: public, max-age=604800` (1 week).
A new deploy busts the cache by changing the URLs: Vite gives every bundle file a
content-hashed name (`index-<hash>.js`), so a rebuild produces new asset URLs and the
browser fetches them fresh. No CDN or manual cache invalidation is needed. The build's
git SHA is surfaced separately — in the SPA footer and as `gitVersion` from
`GET /api/v1/session` — and is what a reader should compare against a deploy.

**Scope:** only truly static files benefit from this — fonts, stylesheets, and bundled JS.
`/api/v1/*` responses and dynamically generated Polis cluster images are not under
`/static/` and are always served fresh. The `/api/v1/*` responses that could otherwise be
cached carry `Cache-Control: no-store` explicitly, since they are per-participant.

---

## Status & roadmap

This document describes the architecture **as built**, not a build sequence. For the
product phases (the four toggles), see
[`spec_functional-design.md`](spec_functional-design.md); for what has been built, the
[build log](log_changelog.md); for what's planned next, the [roadmap](plan_roadmap.md).

---

## What we do not build

- Custom clustering visualisation (we use the Polis results page; custom viz deferred)
- Nested replies or threading
- Recommendation feeds
- Any AI features (out of MVP scope)
