# Local development setup

This doc covers running the full wiki-polis stack locally: the Flask app (native) + the Particiapi/Polis backend (Docker).

## Prerequisites

- Docker Desktop
- Python 3.11+ with `uv` (`brew install uv`)
- The `particiapp-docker` repo cloned **with submodules** (see below)

## 1. Clone particiapp-docker

```bash
git clone --recurse-submodules https://gitlab.com/particiapp/particiapp-docker
```

If you already cloned without submodules:

```bash
rm -rf subprojects/ && git submodule update --init
```

## 2. Create the local compose override

In the `particiapp-docker` directory, create `docker-compose.local.yaml` (gitignored):

```yaml
# Exposes postgres to the host so the native Flask app can connect directly.
services:
  postgres:
    ports:
      - "127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432"
```

The port defaults to `5432`. If that conflicts with a local postgres, add `POSTGRES_HOST_PORT=5433` (or any free port) to `particiapp-docker/.env` and update the port in `v2/.env` to match.

## 3. Start the backend stack

From the `particiapp-docker` directory:

```bash
docker compose \
  -f docker-compose.yaml \
  -f docker-compose.wiki-polis.yaml \
  -f docker-compose.local.yaml \
  up -d
```

This starts:
- **Particiapi** on `http://127.0.0.1:8000` (auth disabled)
- **Polis server** on `http://127.0.0.1:8001`
- **Postgres** on `127.0.0.1:5432` (exposed to host)

## 4. Configure v2/.env

`v2/.env` should contain (these are the defaults for local dev):

```ini
FLASK_DEBUG=1
FLASK_APP=app.py

PARTICIAPI_BASE_URL=http://127.0.0.1:8000
POLIS_PUBLIC_URL=http://127.0.0.1:8001
POLIS_DATABASE_URL=postgresql://polis:polis@127.0.0.1:5432/polis

ADMIN_USERS=DevUser
DEV_LOGIN_USER=DevUser

OAUTH_CLIENT_ID=
OAUTH_CLIENT_SECRET=
OAUTH_REDIRECT_URI=
```

## 5. Start the Flask app

From `v2/`:

```bash
uv run flask run --host 127.0.0.1 --port 5000
```

Dev login is available at `http://127.0.0.1:5000/dev-login` — use `127.0.0.1`, not `localhost` (macOS AirPlay intercepts port 5000 on IPv6).

## 6. Seed test data (optional)

To populate a cats-vs-dogs demo conversation with statements and featured statements:

```bash
uv run python simulate_cats_vs_dogs.py
```

## Stopping the stack

```bash
docker compose \
  -f docker-compose.yaml \
  -f docker-compose.wiki-polis.yaml \
  -f docker-compose.local.yaml \
  down
```
