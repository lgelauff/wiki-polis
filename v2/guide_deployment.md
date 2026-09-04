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

**Clone the wiki-polis ops scripts** — the `docker exec` helper scripts referenced below (`v2/ops/*.sh`) live in the wiki-polis repo itself, not in `particiapp-docker`. This VPS needs its own checkout:

```bash
git clone https://github.com/lgelauff/wiki-polis.git ~/wiki-polis
```

Run `cd ~/wiki-polis && git pull` after future deploys to pick up ops-script changes.

**Create a read-only Postgres role** for the Flask admin connection — do not use the `polis` superuser for external connections:

```bash
docker exec -it particiapp-docker_postgres_1 psql -U polis polis -c "CREATE ROLE wiki_polis_ro WITH LOGIN PASSWORD '<strong-password>'; GRANT CONNECT ON DATABASE polis TO wiki_polis_ro; GRANT USAGE ON SCHEMA public TO wiki_polis_ro; GRANT SELECT ON ALL TABLES IN SCHEMA public TO wiki_polis_ro; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO wiki_polis_ro;"
```

Use this role in the `POLIS_DATABASE_URL` Toolforge envvar: `postgresql://wiki_polis_ro:<password>@<private-ip>:5432/polis`

> **Use the numeric IP, not the hostname.** Toolforge pods cannot resolve the WMCS internal hostname (`*.wikimedia.cloud`) — the DSN must use the VPS's private IP address directly (e.g. `172.16.19.44`). For staging, use the same IP with port `5442`.

The same role also enqueues math recomputes by inserting into Polis'
`worker_tasks` table when results are empty. Note that nothing consumes those rows on this
deployment — the math container runs polismath's `full` mode, which does not instantiate
the task poller — so the grant prevents an error, it does not cause a recompute. See
[`ops/phase6-vote-sign-repair.md`](ops/phase6-vote-sign-repair.md) step 5b for routes that
do. Grant only that extra write surface:

```bash
~/wiki-polis/v2/ops/grant_polis_worker_tasks.sh \
  --container particiapp-docker_postgres_1 --role wiki_polis_ro
```

For staging, use `--container wiki-polis-staging_postgres_1`.

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

### Embedding sidecar (optional, for semantic similarity)

The semantic-similarity sidecar runs on the VPS as a separate container and is consumed
by future Flask statement-submission code. It is intentionally not a Toolforge
dependency.

```bash
cd ~/wiki-polis/v2/embedding_sidecar
docker-compose -f docker-compose.embedding.yaml up -d --build
curl -fsS http://127.0.0.1:8015/health
```

Expose it only on loopback or the private Docker/VPS network. When the Flask integration
lands, set `EMBEDDING_SIDECAR_URL` to the internal URL (for example
`http://<vps-private-ip>:8015` if Toolforge must reach it over the private network).
The HTTP contract is documented in `embedding_sidecar/README.md`.

### Backups

WMCS does not provide offsite backups for this self-hosted Postgres. Use `rclone` with
Backblaze B2 (or another offsite rclone remote) and keep only a brief local staging
copy:

```bash
sudo apt install -y rclone
rclone config   # create remote, e.g. b2:wiki-polis-postgres-backups
mkdir -p ~/particiapp-data/postgres-backups
```

Install cron on the VPS for production and staging Polis Postgres:

```cron
15 3 * * * RCLONE_REMOTE=b2:wiki-polis-postgres-backups HEALTHCHECKS_URL=https://hc-ping.com/<uuid-prod> /home/<user>/wiki-polis/v2/ops/backups/backup_polis_postgres_b2.sh --container particiapp-docker_postgres_1 --name prod
45 3 * * * RCLONE_REMOTE=b2:wiki-polis-postgres-backups HEALTHCHECKS_URL=https://hc-ping.com/<uuid-staging> /home/<user>/wiki-polis/v2/ops/backups/backup_polis_postgres_b2.sh --container wiki-polis-staging_postgres_1 --name staging
```

