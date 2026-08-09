# wiki-polis

A deliberation tool for the Wikimedia community. Participants vote on atomic statements, opinion clusters emerge, and a curated argument layer can be added on top.

Hosted on [Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge) at `https://wiki-polis.toolforge.org`.

---

## Architecture

```
  Browser ──▶ Flask app (Toolforge)
               - Wikimedia OAuth (single login)
               - Conversation management, access policies, roles
               - Proxies voting calls to VPS
               - MariaDB (ToolsDB) — identity layer
                     │
                     ▼ internal proxy (xid only)
              Polis + Particiapi (VPS, Docker Compose)
               - Voting, statement routing, clustering
               - PostgreSQL — deliberation layer (pseudonymised)
```

---

## Directories

| Directory | Contents |
|---|---|
| `v2/` | **The live application** — Flask app, models, templates, tests, and v2 docs |
| `v2/reference/` | Reference notes on the Particiapi API |
| `guidance/` | Organizer and participant guides, plus statement-writing help |
| `docs/` | Documentation index (`docs/README.md`) and background research syntheses |

---

## Project structure

```
wiki-polis/
  wsgi.py         — WSGI entry point (loads the v2 app)
  deploy.sh       — Toolforge deploy script (deploys v2)
  v2/             — the live application: Flask app, models, templates, tests, docs
  guidance/       — organizer & participant guides, statement-writing help
  docs/           — documentation index (docs/README.md) + research syntheses
  app.py, db.py, templates/, static/  — legacy pre-v2 app code, superseded by v2/ (not deployed)
```
