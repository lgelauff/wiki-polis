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

### 1. Register the tool

Register at https://toolsadmin.wikimedia.org with tool name `wiki-polis`.

### 2. Register OAuth consumer

Register at https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration with:
- Callback URL: `https://wiki-polis.toolforge.org/oauth-callback`
- Grants: identify only

### 3. Set secrets

From the Toolforge shell:

```bash
toolforge secrets create wiki-polis-oauth-client-id --from-literal=value=YOUR_CLIENT_ID
toolforge secrets create wiki-polis-oauth-client-secret --from-literal=value=YOUR_CLIENT_SECRET
toolforge secrets create wiki-polis-oauth-redirect-uri --from-literal=value=https://wiki-polis.toolforge.org/oauth-callback
toolforge secrets create wiki-polis-secret-key --from-literal=value=YOUR_RANDOM_SECRET_KEY
toolforge secrets create wiki-polis-admin-users --from-literal=value=Username1,Username2
toolforge secrets create wiki-polis-database-url --from-literal=value=mysql+pymysql://...
```

### 4. Deploy

```bash
toolforge webservice --backend=kubernetes python3.11 start
```

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