On Toolforge, back up ToolsDB with the same B2 remote and a MySQL option file rather
than command-line credentials:

```cron
30 4 * * * TOOLSDB_DATABASE=<creduser>__wiki-polis RCLONE_REMOTE=b2:wiki-polis-postgres-backups HEALTHCHECKS_URL=https://hc-ping.com/<uuid-toolsdb> /data/project/wiki-polis/wiki-polis/v2/ops/backups/backup_toolsdb_b2.sh
```

`backup_toolsdb_b2.sh` reads ToolsDB credentials from a MySQL option file via
`TOOLSDB_DEFAULTS_FILE`, which defaults to `$HOME/replica.my.cnf` — the standard
Toolforge-provisioned credentials file — so it does not normally need to be set explicitly.

Record the B2 application key, rclone remote name, Healthchecks URLs, Toolforge envvar
export, and VPS `.env` location in the password manager. See `guide_runbook.md` for the
restore drill.

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

**Toolforge jobs framework access:** the tool account also needs access to the Toolforge
jobs framework (`toolforge jobs ...`). Scheduled phase transitions rely on a `phase-scheduler`
job defined in `jobs.yaml` (repo root) — a `*/5 * * * *` cron job running
`v2/bin/phase-scheduler.sh`, which runs `flask --app app process-phase-schedules`.
`deploy.sh` registers/re-asserts this job on every deploy (`toolforge jobs load
~/wiki-polis/jobs.yaml`), so no separate one-time `toolforge jobs load` step is needed —
just make sure the tool account isn't blocked from the jobs framework.

### Install Python dependencies

Dependencies must be installed **inside the webservice shell** — a venv created on the bastion won't work with uWSGI:

```bash
toolforge webservice python3.13 shell
python3 -m venv ~/www/python/venv
source ~/www/python/venv/bin/activate
pip install -r ~/wiki-polis/v2/requirements-deploy.txt
pip install --no-deps -e ~/wiki-polis/v2
exit
```

### Add uwsgi.ini

Wikimedia OAuth tokens exceed uWSGI's default 4 KB header buffer, causing silent failures. The webservice also needs **threaded workers** to handle concurrent voters — the app is I/O-bound (each request blocks on Particiapi / Polis Postgres), so threads clear far more in-flight requests than the default single-threaded workers.

The canonical config lives in the repo at [`v2/ops/uwsgi.ini`](ops/uwsgi.ini) (record of truth). Toolforge reads it from `~/www/python/uwsgi.ini` — that is the required location, and `deploy.sh` does **not** copy it — so install it once per tool:

```bash
cp ~/wiki-polis/v2/ops/uwsgi.ini ~/www/python/uwsgi.ini
cd ~ && toolforge webservice restart
```

Or write it directly:

```bash
printf '[uwsgi]\nbuffer-size = 65536\nenable-threads = true\nprocesses = 4\nthreads = 20\n' > ~/www/python/uwsgi.ini
```

