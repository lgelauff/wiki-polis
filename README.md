# wiki-polis

A deliberation tool for the Wikimedia community. Participants vote on atomic statements, opinion clusters emerge, and a curated argument layer can be added on top.

Hosted on [Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge) at `https://wiki-polis.toolforge.org`.

---

## Architecture (v2, in development)

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
| `v1/` | Current live deployment — local dev and Toolforge deployment docs |
| `v2/` | v2 planning: architecture, functional design, data model, roadmap |
| `v2/reference/` | Reference notes on Particiapi API and web components |

---

## Project structure

```
wiki-polis/
  app.py          — Flask app (v1, live)
  db.py           — SQLAlchemy models (v1)
  wsgi.py         — WSGI entry point
  uwsgi.ini       — uWSGI config
  deploy.sh       — Toolforge deploy script
  pyproject.toml  — Dependencies (UV)
  templates/      — Jinja2 templates
  static/         — CSS
  v1/             — v1 docs
  v2/             — v2 planning docs
```
