# Deployment Guide

wiki-polis v2 runs as two separate services:

```
Browser → Toolforge (wiki-polis Flask app) → Cloud VPS (Particiapi + Polis + Postgres)
               ↑ Wikimedia OAuth                      ↑ internal only, not public
```

- **Toolforge** hosts the Flask app at `wiki-polis.toolforge.org`
- **Cloud VPS** (WMCS or any ~$6/mo VPS) runs the Particiapi/Polis Docker stack
- Particiapi is never exposed publicly — Flask proxies to it over the internal network

---

## Part 1 — Cloud VPS: Particiapi + Polis backend

### Server requirements

| | Minimum | Recommended |
|---|---|---|
| **CPU** | 2 vCPU | 4 vCPU |
| **RAM** | 4 GB | 8 GB |
| **Disk** | 20 GB SSD | 40 GB SSD |
| **OS** | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| **Docker** | 24+ | latest |
| **Network** | Outbound internet | + static IP or hostname |

Polis (Node.js) and Particiapi (Python/Flask) each run as Docker containers alongside PostgreSQL. The 4 GB minimum is tight — allocate swap if RAM is limited.

The VPS does **not** need a public-facing port for Particiapi. Only the Flask app on Toolforge needs to reach it (port 8000), so a firewall rule allowing only Toolforge's egress IPs is sufficient.

### Provision

Request a WMCS Cloud VPS project at https://horizon.wikimedia.org, or use any VPS provider. A small instance (2 vCPU, 4 GB RAM) is enough for a pilot.

### Install Docker

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER && newgrp docker
```

### Deploy particiapp-docker

```bash
git clone --recurse-submodules \
  https://gitlab.wikimedia.org/repos/tool-labs/particiapp/particiapp-docker.git
cd particiapp-docker
cp .env.example .env
```

Edit `.env`:

```
PARTICIAPI_AUTHENTICATION_DISABLED=True
POSTGRES_PASSWORD=<strong-random-password>
SECRET_KEY=<strong-random-secret>
```

Bind Particiapi to localhost only — add to `docker-compose.yml` under the `particiapi` service:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

Start the stack:

```bash
docker compose up -d
curl http://127.0.0.1:8000/api/conversations/   # should return []
```

### Backups

Set up a daily `pg_dump` to WMCS Object Storage (Swift) or any offsite location:

```bash
# Example cron (adjust credentials and bucket name)
0 3 * * * docker exec particiapp-docker-db-1 \
  pg_dump -U postgres particiapp | gzip > /backup/particiapp-$(date +\%F).sql.gz
```

---

## Part 2 — Toolforge: Flask app

### Requirements

Toolforge is a managed Kubernetes platform — you do not provision a server. What you need:

- A **Wikimedia developer account**: https://developer.wikimedia.org
- A **Toolforge tool account** named `wiki-polis` (created via `toolforge tools create wiki-polis`)
- A **ToolsDB database** (MySQL/MariaDB, provisioned via `sql tools` on the bastion)
- A **registered Wikimedia OAuth consumer** for the callback URL (approved by Wikimedia; can take a few days)
- Python **3.13** webservice (available by default on Toolforge; no installation needed)

You do **not** need to install Python, uWSGI, or a web server — Toolforge provides all of that. You only manage the app code, venv, and secrets.

### One-time tool setup

SSH to `login.toolforge.org`, then:

```bash
toolforge tools create wiki-polis
become wiki-polis

# Clone repo
git clone https://github.com/lgelauff/wiki-polis.git ~/wiki-polis

