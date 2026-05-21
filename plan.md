# wiki-polis — Deployment Plan

_Updated 2026-05-21. Detailed build history in `v2/next_steps.md`._
_Reviewed by DevOps, Security, and Senior Dev agents (cross-reviewed 2026-05-21)._

---

## Current state

| Layer | Status |
|---|---|
| Flask app (v2) | ✅ Complete, 98 tests green |
| Arguments tab redesign (Step 4e) | ✅ Complete — PR #22 open, not yet merged |
| Cloud VPS project | ✅ Created (`wiki-polis-backend`, T425892) |
| VPS instance | ❌ Not yet provisioned |
| Toolforge tool account | ❌ Not yet created |
| Wikimedia OAuth consumer | ❌ Not yet registered |

---

## Pre-deployment fixes (must be done before first launch)

All three agents cross-reviewed. Items marked ⚠️ had disagreements — note is included.

### Code fixes

- [ ] **`argument_unvote` cross-conversation** — route does not join `arg_id` to the current conversation; a participant could unvote arguments in other conversations by guessing integer IDs. Add a join to `FeaturedStatement.conversation_id`. (`app.py`)
- [ ] **Proxy DELETE restriction** — `POST /proxy/particiapi/...` forwards any authenticated `DELETE` with only `@login_required`. Restrict to moderators/admins, or audit Particiapi's DELETE surface first. ⚠️ _Senior dev: PRE; others: POST. Promoted to PRE given Particiapi auth is disabled._
- [ ] **`_is_emailable()` blocks login** — synchronous `requests.get` with 5s timeout called on every OAuth callback. A slow Meta-wiki stalls the entire uWSGI worker (single-process). Wrap in try/except with immediate fallback to `False` rather than waiting for timeout. ⚠️ _DevOps/Security: PRE; Senior dev: POST. Promoted to PRE — a hanging login page is a bad first impression._
- [ ] **Issue #5 (argument moderation) blocks launch** — `moderate()` in `polis_admin.py` unconditionally raises `PolisAdminError`; there is no way to hide an abusive argument. Either implement a workaround or remove the moderation button from the admin UI with a clear note. ⚠️ _Conditional: if real community members participate on day one this must land; if first deploy is internal/testing only it can wait one sprint._

### Runbook fixes (deployment.md + plan.md)

- [ ] **Fix bind address contradiction** — `deployment.md` binds Particiapi to `127.0.0.1:8000`; `plan.md` says bind to the private IP. These contradict. Correct `deployment.md`: bind to `0.0.0.0:8000` (or the private IP) and rely on the security group to restrict access.
- [ ] **ToolsDB charset** — `deployment.md` uses `CHARACTER SET utf8`; `plan.md` says `utf8mb4`. Use `utf8mb4 COLLATE utf8mb4_unicode_ci` everywhere — emoji and non-Latin scripts are common in Wikimedia contexts. Migrating after creation is painful.
- [ ] **Swap `flask init-db` / `webservice start` order** — Stage 3 currently starts the webservice before `init-db`. Any request hitting the app before tables exist = 500. Run `init-db` first.
- [ ] **Add `ADMIN_USERS` envvar to Stage 3 runbook** — `_read_secret('admin-users')` is the only source; if absent, no one can reach `/admin` on first deploy. Add `toolforge envvars create admin-users '<username>'` as an explicit step.
- [ ] **Add pre-launch checklist step** — confirm `DEV_LOGIN_USER` and `FLASK_DEBUG` are absent from `toolforge envvars list` before starting the webservice.

### Infrastructure (VPS)

- [ ] **Resolve issue #35** (security group for Toolforge → Particiapi port 8000) — must be done before Stage 2 complete. The security group rule must be as narrow as possible; broad Toolforge CIDR exposes unauthenticated Particiapi to all other Toolforge tools. Investigate cross-project security group reference in Horizon first.
- [ ] **Docker restart policy** — add `restart: unless-stopped` to all services in `docker-compose.yml` and `sudo systemctl enable docker`. ⚠️ _Senior dev argued POST (manual restart is quick); DevOps argues PRE. Keeping PRE — a VM reboot after maintenance on day one would be embarrassing._

---

## Path to production

### Stage 1 — Merge & smoke test (local)

- [ ] Merge PR #22 (arguments tab redesign)
- [ ] Apply pre-deployment code fixes above
- [ ] Run `dev.sh` full stack; verify end-to-end: login → accept → vote → argument submit → admin phase toggle
- [ ] Confirm all tests pass: `pytest v2/tests/`

---

### Stage 2 — VPS: provision and deploy backend

**Closes issue #14.**