The `[uwsgi]` section header is mandatory; without it uWSGI silently ignores the file and uses its 4 KB default (and single-threaded workers). The `processes`/`threads` values are a starting point for ~1000 concurrent voters — **tune them with the load test** (`synthetic_traffic.py`), reconciling `processes × threads` with ToolsDB `max_user_connections`, the connection pools (`POLIS_HTTP_POOL_MAXSIZE` and `POLIS_PG_POOL_MAXCONN` default 20; `TOOLSDB_POOL_SIZE`+`TOOLSDB_MAX_OVERFLOW` default 10+10 = 20 total), and the pod's memory (raise with `toolforge webservice --mem 2Gi --cpu 1 python3.13 start`). See [`v2/ops/uwsgi.ini`](ops/uwsgi.ini) for the full rationale.

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
toolforge envvars create RATELIMIT_KEY_PREFIX
toolforge envvars create RATELIMIT_IDENTITY_SECRET
toolforge envvars create PARTICIAPI_SUB_SECRET
```

> ⚠️ **`PARTICIAPI_SUB_SECRET` is a long-lived master credential.** It lets the proxy
> assert any logged-in user's identity to Particiapi (cross-device stable participant).
> It must match Particiapi's config key `TRUSTED_SUB_SECRET` — which is set from the
> environment variable **`PARTICIAPI_TRUSTED_SUB_SECRET`**, since the image loads config
> via `from_prefixed_env("PARTICIAPI")` and strips the prefix. Setting the bare name does
> nothing, silently. It is sent to `PARTICIAPI_BASE_URL`
> on every identity bind — so that link **must be encrypted (WireGuard/TLS) or loopback**.
> A wire-capture of this secret, combined with the enumerable xid, would let an attacker
> forge any user's identity — so do not set it until the Toolforge↔VPS hop is encrypted
> (WireGuard/TLS) or loopback. If the secret is sent over a cleartext non-loopback
> transport the app logs a warning on every bind. Leave `PARTICIAPI_SUB_SECRET` unset to
> fall back to the old anonymous-per-session behaviour.

Non-secret values can be passed as arguments:

```bash
toolforge envvars create OAUTH_REDIRECT_URI 'https://wiki-polis.toolforge.org/oauth-callback'
toolforge envvars create TRUSTED_HOSTS 'wiki-polis.toolforge.org'
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
- `RATELIMIT_KEY_PREFIX` — unique Redis key namespace for this deployment; generate a random value such as `wiki-polis:prod:<random>:` for production and a different one for staging
- `RATELIMIT_IDENTITY_SECRET` — strong random HMAC key used to hash client identities before Flask-Limiter writes Redis keys
- `TRUSTED_HOSTS` — comma-separated allowed request hostnames, for example `wiki-polis.toolforge.org`; add explicit staging hostnames on staging deployments

Toolforge exposes shared Redis through the global `TOOL_REDIS_URI` environment variable, so production does not normally need a `RATELIMIT_STORAGE_URI` envvar. If running the Flask frontend directly on a Wikimedia VPS or overriding Toolforge Redis, set `RATELIMIT_STORAGE_URI` to a Redis URL such as `redis://<vps-private-ip>:6379/0`; production startup rejects local limiter backends such as `memory://`. Toolforge proxy headers are trusted automatically. On a Wikimedia VPS, set `TRUST_PROXY_HEADERS=1` only when the Flask app is behind a reverse proxy that overwrites incoming forwarding headers.

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

> **Budget four to five minutes.** `deploy.sh` is not instant and gives little output
> while it works, so it reads as hung when it is not. Most of the time is the React
> build: on a Toolforge bastion there is no `npm`, so the script opens an ephemeral
> `node20` runtime shell and runs `npm ci` plus `npm run build` inside it. Dependency
> sync, `toolforge jobs load` and the webservice restart account for the rest.
>
> Wait it out rather than interrupting — a deploy killed midway can leave dependencies
> synced against a revision whose assets were never built. The `--expect` guard only
> protects the start of the run, not the middle.

