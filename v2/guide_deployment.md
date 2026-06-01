# Deployment Guide

wiki-polis v2 runs as two separate services:

```
Browser → Toolforge (wiki-polis Flask app) → Cloud VPS (Particiapi + Polis + Postgres)
               ↑ Wikimedia OAuth                      ↑ internal only, not public
```

- **Toolforge** hosts the Flask app at `wiki-polis.toolforge.org`
- **Cloud VPS** (WMCS or any ~$6/mo VPS) runs the Particiapi/Polis Docker stack
- Particiapi is never exposed publicly — Flask proxies to it over the internal network

> This guide covers **first-time provisioning**. For day-2 operations (monitoring,
> backups/restore, logs, staging, secrets rotation, outages), see the operator runbook:
> [`guide_runbook.md`](guide_runbook.md).

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

#### Provisioning in WMCS Horizon (step by step)

1. Go to https://horizon.wikimedia.org and select your project (e.g. `wiki-polis-backend`)
2. **Launch instance**: Compute → Instances → Launch Instance
   - **Instance Name**: `wiki-polis-backend`
   - **Description**: `wiki-polis Particiapi/Polis backend` (optional but useful)
   - **Source**: `Debian 12 Bookworm` (do not use Debian 13 Trixie — still testing; avoid Fedora, CoreOS, Magnum)
   - **Flavor**: `g4.cores2.ram4.disk20` (2 vCPU, 4 GB RAM, 20 GB disk)
   - **Networks / Network Ports / Security Groups / Configuration / Server Groups / Scheduler Hints / Metadata**: leave all as default
   - **Key Pair**: leave as default (WMCS managed instances use LDAP, not Horizon keys — see SSH section below)
3. **Note the private IP**: shown in Compute → Instances. This is the internal OpenStack IP used for Toolforge → Particiapi traffic. It is fixed for the lifetime of the instance.

> **Floating IP**: WMCS quotas are limited. A floating IP is not needed — use the ProxyJump config below instead.

#### Security group (after Docker stack is running)

In Horizon → Network → Security Groups → **Manage Rules** on the default group → **Add Rule** (repeat for each rule below):

| Port | Purpose | CIDR | Description |
|---|---|---|---|
| 8000 | Particiapi — participant voting | `172.16.0.0/17` | Allow Toolforge pods to reach Particiapi |
| 8001 | Polis server — conversation creation | `172.16.0.0/17` | Allow Toolforge pods to create Polis conversations |
| 5432 | Postgres — admin stats | `172.16.0.0/17` | Allow Toolforge pods to query Polis DB directly (needed for moderation view) |

`172.16.0.0/17` covers all WMCS internal traffic (Toolforge workers, Cloud VPS instances). The full Toolforge worker list is at `https://tools-static.wmflabs.org/admin/meta/worker-ips.json` — 77 individual IPs, too many for per-IP rules.

> **Port 8001 surface:** port 8001 exposes the Polis HTTP API. The CIDR restricts it to Toolforge pods. Protect further with `POLIS_ADMIN_PASSWORD` strength and by not exposing the Polis admin UI to the public internet.

> **Note:** Instance snapshots are blocked by WMCS policy (`os_compute_api:servers:create_image` — HTTP 403). Use pg_dump for backups instead.

#### SSH key setup (one-time)

WMCS Cloud VPS instances use **LDAP-managed SSH keys**, not Horizon Key Pairs. You must upload your public key to the Wikimedia Identity Management system:

1. Go to https://idm.wikimedia.org/keymanagement/ and upload your public key (`~/.ssh/<your-vps-key>.pub`)
2. Your SSH username is the **"SSH access (shell) username"** shown at idm.wikimedia.org — note it down

#### SSH config

Add to `~/.ssh/config` on your local machine:

