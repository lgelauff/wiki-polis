# wiki-polis

A deliberation tool for the Wikimedia community. Participants vote on atomic statements, opinion clusters emerge, and a curated argument layer can be added on top.

Hosted on [Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge) at `https://wiki-polis.toolforge.org`.

---

## Architecture

```
  Browser ──▶ Flask app (Toolforge)
               - Wikimedia OAuth (single login)
               - Conversation management, access policies, roles
               - Admin panel
               - Proxies voting calls to VPS
               - MariaDB (ToolsDB) — identity layer
                     │
                     ▼ internal proxy (xid only)
              Polis + Particiapi (VPS, Docker Compose)
               - Voting, statement routing, clustering
               - PostgreSQL — deliberation layer (pseudonymised)
```

The Flask app on Toolforge handles all authentication. The VPS runs stock Polis + Particiapi with authentication disabled — it is not publicly exposed. Flask proxies all voting calls to it, passing only the user's xid (SHA-256 of their Wikimedia user ID).

See `v2/architecture.md` for the full design.

---

## How it works

1. Users log in with their Wikimedia account (Wikimedia OAuth 2.0)
2. The home page shows conversations they have joined, can join, or moderate
3. Joining a conversation requires an explicit accept step (intro text + pseudonym selection)
4. The voting loop presents one statement at a time — agree, disagree, or pass — with an optional inline prompt to propose a better alternative
5. Admins control four independent phase toggles per conversation: submission open, personal results, argument mapping, and full public results
6. The argument mapping tab shows featured statements with short pro/con arguments, visible once the admin enables it

---

## v2 status

v2 is currently in development. The planning documents are in `v2/`:

| File | Purpose |
|---|---|
| `v2/functional_design.md` | Full product specification — what the platform does |
| `v2/architecture.md` | Technical architecture and data model |
| `v2/design_principles.md` | Stable design rules |
| `v2/next_steps.md` | Implementation roadmap |

The current live deployment runs on the v1 codebase (see below).

---

## Local development (v1, currently deployed)

### Prerequisites

- [UV](https://docs.astral.sh/uv/) for Python dependency management
- Python 3.11 or later

### Setup

```bash
git clone https://github.com/lgelauff/wiki-polis
cd wiki-polis
uv sync
```

Create a `.env` file (never commit this):

```bash
cp .env.example .env
```

Edit `.env` with your values:

```
OAUTH_CLIENT_ID=your_client_id
OAUTH_CLIENT_SECRET=your_client_secret
OAUTH_REDIRECT_URI=http://127.0.0.1:5000/oauth-callback
SECRET_KEY=any-random-string-for-local-dev
ADMIN_USERS=YourWikimediaUsername
```

> **Note:** The OAuth consumer is registered for the Toolforge callback URL, so the full OAuth flow won't work locally. Use the dev-login bypass instead (see below).

### Running the app

```bash
FLASK_DEBUG=1 uv run python app.py
```

Visit `http://127.0.0.1:5000` (not `localhost` — use `127.0.0.1`).

### Dev login (bypass OAuth)

With `FLASK_DEBUG=1`, a dev login bypass is available that skips OAuth entirely:

```
http://127.0.0.1:5000/dev-login?username=YourWikimediaName
```

This creates a participant record and sets your session directly. Use your real Wikimedia username to test admin access (must match `ADMIN_USERS`).

### Database

By default, a local SQLite database (`instance/dev.db`) is used. No setup needed — it is created automatically on first run.

---

## Deployment (Toolforge)

This is a one-time setup. For routine updates after the initial deploy, see [Updating](#updating).

### 1. Register the tool

Register at https://toolsadmin.wikimedia.org with tool name `wiki-polis`.

### 2. Register OAuth consumer

Register at https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration with:
- Callback URL: `https://wiki-polis.toolforge.org/oauth-callback`
- Grants: identify only

### 3. SSH into Toolforge and install uv

```bash
ssh login.toolforge.org
become wiki-polis
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

> Add `source $HOME/.local/bin/env` to your `~/.bashrc` so uv is available in future sessions.

### 4. Clone the repository

```bash
git clone https://github.com/lgelauff/wiki-polis ~/wiki-polis
```

### 5. Create the database

Read your replica credentials:

```bash
cat ~/replica.my.cnf
```

Connect to ToolsDB and create the database:

```bash
mariadb --defaults-file=$HOME/replica.my.cnf -h tools.db.svc.wikimedia.cloud
```

```sql
CREATE DATABASE `s57499__wiki-polis`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
EXIT;
```

> The database name **must** start with your tools prefix (e.g. `s57499__`). Check your prefix in `~/replica.my.cnf`.

### 6. Set secrets

```bash
toolforge envvars create OAUTH_CLIENT_ID "YOUR_CLIENT_ID"
toolforge envvars create OAUTH_CLIENT_SECRET "YOUR_CLIENT_SECRET"
toolforge envvars create OAUTH_REDIRECT_URI "https://wiki-polis.toolforge.org/oauth-callback"
toolforge envvars create SECRET_KEY "YOUR_RANDOM_SECRET_KEY"
toolforge envvars create ADMIN_USERS "Username1,Username2"
toolforge envvars create DATABASE_URL "mysql+pymysql://USER:PASSWORD@tools.db.svc.wikimedia.cloud/s57499__wiki-polis"  # pragma: allowlist secret
```

### 7. Set up the web service directory

```bash
mkdir -p ~/www/python
ln -s ~/wiki-polis ~/www/python/src
```

Then open a webservice shell to create the venv:

```bash
toolforge webservice python3.13 shell
```

Inside the shell:

```bash
python3 -m venv ~/www/python/venv
~/www/python/venv/bin/pip install -e ~/wiki-polis
exit
```

### 8. Start the web service

```bash
cd ~
toolforge webservice --backend=kubernetes python3.13 start
```

### Updating

```bash
bash ~/wiki-polis/deploy.sh
```

The deploy script runs `git pull`, reinstalls dependencies, and restarts the web service.

---

## Project structure

```
wiki-polis/
  app.py          — Flask app, OAuth flow, routes
  db.py           — SQLAlchemy models
  wsgi.py         — WSGI entry point
  uwsgi.ini       — uWSGI config
  deploy.sh       — Toolforge deploy script
  pyproject.toml  — Dependencies (managed with UV)
  templates/      — Jinja2 templates
  static/         — CSS
  v2/             — Planning documents for the next version
```