```bash
# On Toolforge bastion as wiki-polis user:
cd ~/wiki-polis && git pull
pip install -r ~/wiki-polis/v2/requirements-deploy.txt
pip install --no-deps -e ~/wiki-polis/v2
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

Deploy a named branch only while it remains a live `origin` ref, and pin the
reviewed commit when staging a moving development branch:

```bash
bash ~/wiki-polis/deploy.sh refactor/spa-api-foundation --expect 94fda38
```

For a pull request whose head branch belongs to a fork, deploy GitHub's pull ref
directly instead of temporarily changing `origin`:

```bash
bash ~/wiki-polis/deploy.sh --pr 303 --expect 94fda38
```

The script fetches with pruning and validates `--expect` before installing
dependencies, building assets, running migrations, or restarting the service. A
deleted branch, missing pull ref, or SHA mismatch therefore fails closed.
Python dependencies are installed from `v2/requirements-deploy.txt`, an exact
production snapshot exported from `v2/uv.lock`; the editable app install then uses
`--no-deps` so pip cannot silently re-resolve a different graph on Toolforge.

`deploy.sh` also runs `toolforge jobs load ~/wiki-polis/jobs.yaml` on every deploy, re-asserting
the `phase-scheduler` scheduled job (see [One-time tool setup](#one-time-tool-setup) above). This
step is non-fatal but loud — if `toolforge jobs load` fails, the script prints an error and
continues the web deploy, but scheduled phase transitions won't fire until the job is reloaded
manually.

The script also builds the React frontend on every deploy. When `npm` is available it builds
directly; on a Toolforge bastion, where application runtimes are intentionally absent, it
automatically opens an ephemeral `node20` runtime shell and builds there. Toolforge mounts the
tool's shared home directory into that shell, so the resulting `v2/static/spa` assets are ready
for the Python webservice restart. No manual npm or partial-deployment recovery step is needed.

### Buildservice status

Toolforge buildservice has been evaluated but is **not** the default deploy path. The
repo still contains legacy top-level Flask files while the live app is under `v2/`, so a
root buildpack/Procfile migration could accidentally build the wrong app. Use the
current `python3.13` webservice flow until a staging pilot with an explicit `v2/`
Dockerfile/build context passes. See `ops/toolforge-buildservice.md`.

---

## Database migrations

There are two ways to run Alembic migrations. **The supported path is `bash ~/wiki-polis/deploy.sh --migrate`** (see below) — it handles the environment for you. The manual webservice-shell path is documented after it as a fallback / for ad-hoc upgrades.

The underlying constraint: `toolforge envvars` (including `DATABASE_URL`) are injected into the webservice pod, not into bastion sessions, **and** the app's production startup runs checks (TRUSTED_HOSTS, distributed rate-limit storage) that also depend on pod-only values. So a bare `flask db upgrade` on the bastion fails twice over — first on `DATABASE_URL`, then on those startup checks.

### `deploy.sh --migrate` and `MIGRATION_MODE`

`deploy.sh --migrate` runs the migration from the bastion by:
1. **Loading all Toolforge envvars** into the environment dynamically (so `DATABASE_URL` etc. are present — no hard-coded list to maintain).
2. Running `MIGRATION_MODE=1 flask --app app db upgrade`.

**`MIGRATION_MODE=1`** tells `create_app()` to **skip the web-server-only startup checks** (TRUSTED_HOSTS, RATELIMIT_STORAGE_URI / key / identity secret) that require Kubernetes-injected values unavailable on the bastion. It has **no effect on which code runs** — migrations only touch the database — so it is safe and is the intended way to migrate outside the pod. (It is also handy when running the test suite or any one-off Flask command on a machine without the full production env.)

```bash
# from the bastion, as the wiki-polis tool
bash ~/wiki-polis/deploy.sh --migrate
```

### Manual path (fallback)

Run inside the webservice shell, where pod envvars are present (here you do **not** set `MIGRATION_MODE` — the real env satisfies the checks):

### Migration history

Ordered chain (oldest → newest); the current head is `d5e6f7a8b9c0`. Run `flask --app app db upgrade` to apply everything up to the head — you do not apply these individually.

| Order | Revision | Description |
|---|---|---|
| 1 | `65de8d5c7314` | Adds `closed_at`, `public_username`, `revealed_at`. |
| 2 | `b959def66404` | Adds `conversations.paused`. |
| 3 | `99f8b42af697` | Adds `arguments.hidden`. |
| 4 | `a3f1c8e2d905` | Adds `participations.new_stmt_ids`. |
| 5 | `3e86727dbcee` | Phase 6 — adds `phase_informed_voting`, `phase6_polis_conversation_id` to conversations; `phase6_polis_statement_id` to featured_statements; UNIQUE constraints and index. |
| 6 | `f667548e9519` | Adds `participations.phase6_card_order` (JSON, nullable). |
| 7 | `c1a2b3d4e5f6` | Adds `conversations.phase_cleanup` (boolean, default off) — the passive phase between argument mapping and informed voting (#163). |
| 8 | `d2e3f4a5b6c7` | Adds the append-only `audit_events` table (#135). |
| 9 | `e3f4a5b6c7d8` | Adds `statement_provenance` and `statement_similarity_scores` tables for derivative-statement tracking (#143). |
| 10 | `4b6c7d8e9f01` | Adds `participants.xid_key_version` (legacy plain-sha256 vs. HMAC-keyed xid) (#96). |
| 11 | `5c7d8e9f0123` | Adds `arguments.proposer_pseudonym`, backfills it, and drops `arguments.proposer_id` (#113). |
| 12 | `6d8e9f012345` | Adds conversation/participation eligibility-gate columns (`eligibility_event_id`, `eligibility_label`, `eligibility_status`, `eligibility_checked_at`, `eligibility_detail`) (#146). |
| 13 | `7e9f01234567` | Adds `participants.is_demo` marker (#223). |
| 14 | `a4b5c6d7e8f9` | Adds `conversations.recommended_quantities` (JSON) (#160). |
| 15 | `b5c6d7e8f9a0` | Adds `conversations.phase_route` (default `default_7`) (#173). |
| 16 | `c6d7e8f9a0b1` | Adds scheduled phase-transition fields to `conversations` (`scheduled_transition_at`, `scheduled_transition_target`, `scheduled_transition_frozen`) (#164). |
| 17 | `d7e8f9a0b1c2` | Adds `conversations.report_filter_snapshot` (JSON) (#186). |
| 18 | `a4b5c6d7e8fa` | Widens the `admin_roles.role` enum to add the organizer role (#154). |
| 19 | `b4c5d6e7f8a9` | Adds `participations.last_engagement` (#42). |
| 20 | `c4d5e6f7a8b9` | Adds the `conversation_bans` table (#60). |
| 21 | `d5e6f7a8b9c0` | Adds the `content_flags` table (statement/argument moderation flags) (#138). **Current head.** |

Verify the live head with `flask --app app db current`; confirm it matches `d5e6f7a8b9c0` after deploying. When new migrations land, append them here.

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

**This only works on the bastion.** `toolforge` is not installed inside `toolforge webservice python3.13 shell` (confirmed 2026-08 — `bash: toolforge: command not found`), and `/run/secrets/wiki-polis/<name>` is also **not** mounted in that debug shell (despite being what `_read_secret()` in `app.py` reads from at runtime — that mount exists in the actual serving pod, not this ad-hoc shell). So the pattern above cannot be run from inside the webservice shell itself.

If you need a secret value inside the webservice shell (e.g. to run a one-off script that isn't wired into `flask --app app.py ...`), fetch it on the bastion first, then pass it in without echoing it to the screen or shell history:

```bash
# On the bastion:
toolforge envvars show DATABASE_URL   # note the value

