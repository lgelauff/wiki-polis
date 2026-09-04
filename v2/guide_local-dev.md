# Local Development Setup

This runs the v2 wiki-polis stack locally:

- Flask runs natively from this repository.
- Particiapi, Polis, Polis math, and Postgres run in Docker from a sibling
  `particiapp-docker` checkout.
- Particiapi authentication is disabled locally; wiki-polis supplies identity
  through the Flask dev-login route.

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
- persists Postgres data in the Compose-managed `polis-pgdata` volume, using the
  Postgres 18 compatible `/var/lib/postgresql` mount point. A named volume avoids
  fresh-database ownership failures with Docker Desktop bind mounts on macOS.

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

**Pass `--particiapi-url` whenever `v2/.env` sets `PARTICIAPI_BASE_URL`.** The simulator
calls `load_dotenv` at import, so a value there wins over the built-in default and the
run fails with *"cannot reach Particiapi"* naming a port you did not choose. `dev.sh`
exports the port it actually bound; give the simulator the same one.

**Do not reuse a conversation generated before the phase-2 vote-sign fix.** Those runs
wrote every agree as a disagree (the `VOTES` table was authored the intuitive way round),
so an old cats-vs-dogs conversation holds inverted phase-2 votes that cannot be repaired
in place — its phase 6 round, if it has one, was written correctly, so the database mixes
both conventions. Generate a fresh conversation instead.

The script also reads `PARTICIAPI_BASE_URL` from `v2/.env`.

### Derivative statements

`--derivatives N` makes N of the mid-run submissions **rewordings of an existing
statement**, each recorded in `statement_provenance` via the app's own
`record_statement_provenance()` — the same function the `/statements/new` route uses,
so the rows and their similarity scores are the real thing. Simulated voters vote a
rewording the way they voted its parent, so a lineage looks like a lineage in the
vote matrix.

```bash
uv run python simulate_cats_vs_dogs.py --derivatives 6
```

Needed by anything that reads provenance: the derivative-statement analysis, the
lineage-collapse counterfactual, and the near-duplicate grouping. Requires Flask
registration, so it is skipped under `--skip-flask`.

### Stable participant identity

By default every simulated voter opens a fresh anonymous Particiapi session, so each
one becomes a **different** Polis `uid`. That is fine for a single round, but it means
a Phase 2 participant and a Phase 6 participant can never be recognised as the same
person — which is exactly what a before/after comparison needs.

Set `PARTICIAPI_SUB_SECRET` in `v2/.env` and the simulator asserts a stable subject per
synthetic person, the way Flask's proxy does in production — see
[`ref_cross-device-identity.md`](ref_cross-device-identity.md).

`dev.sh` passes that same value to the container as `PARTICIAPI_TRUSTED_SUB_SECRET`, so
one setting covers both sides and they cannot drift apart. It prints which mode it started
in. (Before this was wired, the two variables had to be set separately and nothing carried
the value to the container — so the local stack could not exercise trusted-sub at all, and
identity behaviour observed locally meant nothing.)

**The secret alone is not enough.** The published
`registry.gitlab.com/particiapp/particiapi/particiapi:latest` image predates the
trusted-sub feature. An image without it accepts the header, ignores it, and returns
`200` — indistinguishable from working, and `particiapi_users` simply stays empty.
`dev.sh` now checks the image and says so rather than letting you discover it from an
empty table. To get an image that does support it, build from the submodule, which
carries the feature:

```bash
docker build -t registry.gitlab.com/particiapp/particiapi/particiapi:latest \
  ../particiapp-docker/subprojects/particiapi
```

Then `dev.sh` again. Confirm with `SELECT count(*) FROM particiapi_users;` after voting —
a non-zero count is the only proof that binding is live.

The script probes this at startup and says which mode it is in:

```
[identity] trusted-sub honoured — participants keep one uid across rounds
[identity] trusted-sub NOT honoured (secret mismatch, or a Particiapi image
           predating the feature) — participants will be anonymous
```

It asks the database rather than trusting the response, because an unset secret, a
mismatched secret and an image without the feature all look identical from the
client side: a session that silently falls back to anonymous.

## Dev Test Users

Three generic test accounts let you switch between user identities without going through Wikimedia OAuth. Enable them by setting `DEV_FAKE_LOGIN=1` in `v2/.env`.

**Local dev** — `v2/.env`:
```
DEV_FAKE_LOGIN=1
```

Restart Flask, then visit the home page. An amber badge strip appears below the login button with three accounts: `dev-user-1`, `dev-user-2`, `dev-user-3`. Clicking a badge logs you in immediately — the `Participant` record is created on first use. Use the accounts to simulate multiple participants interacting in the same consultation.

These accounts use negative `mw_user_id` values so they never collide with real Wikimedia accounts. The route only registers when Flask is running in local debug mode and not on Toolforge, even if `DEV_FAKE_LOGIN=1` is present.

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