```
Host wiki-polis-vps
    HostName wiki-polis-backend.wiki-polis-backend.eqiad1.wikimedia.cloud
    User <your-shell-username>
    IdentityFile ~/.ssh/<your-vps-key>
    ProxyJump <your-shell-username>@bastion.wmcloud.org
```

Then connect with:

```bash
ssh wiki-polis-vps
```

On first connect, accept the host fingerprint prompt — SSH will save it to `~/.ssh/known_hosts` for future verification. The fingerprint itself is safe to store.

### Install Docker

```bash
sudo apt update && sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER && newgrp docker
sudo systemctl enable docker
```

> Note: Debian 12 repos provide `docker-compose` (standalone v1) and `docker.io` as separate packages. `docker-compose-plugin` is not available. Use `docker-compose` (with hyphen) instead of `docker compose` (with space).

### Deploy particiapp-docker

```bash
git clone --recurse-submodules \
  https://gitlab.com/particiapp/particiapp-docker.git
cd particiapp-docker
cp env .env
mkdir -p ~/particiapp-data/postgresql-data ~/particiapp-data/postgres-backups
nano .env
```

Set these values in `.env` (replace `<private-ip>` with the VM's internal IP from `hostname -I`):

```
DATA_DIR=/home/<your-username>/particiapp-data
PARTICIAPI_DIR=/home/<your-username>/particiapp-docker
POSTGRES_PASSWORD=<strong-random-password>
POLIS_SERVER_NAME=polis.internal
PARTICIAPI_HOSTNAME=particiapi
PARTICIAPI_DOMAINNAME=internal
PARTICIAPI_SECRET_KEY=<strong-random-secret>
PARTICIAPI_CORS_ORIGINS=https://wiki-polis.toolforge.org
PARTICIAPI_IDP_API_BASE_URL=
PARTICIAPI_IDP_CLIENT_ID=
PARTICIAPI_IDP_CLIENT_SECRET=
PARTICIAPI_AUTHENTICATION_DISABLED=True
BIND_ADDRESS=<private-ip>
```

Notes:
- `DATA_DIR` — persistent postgres data; survives container restarts
- `PARTICIAPI_DIR` — the cloned repo root (needed for the schema.sql submodule)
- `BIND_ADDRESS` — private IP only; do **not** use `0.0.0.0`
- IDP fields can be left empty when `PARTICIAPI_AUTHENTICATION_DISABLED=True`
- `restart: always` is already set on all services — do not modify it
- The container-internal Particiapi port is 5000, mapped to host port 8000

**Expose Postgres to Toolforge** (required for the admin moderation view): in `docker-compose.yaml`, add a `ports` entry to the `postgres` service:

```yaml
ports:
  - "<private-ip>:5432:5432"
```

This binds Postgres only to the private IP, not publicly.

Pre-seed the Polis schema volume before first start:

```bash
docker run --rm -v particiapp-docker_polis-schemas:/data \
  registry.gitlab.com/particiapp/polis/server:latest \
  cp -r /app/postgres/migrations/. /data/
```

> The volume name uses the compose project name as prefix. With no `-p` flag the project defaults to the directory name (`particiapp-docker`), giving `particiapp-docker_polis-schemas`.

Start the stack:

```bash
docker-compose up -d
docker ps   # all 5 services should show (healthy) or Up
```

**Run Polis migrations manually** — polis-server does not auto-apply schema migrations on a fresh database. After the stack is up, copy the migration files into the postgres container and run them:

```bash
docker create --name tmp-migrations -v particiapp-docker_polis-schemas:/migrations alpine
docker cp tmp-migrations:/migrations /tmp/polis-migrations
docker rm tmp-migrations
docker cp /tmp/polis-migrations particiapp-docker_postgres_1:/tmp/polis-migrations
docker exec particiapp-docker_postgres_1 \
  sh -c 'for f in $(ls /tmp/polis-migrations/0*.sql | sort); do echo "$f"; psql -U polis polis -f "$f"; done'
```

Then restart polis-server:

```bash
docker-compose restart polis-server
docker ps   # polis-server should show (healthy) within ~30 seconds
```

Health check:

```bash
curl -s -o /dev/null -w "%{http_code}" http://<private-ip>:8000/
# returns 200 when particiapi is up
```

> Note: uses `docker-compose` (v1 hyphen) as installed on Debian 12. If v2 plugin is available, use `docker compose` instead.

> **Postgres data directory permissions:** Docker runs postgres as an internal user, so `~/particiapp-data/postgresql-data/` will be owned by that user, not by you. If you ever need to delete it (e.g. to re-initialise the database), use `sudo rm -rf ~/particiapp-data/postgresql-data/`.

### Security hardening (one-time, after stack is running)

**Tighten `.env` permissions:**
```bash
chmod 600 ~/particiapp-docker/.env
```

**Create a read-only Postgres role** for the Flask admin connection — do not use the `polis` superuser for external connections:

```bash
docker exec -it particiapp-docker_postgres_1 psql -U polis polis -c "CREATE ROLE wiki_polis_ro WITH LOGIN PASSWORD '<strong-password>'; GRANT CONNECT ON DATABASE polis TO wiki_polis_ro; GRANT USAGE ON SCHEMA public TO wiki_polis_ro; GRANT SELECT ON ALL TABLES IN SCHEMA public TO wiki_polis_ro; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO wiki_polis_ro;"
```

Use this role in the `POLIS_DATABASE_URL` Toolforge envvar: `postgresql://wiki_polis_ro:<password>@<private-ip>:5432/polis`

### Polis system account (one-time)

The wiki-polis admin panel creates Polis conversations by calling the Polis API at port 8001. This requires a dedicated Polis user account. Create it once on the VPS:

```bash
# SSH to VPS, then:
curl -s -X POST http://localhost:8001/api/v3/auth/new \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "wiki-polis-system@internal.invalid",
    "password": "<strong-random-password>",
    "hname": "wiki-polis system",
    "gatekeeperTosPrivacy": true
  }'
```

A successful response returns JSON with a `uid`. Store the email and password in your password manager — they go into the `POLIS_ADMIN_EMAIL` and `POLIS_ADMIN_PASSWORD` Toolforge env vars.

> **If Polis replies "Please use HTTPS":** the port is bound to the private IP, not loopback, so add `-H 'X-Forwarded-Proto: https'` to the curl command.

### Backups

Set up a daily `pg_dump` to WMCS Object Storage (Swift) or any offsite location:

```bash
# Example cron (adjust credentials and bucket name)
0 3 * * * docker exec $(docker ps --filter name=postgres --format '{{.Names}}' | head -1) \
  pg_dump -U polis polis | gzip > /backup/polis-$(date +\%F).sql.gz
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
source ~/www/python/venv/bin/activate
pip install -e ~/wiki-polis/v2
exit
```

### Add uwsgi.ini

Wikimedia OAuth tokens exceed uWSGI's default 4 KB header buffer, causing silent failures. Create `~/www/python/uwsgi.ini`:

```bash
printf '[uwsgi]\nbuffer-size = 65536\n' > ~/www/python/uwsgi.ini
```

Toolforge picks this up from `~/www/python/uwsgi.ini` — this is the required location. The `[uwsgi]` section header is mandatory; without it uWSGI silently ignores the file and uses its 4 KB default.

### Set secrets

**Do not pass secret values as CLI arguments** — they are logged to shell history and visible to other bastion users. Use the interactive prompt instead (input is hidden):

```bash
toolforge envvars create SECRET_KEY
toolforge envvars create OAUTH_CLIENT_ID
toolforge envvars create OAUTH_CLIENT_SECRET
toolforge envvars create PARTICIAPI_BASE_URL
toolforge envvars create DATABASE_URL
toolforge envvars create ADMIN_USERS
toolforge envvars create POLIS_SERVER_URL
toolforge envvars create POLIS_ADMIN_EMAIL
toolforge envvars create POLIS_ADMIN_PASSWORD
toolforge envvars create POLIS_DATABASE_URL
```

Non-secret values can be passed as arguments:

```bash
toolforge envvars create OAUTH_REDIRECT_URI 'https://wiki-polis.toolforge.org/oauth-callback'
```

Values to enter at the prompts:
- `SECRET_KEY` — your strong random secret
- `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` — from OAuth registration
- `PARTICIAPI_BASE_URL` — `http://<vps-private-ip>:8000`
- `DATABASE_URL` — `mysql+pymysql://<creduser>:<password>@tools.db.svc.wikimedia.cloud/<creduser>__wiki-polis?charset=utf8mb4` (see ToolsDB step below for `<creduser>`)
- `ADMIN_USERS` — your Wikimedia username, exact capitalisation (e.g. `YourUsername`)
- `POLIS_SERVER_URL` — `http://<vps-private-ip>:8001` (Polis server, for conversation creation)
- `POLIS_ADMIN_EMAIL` — email of the Polis system account (see Polis system account step below)
- `POLIS_ADMIN_PASSWORD` — password of the Polis system account
- `POLIS_DATABASE_URL` — `postgresql://wiki_polis_ro:<password>@<vps-private-ip>:5432/polis` — use the password set when creating the `wiki_polis_ro` role (see Security hardening step above); do not use the `polis` superuser here

> `toolforge envvars list` shows names only, not values. Keep a local record.

> `toolforge envvars` has no `update` command — to change a value, delete and recreate: `toolforge envvars delete <NAME>` then `toolforge envvars create <NAME>`.

The app reads secrets from env vars via `_read_secret()` in `app.py`. On Kubernetes it also checks `/run/secrets/wiki-polis/<name>` first, so either mechanism works.

### Create ToolsDB database

```bash
sql tools   # opens MySQL as your tool user
SELECT SUBSTRING_INDEX(CURRENT_USER(), '@', 1);   -- note this value, it's your <creduser>
CREATE DATABASE `<creduser>__wiki-polis` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
exit
```

The database name must use the exact credential username shown by `CURRENT_USER()` — you cannot choose it freely. It will be a numeric ID like `s11111` (not a tool name). Use this same value in the `DATABASE_URL` envvar above.

### Register Wikimedia OAuth application

Go to https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration and register a consumer:

- **Callback URL:** `https://wiki-polis.toolforge.org/oauth-callback`
- **Grants:** Basic rights, confirm email address

Fill in `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, and `OAUTH_REDIRECT_URI` envvars above once approved.

### Initialise database and start

```bash
# init-db must run inside the webservice shell — envvars are not available on the bastion
toolforge webservice python3.13 shell
source ~/www/python/venv/bin/activate
cd ~/wiki-polis/v2
flask --app app.py init-db
exit

# start from the bastion
cd ~   # webservice commands must run from home directory
toolforge webservice python3.13 start
```

### Verify

```
https://wiki-polis.toolforge.org/          → home page (login prompt)
https://wiki-polis.toolforge.org/login     → redirects to Wikimedia OAuth
```

---

## Ongoing deploys

```bash
# On Toolforge bastion as wiki-polis user:
cd ~/wiki-polis && git pull
pip install -e ~/wiki-polis/v2   # skip if no new dependencies
```

If the deploy includes database migrations, run them **before** restarting (see [Database migrations](#database-migrations) below).

```bash
cd ~   # webservice commands must run from home directory
toolforge webservice restart
```

Or use the deploy script (which handles all steps):

```bash
bash ~/wiki-polis/deploy.sh
```

---

## Database migrations

Alembic migrations must run inside `toolforge webservice python3.13 shell` — **not** on the bastion shell. The reason: `toolforge envvars` (including `DATABASE_URL`) are only injected into the webservice pod environment, not exported to regular bastion sessions. Running `flask db upgrade` on the bastion will fail with `RuntimeError: DATABASE_URL is not set`.

### Check whether a migration is needed

After `git pull`, check if the new commits added any migration files:

```bash
ls ~/wiki-polis/v2/migrations/versions/
```

If there are new files since the last deploy, run the migration steps below before restarting.

### Run migrations

```bash
# Step 1 — enter the webservice shell (envvars are available here)
toolforge webservice python3.13 shell

# Step 2 — activate the venv (flask is not on PATH by default)
source /data/project/wiki-polis/www/python/venv/bin/activate

# Step 3 — run the migration from the app directory
cd ~/wiki-polis/v2
flask --app app db upgrade

# Step 4 — exit the webservice shell
exit
```

Expected output:

```
INFO  [alembic.runtime.migration] Context impl MySQLImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade <prev> -> <new>, <description>
```

No output after "Will assume non-transactional DDL." means the database is already up to date.

### After migration — restart the webservice

Run this from the **bastion** (not inside the webservice shell):

```bash
cd ~
toolforge webservice restart
```

### Verify

Check the live app returns 200, then inspect the log for errors:

```bash
tail -50 /data/project/wiki-polis/uwsgi.log | grep -v lseek
```

### If something goes wrong — rollback

To undo the last migration:

```bash
toolforge webservice python3.13 shell
source /data/project/wiki-polis/www/python/venv/bin/activate
cd ~/wiki-polis/v2
flask --app app db downgrade   # rolls back one step
exit
```

Then revert the code change and restart.

### Toolforge gotchas specific to migrations

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: DATABASE_URL is not set` | Running `flask` on the bastion shell without exporting envvars | Use `deploy.sh --migrate`, or export manually (see below) |
| `flask: command not found` | Venv not activated | `source /data/project/wiki-polis/www/python/venv/bin/activate` |
| `Error: No such command 'db'` | Wrong working directory or FLASK_APP not set | `cd ~/wiki-polis/v2` first, then `flask --app app db upgrade` |
| `No such file or directory: .../activate` | Wrong venv path | Run `find /data/project/wiki-polis -name activate -path "*/venv/*"` to find the real path |

### Exporting envvars manually

`toolforge envvars show <NAME>` outputs a two-column table, not a raw value:

```
name        value
SECRET_KEY  <value>
```

To export an envvar to the shell:

```bash
export SECRET_KEY=$(toolforge envvars show SECRET_KEY | tail -1 | awk '{print $NF}')
```

`deploy.sh --migrate` does this automatically for `DATABASE_URL`, `SECRET_KEY`, and `PARTICIAPI_BASE_URL`.

---

## Toolforge gotchas

| Issue | Fix |
|---|---|
| `pip install` breaks uWSGI | Always install inside `toolforge webservice python3.13 shell` |
| OAuth callback fails silently | `uwsgi.ini` must have `[uwsgi]` section header + `buffer-size = 65536`; without the header uWSGI ignores the file |
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
| `POLIS_SERVER_URL` | yes | Direct Polis server URL (e.g. `http://10.x.x.x:8001`) — required for conversation creation |
| `POLIS_ADMIN_EMAIL` | yes | Email of the Polis system account (created once on VPS) |
| `POLIS_ADMIN_PASSWORD` | yes | Password of the Polis system account |
| `POLIS_DATABASE_URL` | no | Direct Postgres connection for admin stats panel; leave blank to disable |
| `POLIS_PUBLIC_URL` | no | Public Polis URL for "view full results" links |
| `DEV_LOGIN_USER` | dev only | Bypasses OAuth in local dev; never set in production |
| `DEV_FAKE_LOGIN` | dev only | Set to `1` to show hardcoded test-user badges on the home page; never set in production |
| `FLASK_DEBUG` | dev only | Enables debug mode; never set in production |