- [ ] Provision instance on [Horizon](https://horizon.wikimedia.org) in project `wiki-polis-backend`
  - Flavor: `g4.cores2.ram4.disk20` (minimum) or `g4.cores4.ram8.disk20`
  - OS: Debian (latest available)
  - Security group: default
- [ ] SSH in: `ssh -J <user>@bastion.wmcloud.org <user>@<instance>.wiki-polis-backend.eqiad1.wikimedia.cloud`
- [ ] Install Docker CE from Docker's apt repo (see `v2/cache/cloud-vps.md`)
- [ ] `sudo systemctl enable docker`
- [ ] Clone `particiapp-docker` with `--recurse-submodules`
- [ ] Configure `.env` — bind Particiapi to `0.0.0.0:8000` (not `127.0.0.1`); set `restart: unless-stopped` on all services
- [ ] `docker compose up -d` — verify `curl http://localhost:8000/api/conversations/` returns `[]`
- [ ] **Resolve issue #35**: find Toolforge pod CIDR, add TCP ingress rule for port 8000 in Horizon security groups
- [ ] Verify from Toolforge webservice shell: `curl http://<vps-private-ip>:8000/api/conversations/`
- [ ] Set up nightly backup cron (pg_dump → B2 or similar; see `v2/deployment.md`)

---

### Stage 3 — Toolforge: deploy Flask app

- [ ] Create tool account `wiki-polis` via [toolsadmin.wikimedia.org](https://toolsadmin.wikimedia.org)
- [ ] SSH to `login.toolforge.org`, `become wiki-polis`
- [ ] Clone repo: `git clone https://github.com/lgelauff/wiki-polis.git ~/wiki-polis`
- [ ] `mkdir -p ~/www/python && ln -s ~/wiki-polis/v2 ~/www/python/src`
- [ ] Install venv inside webservice shell (see `v2/deployment.md`)
- [ ] Create ToolsDB database: `sql tools` → `CREATE DATABASE s_wiki_polis__main CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`
- [ ] Set envvars (SECRET_KEY, PARTICIAPI_BASE_URL, DATABASE_URL, POLIS_DATABASE_URL, admin-users)
- [ ] **Run `flask init-db` BEFORE starting webservice**
- [ ] `cd ~ && toolforge webservice python3.13 start`
- [ ] Confirm `DEV_LOGIN_USER` and `FLASK_DEBUG` absent: `toolforge envvars list`
- [ ] Verify home page loads at `https://wiki-polis.toolforge.org/`

---

### Stage 4 — Wikimedia OAuth consumer

_Register in parallel with Stage 2–3; approval takes several days._

- [ ] Register at [Special:OAuthConsumerRegistration](https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration)
  - Confidential client; callback: `https://wiki-polis.toolforge.org/oauth-callback`
  - Grants: Basic rights, confirm email address
- [ ] Once approved: add `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_REDIRECT_URI` envvars
- [ ] `cd ~ && toolforge webservice python3.13 restart`
- [ ] Test full OAuth login end-to-end

---

### Stage 5 — Production smoke test

- [ ] Login → accept → vote → submit argument
- [ ] Admin: create conversation, toggle phases, add featured statement
- [ ] Test from incognito window
- [ ] Check `toolforge webservice logs` for errors

---

## Issue priority

### Block deployment

| Issue | Why |
|---|---|
| PR #22 | Merge before deploying |
| #35 | Toolforge → VPS connectivity required |
| #14 | VPS deployment itself |
| (new) Bind address fix in deployment.md | Silently breaks all connectivity if not fixed |
| (new) ADMIN_USERS in runbook | First deploy has zero admins |
| (new) `argument_unvote` cross-conv | Data integrity bug |

### Fix before real community members use it

| Issue | Notes |
|---|---|
| #5 | Argument moderation — `moderate()` always errors; no way to hide abusive content |
| #12 | Gate arguments phase on at least one confirmed proposal |
| #24 | Move argument delete to moderator view |
| (new) Proxy DELETE restriction | Restrict to mods/admins |
| (new) `_is_emailable()` timeout | Hanging login = bad first impression |
| (new) Health check + monitoring | Add `/healthz` + UptimeRobot |
| (new) Backup cron error handling | Silent zero-byte dumps |

### Deferred (post-launch polish)

| Issue | Notes |
|---|---|
| #6 | Move approved statements back to pending |
| #7 | Admin audit panel |
| #10 | Arguments tab one-at-a-time navigation |
| #11 | Importance voting unlock messaging |
| (new) Rate limiter storage (Redis) | Single-worker for now; add before scaling |
| (new) `psycopg2` connection pooling | Admin paths only; low traffic initially |
| (new) `_generate_pseudonyms` N+1 queries | Performance, not correctness |
| (new) `_nullify_expired_reveals` error handling | Wrap in try/except |
| (new) `Query.get()` deprecation | SQLAlchemy 2.x warning only |
| #4 | Won't fix — pa-login-button incompatible with proxy architecture |

---

## Agents' disagreements (for reference)

| Finding | DevOps | Security | Senior dev | Decision |
|---------|--------|----------|------------|----------|
| Docker restart policy | PRE | PRE | POST (overcalled) | **PRE** — VM reboots happen |
| Rate limiter per-worker | POST | PRE | POST | **POST** — Toolforge is single-worker; revisit if replicas added |
| `_is_emailable()` blocking | PRE | PRE | POST | **PRE** — hanging login = bad impression |
| Proxy DELETE | POST | POST | PRE | **PRE** — Particiapi auth disabled, risk is real |
| `argument_vote_data` key casing | — | Not a bug (code consistent) | High | **Not a bug** — security agent confirmed both reads use `'K'` |

---

## Reference

- `v2/deployment.md` — full deployment runbook (fix bind address before using)
- `v2/cache/cloud-vps.md` — Wikimedia Cloud VPS reference
- `v2/next_steps.md` — detailed build history
