# Next Steps

Ordered by dependency. Each step is independently testable before the next begins.

---

## Step 1 — Run Polis + Particiapi locally

**Goal:** Validate the approach before touching any infrastructure.

- [ ] Clone gitlab.com/particiapp/particiapp-docker
- [ ] Configure with a local test OIDC provider
- [ ] `docker compose up` — confirm Polis + Particiapi running
- [ ] Browse the reference frontend; evaluate web components in practice
- [ ] Confirm voting loop, statement submission, and SSO flow work

**Deliverable:** Working local stack. Go/no-go decision on Particiapi approach confirmed by seeing it in a browser.

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

## Step 4 — Build Flask app v2

- [ ] Start fresh Flask app (builds on v1 structure)
- [ ] Clean data model: Conversation (with 4 phase toggle fields), Participant, Participation, ConversationInvite, AdminRole, FeaturedStatement, Argument, ArgumentVote
- [ ] Replace PolisClient with ParticiapiClient wrapping Particiapi JSON API
- [ ] Wikimedia OAuth flow (port from v1)
- [ ] Conversation listing: active / archived / available / moderating sections
- [ ] Accept flow
- [ ] Conversation page: embed `<pa-statement>` + `<pa-vote-button>`; inline "propose alternative" prompt
- [ ] Admin panel: conversations, phase toggles, roles, invites
- [ ] Confirm end-to-end: Flask login (Wikimedia OAuth) → Flask proxies voting with xid → Polis records vote

**Deliverable:** End-to-end working app on Toolforge connected to VPS Polis.

---

## Step 5 — Featured statements + argument mapping tab (defer until Step 4 is community-tested)

- [ ] Cluster analysis query to surface featured statement suggestions
- [ ] Admin confirms / dismisses suggestions
- [ ] Argument mapping tab: pro/con submission, usefulness voting, sorted display
- [ ] Phase toggle 3 (argument mapping) wired to show/hide the tab