# Inside the webservice shell:
read -rs DATABASE_URL   # paste the value at the hidden prompt, press Enter
export DATABASE_URL
```

`deploy.sh --migrate` does this automatically — it loads **all** Toolforge envvars dynamically (the full `toolforge envvars list`), so every required variable is present with no hard-coded list to maintain. `flask --app app db upgrade`, run via `deploy.sh --migrate`, is the supported path precisely because it avoids this gap.

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
| `toolforge: command not found` / secrets missing inside `toolforge webservice python3.13 shell` | That debug shell has neither the `toolforge` CLI nor the `/run/secrets/wiki-polis/` mount the serving pod has. Fetch values on the bastion and pass them in via `read -rs VARNAME` (see "Exporting envvars manually" above), or run the work as a job, which *does* get the tool's envvars injected |
| Envvars empty in a script (`$DATABASE_URL` unset) | An interactive **bastion** shell gets no injected envvars — only jobs and the webservice do. Run one-off work with `toolforge jobs run … --wait`, as `v2/bin/phase-scheduler.sh` does |

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | yes | Flask session signing key |
| `OAUTH_CLIENT_ID` | yes (prod) | Wikimedia OAuth consumer key |
| `OAUTH_CLIENT_SECRET` | yes (prod) | Wikimedia OAuth consumer secret |
| `OAUTH_REDIRECT_URI` | yes (prod) | Must match registered callback URL |
| `PARTICIAPI_BASE_URL` | yes | Internal URL of Particiapi (e.g. `http://10.x.x.x:8000`) — **must be encrypted (TLS) or loopback if `PARTICIAPI_SUB_SECRET` is set** |
| `PARTICIAPI_SUB_SECRET` | no | Shared master secret for cross-device identity binding; must be set on Particiapi as env var `PARTICIAPI_TRUSTED_SUB_SECRET` (config key `TRUSTED_SUB_SECRET`; the bare env name is ignored). Unset → anonymous-per-session. Only set it when the transport is encrypted (TLS) or loopback |
| `DATABASE_URL` | yes (prod) | SQLAlchemy DB URL; defaults to `sqlite:///dev.db` |
| `POLIS_SERVER_URL` | yes | Direct Polis server URL (e.g. `http://10.x.x.x:8001`) — required for conversation creation |
| `POLIS_ADMIN_EMAIL` | yes | Email of the Polis system account (created once on VPS) |
| `POLIS_ADMIN_PASSWORD` | yes | Password of the Polis system account |
| `POLIS_DATABASE_URL` | no | Direct Postgres connection for admin stats panel; leave blank to disable |
| `TOOL_REDIS_URI` | provided by Toolforge | Shared Toolforge Redis URL; used automatically for Flask-Limiter when `RATELIMIT_STORAGE_URI` is unset |
| `RATELIMIT_STORAGE_URI` | VPS/override only | Explicit Redis backend, for example `redis://<host>:6379/0`; production rejects non-Redis limiter storage |
| `RATELIMIT_KEY_PREFIX` | yes (prod) | Unique random Redis key namespace for this deployment, for example `wiki-polis:prod:<random>:` |
| `RATELIMIT_IDENTITY_SECRET` | yes (prod) | Random HMAC secret used to avoid storing raw client identities in shared Redis keys |
| `TRUST_PROXY_HEADERS` | VPS reverse proxy only | Set to `1` only when a Wikimedia VPS reverse proxy overwrites forwarding headers; Toolforge is detected automatically |
| `TRUSTED_HOSTS` | yes (prod) | Comma-separated allowed request hostnames, for example `wiki-polis.toolforge.org` |
| `LOKI_URL` | optional | HTTPS Loki push endpoint for central diagnostics logs |
| `LOKI_USERNAME` | optional | Basic-auth username for `LOKI_URL` |
| `LOKI_PASSWORD` | optional | Basic-auth password for `LOKI_URL` |
| `LOKI_LABELS` | optional | Low-cardinality Loki labels, e.g. `stack=toolforge`; `service=wiki-polis` is forced |
| `LOKI_QUEUE_SIZE` | optional | Async log shipping queue size; default `1000` |
| `LOKI_TIMEOUT` | optional | Loki POST timeout in seconds; default `2.0` |
| `WIKI_POLIS_ENV` | optional | Environment label for logs and staging-only operational gates, e.g. `staging` or `prod` |
| `EMBEDDING_SIDECAR_URL` | future optional | Internal URL for the VPS embedding sidecar once semantic similarity is wired |
| `DEV_LOGIN_USER` | dev only | Bypasses OAuth in local dev; never set in production |
| `DEV_FAKE_LOGIN` | dev only | Set to `1` to show hardcoded test-user badges on the home page; never set in production |
| `STAGING_DEV_TOKEN` | staging only | HMAC secret for `/dev/login/<username>?token=...` on `wiki-polis-dev`; never set on production |
| `FLASK_DEBUG` | dev only | Enables debug mode; never set in production |
