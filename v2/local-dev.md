# Local Development Setup

This runs the v2 wiki-polis stack locally:

- Flask runs natively from this repository.
- Particiapi, Polis, Polis math, and Postgres run in Docker from a sibling
  `particiapp-docker` checkout.
- Particiapi authentication is disabled locally; wiki-polis supplies identity
  through the Flask dev-login route.

The v1 app embeds hosted `pol.is`. For a fully local stack, use v2.

## Prerequisites

- Docker Desktop, Colima, or another Docker runtime.
- Docker Compose v2.24+ (shipped with Docker Desktop v4.27+, Jan 2024) as
  either `docker compose` or `docker-compose`. The standalone `docker-compose`
  v1 binary is not supported.
- Python 3.11+.
- `uv` for Python dependency management.

On macOS with Homebrew:

```bash
brew install uv
```

## Repository Layout

Clone `particiapp-docker` next to `wiki-polis`, including submodules:

```bash
cd /path/to/Repositories
git clone https://github.com/lgelauff/wiki-polis
git clone --recurse-submodules https://gitlab.com/particiapp/particiapp-docker
```

Expected layout:

```text
Repositories/
  wiki-polis/
  particiapp-docker/
```

If `particiapp-docker` lives somewhere else, set `PARTICIAPP_DOCKER_DIR` when
running `dev.sh`.

## Quick Start

From the `wiki-polis` repository:

```bash
cp v2/.env.example v2/.env
./dev.sh
```

Then open:

```text
http://127.0.0.1:5001/dev-login
```

`dev.sh` starts the Docker backend, initializes the Flask dev database, and
then starts Flask.

## Default Ports

The first run creates `.dev-session` with local port assignments:

```ini
POSTGRES_PORT=5433
PARTICIAPI_PORT=8002
POLIS_PORT=8003
FLASK_PORT=5001
```

Edit `.dev-session` before running `./dev.sh` if any of those ports are taken.
The defaults avoid common conflicts with local Postgres, other development
servers on `8000`, and macOS AirPlay Receiver on `5000`.

## Configuration Files

The backend Compose stack reads its default service settings from
`particiapp-docker/.env` when present, otherwise from `particiapp-docker/dev.env`.

wiki-polis owns the local override in:

```text
v2/docker-compose.wiki-polis.local.yaml
```

That override:

- exposes Postgres to the host;
- exposes Particiapi and Polis server on configurable host ports;
- disables Particiapi authentication for local Flask-driven dev;
- mounts Postgres data under `v2/tmp/postgresql`, using the Postgres 18
  compatible `/var/lib/postgresql` mount point.

Copy the example Flask environment file before the first run:

```bash
cp v2/.env.example v2/.env
```

Then edit `v2/.env`:

- Set `SECRET_KEY` to a random value:
  `python3 -c "import secrets; print(secrets.token_hex(32))"`.
- Set `ADMIN_USERS` and `DEV_LOGIN_USER` to your Wikimedia username.
- Optionally set `POLIS_ADMIN_EMAIL` and `POLIS_ADMIN_PASSWORD` if you have
  created a local Polis system account.

All other defaults work for local dev out of the box. `dev.sh` also exports the
same core values so `.dev-session` port changes are reflected automatically:

```ini
FLASK_DEBUG=1
FLASK_APP=app.py
SECRET_KEY=dev-insecure-key
ADMIN_USERS=DevUser
DEV_LOGIN_USER=DevUser
DEV_DATABASE_URL=sqlite:///dev.db
PARTICIAPI_BASE_URL=http://127.0.0.1:8002
POLIS_SERVER_URL=http://127.0.0.1:8003
POLIS_PUBLIC_URL=
POLIS_DATABASE_URL=postgresql://polis:polis@127.0.0.1:5433/polis
POLIS_ADMIN_EMAIL=
POLIS_ADMIN_PASSWORD=
```

Do not set `POLIS_PUBLIC_URL` to an `http://` URL for local dev. The Flask app
ignores non-HTTPS values by design.

If `POLIS_ADMIN_EMAIL` and `POLIS_ADMIN_PASSWORD` are blank, creating a
wiki-polis conversation from the admin form requires entering an existing
`polis_id` manually. To enable automated conversation creation locally, create a
Polis system account after the Docker stack is running:

```bash
curl -s -X POST http://127.0.0.1:8003/api/v3/auth/new \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "wiki-polis-system@internal.invalid",
    "password": "localdev",
    "hname": "wiki-polis system",
    "gatekeeperTosPrivacy": true
  }'
```

Then put those credentials in `v2/.env`.

## Manual Backend Commands

`dev.sh` is the recommended path. If you need to run the backend manually, use
the same Compose files and provide `WIKI_POLIS_DIR`:

```bash
WIKI_POLIS_DIR="$(pwd)" \
POSTGRES_HOST_PORT=5433 \
PARTICIAPI_HOST_PORT=8002 \
POLIS_HOST_PORT=8003 \
FLASK_HOST_PORT=5001 \
docker compose \
  --env-file ../particiapp-docker/dev.env \
  -f ../particiapp-docker/docker-compose.yaml \
  -f v2/docker-compose.wiki-polis.local.yaml \
  up -d
```

Use `docker-compose` in place of `docker compose` if your machine has the
standalone command.

Initialize and run Flask manually:

```bash
cd v2
uv run flask --app app init-db
uv run flask --app app run --host 127.0.0.1 --port 5001
```

## Seed Demo Data

To populate a cats-vs-dogs demo conversation:

```bash
cd v2
uv run python simulate_cats_vs_dogs.py
```

If you changed the Particiapi port:

```bash
uv run python simulate_cats_vs_dogs.py --particiapi-url http://127.0.0.1:8012
```

The script also reads `PARTICIAPI_BASE_URL` from `v2/.env`.

## Stopping The Stack

If you started with `./dev.sh`, press `Ctrl-C`; the script stops the Docker
stack it started.

For a manual backend stop:

```bash
WIKI_POLIS_DIR="$(pwd)" \
docker compose \
  --env-file ../particiapp-docker/dev.env \
  -f ../particiapp-docker/docker-compose.yaml \
  -f v2/docker-compose.wiki-polis.local.yaml \
  down
```

Use `docker-compose` instead of `docker compose` when appropriate.

## Troubleshooting

- If `./dev.sh` cannot find `particiapp-docker`, either clone it next to
  `wiki-polis` or set `PARTICIAPP_DOCKER_DIR=/absolute/path/to/particiapp-docker`.
- If Docker reports port conflicts, edit `.dev-session` and re-run `./dev.sh`.
- On Apple Silicon, Docker may warn that some Polis images are `linux/amd64`.
  That is expected when the image has no native ARM build.
- If `polis-server` is repeatedly killed with `SIGKILL`, increase Docker's
  memory limit. Particiapi and Postgres may still be healthy, but Polis admin
  operations will be unreliable until the server stays up.