# ~/www/python must be a real directory (not a symlink to the repo)
mkdir -p ~/www/python
ln -s ~/wiki-polis/v2 ~/www/python/src
```

### Install Python dependencies

Dependencies must be installed **inside the webservice shell** — a venv created on the bastion won't work with uWSGI:

```bash
toolforge webservice python3.13 shell
python3 -m venv ~/www/python/venv
~/www/python/venv/bin/pip install -e ~/wiki-polis/v2
exit
```

### Add uwsgi.ini

Wikimedia OAuth tokens exceed uWSGI's default 4 KB header buffer, causing silent failures. Create `wiki-polis/v2/uwsgi.ini`:

```ini
buffer-size = 65536
```

Toolforge picks this up automatically from `~/www/python/src/uwsgi.ini`.

### Set secrets

```bash
toolforge envvars create SECRET_KEY            "your-strong-secret"
toolforge envvars create OAUTH_CLIENT_ID       "your-oauth-client-id"
toolforge envvars create OAUTH_CLIENT_SECRET   "your-oauth-secret"
toolforge envvars create OAUTH_REDIRECT_URI    "https://wiki-polis.toolforge.org/oauth-callback"
toolforge envvars create PARTICIAPI_BASE_URL   "http://<vps-internal-ip>:8000"
toolforge envvars create DATABASE_URL          "mysql+pymysql://s_wiki_polis:<password>@tools.db.svc.wikimedia.cloud/s_wiki_polis__main"
```

> `toolforge envvars list` shows names only, not values. Keep a local record.

The app reads secrets from env vars via `_read_secret()` in `app.py`. On Kubernetes it also checks `/run/secrets/wiki-polis/<name>` first, so either mechanism works.

### Create ToolsDB database

```bash
sql tools   # opens MySQL as your tool user
CREATE DATABASE s_wiki_polis__main CHARACTER SET utf8;
exit
```

### Register Wikimedia OAuth application

Go to https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration and register a consumer:

- **Callback URL:** `https://wiki-polis.toolforge.org/oauth-callback`
- **Grants:** Basic rights, confirm email address

Fill in `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, and `OAUTH_REDIRECT_URI` envvars above once approved.

### Initialise database and start

```bash
cd ~   # webservice commands must run from home directory
toolforge webservice python3.13 start

# Run once to create tables
flask --app ~/wiki-polis/v2/app.py init-db
```

### Verify

```
https://wiki-polis.toolforge.org/          → home page (login prompt)
https://wiki-polis.toolforge.org/login     → redirects to Wikimedia OAuth
```

---

## Ongoing deploys

```bash
# On Toolforge as wiki-polis user:
cd ~/wiki-polis && git pull
~/www/python/venv/bin/pip install -e ~/wiki-polis/v2
cd ~ && webservice restart
```

---

## Toolforge gotchas

| Issue | Fix |
|---|---|
| `pip install` breaks uWSGI | Always install inside `toolforge webservice python3.13 shell` |
| OAuth callback fails silently | `uwsgi.ini` with `buffer-size = 65536` is required |
| `webservice restart` fails | Must run from `~`, not from inside the repo |
| No SQLite CLI on Toolforge | Use `python3 -c 'import sqlite3; ...'` if needed |
| Replica DBs unavailable locally | `get_polis_stats()` already handles missing `POLIS_DATABASE_URL` gracefully |
| "lseek: Illegal seek" in logs | uWSGI stdout rotation noise — safe to ignore |

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | yes | Flask session signing key |
| `OAUTH_CLIENT_ID` | yes (prod) | Wikimedia OAuth consumer key |
| `OAUTH_CLIENT_SECRET` | yes (prod) | Wikimedia OAuth consumer secret |
| `OAUTH_REDIRECT_URI` | yes (prod) | Must match registered callback URL |
| `PARTICIAPI_BASE_URL` | yes | Internal URL of Particiapi (e.g. `http://10.x.x.x:8000`) |
| `DATABASE_URL` | yes (prod) | SQLAlchemy DB URL; defaults to `sqlite:///dev.db` |
| `POLIS_DATABASE_URL` | no | Direct Postgres connection for admin stats panel; leave blank to disable |
| `POLIS_PUBLIC_URL` | no | Public Polis URL for "view full results" links |
| `DEV_LOGIN_USER` | dev only | Bypasses OAuth in local dev; never set in production |
| `FLASK_DEBUG` | dev only | Enables debug mode; never set in production |
