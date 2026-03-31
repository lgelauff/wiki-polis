# wiki-polis

A lightweight Wikimedia community consultation tool. Wraps a [Polis](https://pol.is) conversation behind MediaWiki OAuth, with a custom landing page, acceptance flow, and notification preferences.

Hosted on [Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge) at `https://wiki-polis.toolforge.org`.

---

## How it works

1. Users log in with their Wikimedia account (MediaWiki OAuth 2.0)
2. They are shown active consultations they haven't joined yet
3. On joining, they set notification preferences (email / talk page)
4. The Polis embed handles proposal submission, voting, and consensus math
5. Admins manage conversations and participants via `/admin`

---

## Local development

### Prerequisites

- [UV](https://docs.astral.sh/uv/) for Python dependency management
- Python 3.11

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

This creates a participant record and sets your session directly. Use your real Wikimedia username to test admin access (must match `ADMIN_USERS` in `app.py`).

### Database

By default, a local SQLite database (`instance/dev.db`) is used. No setup needed — it's created automatically on first run.

To inspect it:

```bash
uv run python -c "from app import app; from db import db; app.app_context().push(); from db import *"
```

Or use any SQLite browser pointed at `instance/dev.db`.

### Setting up a test conversation

1. Log in via dev-login
2. Visit `http://127.0.0.1:5000/admin`
3. Create a conversation with a Polis conversation ID (e.g. from [pol.is](https://pol.is))
4. Visit `http://127.0.0.1:5000` to see it on the landing page

---

## Configuration

Edit the config block at the top of `app.py`:

```python
TOOL_NAME  = "wiki-polis"              # Toolforge tool name
EVENT_NAME = "Community Consultation"  # Shown in the header
```

Admin usernames are never hardcoded. Set them via secret/env:
- **Locally:** `ADMIN_USERS=Username1,Username2` in `.env`
- **Toolforge:** `toolforge secrets create wiki-polis-admin-users --from-literal=value=Username1,Username2`

Conversations (Polis ID, title, intro/outro text) are managed via the admin UI — no code changes needed.

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
cd ~/wiki-polis
uv sync
```

### 5. Create the database

Read your replica credentials:

```bash
cat ~/replica.my.cnf
```

Copy the `user` and `password` values locally — you will need them for the database URL secret.

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
toolforge envvars create DATABASE_URL "mysql+pymysql://USER:PASSWORD@tools.db.svc.wikimedia.cloud/s57499__wiki-polis"
```

> `toolforge envvars list` masks values after creation — keep a local record of your secrets.

### 7. Set up the web service directory

Toolforge expects `~/www/python/` to be a **real directory** (not a symlink). Create it and symlink the repo as `src`:

```bash
mkdir -p ~/www/python
ln -s ~/wiki-polis ~/www/python/src
```

Then open a webservice shell to create the venv — **the venv must be created inside the webservice container**, not on the bastion, or it will not work:

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

Run from your **home directory** — webservice commands fail silently when run from inside the repo:

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
  app.py          — Flask app, OAuth flow, routes, config block at top
  db.py           — SQLAlchemy models (Participant, Conversation, Participation)
  wsgi.py         — WSGI entry point
  pyproject.toml  — Dependencies (managed with UV)
  templates/
    base.html     — Header with event name, username, logout, admin links
    landing.html  — Lists open and accepted consultations
    accept.html   — Acceptance screen with notification preferences
    index.html    — Polis embed with intro/outro text
    admin.html    — Conversation management and participant list
  static/
    style.css     — Polis-inspired styling
```

---

## Analysis

Polis handles clustering and consensus math internally. To analyse results:

1. Export conversation data from pol.is (votes.csv, comments.csv, participants-votes.csv)
2. Join the `xid` column in the export with the local `participants` table to recover Wikimedia usernames
3. Run further analysis in Python as needed
