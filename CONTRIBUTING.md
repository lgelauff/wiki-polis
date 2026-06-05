# Contributing to wiki-polis

Thanks for contributing. This guide covers everything you need to get from a
fresh clone to a merged pull request.

---

## Table of contents

1. [Prerequisites](#prerequisites)
2. [Local setup](#local-setup)
3. [Project structure](#project-structure)
4. [Making changes](#making-changes)
5. [Running tests](#running-tests)
6. [Adding a new environment variable](#adding-a-new-environment-variable)
7. [Database migrations](#database-migrations)
8. [Submitting a pull request](#submitting-a-pull-request)
9. [Deploying to staging](#deploying-to-staging)

---

## Prerequisites

- **Docker Desktop** (or Colima / any Docker runtime with Compose v2.24+)
- **Python 3.13** (other 3.x versions may work but are untested)
- **uv** for Python dependency management

On macOS with Homebrew:

```bash
brew install uv
```

---

## Local setup

Clone both repositories side by side — wiki-polis depends on a sibling
`particiapp-docker` checkout for the backend services:

```bash
cd /path/to/Repositories
git clone https://github.com/lgelauff/wiki-polis
git clone --recurse-submodules https://gitlab.com/particiapp/particiapp-docker
```

> If `particiapp-docker` lives elsewhere, set `PARTICIAPP_DOCKER_DIR=/path/to/it`
> when running `dev.sh`.

Copy the example env file and start the stack:

```bash
cp v2/.env.example v2/.env
./dev.sh
```

Then open `http://127.0.0.1:5001`. Log in via `/dev-login` (single dev user)
or set `DEV_FAKE_LOGIN=1` in `v2/.env` to get three switchable test accounts.

Verify everything is healthy:

```bash
curl http://127.0.0.1:5001/health
# {"db":"ok","particiapi":"ok","status":"ok"}
```

See [`v2/guide_local-dev.md`](v2/guide_local-dev.md) for a full walkthrough
including port configuration and stopping the stack.

---

## Project structure

```
wiki-polis/
├── v2/                         Flask app (production code)
│   ├── app.py                  Main application — routes, auth, startup
│   ├── db.py                   SQLAlchemy models
│   ├── migrations/             Alembic database migrations
│   ├── templates/              Jinja2 HTML templates
│   ├── static/                 CSS, JS, assets
│   ├── tests/                  pytest test suite
│   ├── .env.example            Documented env var template
│   ├── guide_local-dev.md      Local development walkthrough
│   ├── guide_deployment.md     Production / Toolforge deployment guide
│   └── guide_runbook.md        Day-2 operations (logs, staging, secrets)
├── deploy.sh                   Toolforge deploy script
└── CONTRIBUTING.md             This file
```

---

## Making changes

### Branch naming

| Prefix | Use for |
|--------|---------|
| `feat/` | New features |
| `fix/` | Bug fixes |
| `docs/` | Documentation only |
| `security/` | Security hardening |

### Workflow

```bash
git checkout -b feat/my-change
# make changes
git push origin feat/my-change
# open a pull request on GitHub
```

Force-pushed branches are fine — `deploy.sh` handles them with `reset --hard`.

---

## Running tests

```bash
cd v2
uv run pytest
```

The test suite uses SQLite in-memory and mocks the Polis/Particiapi backends,
so the Docker stack does not need to be running.

For anything that touches the live backend (featured statements, voting, real
statement text), test on staging after deploying. See
[Deploying to staging](#deploying-to-staging).

---

## Adding a new environment variable

When you add a new config value to the app, update **all five** of these
places. Missing any one of them will cause a confusing failure — most likely
a `RuntimeError` on startup or a silent wrong value in production.

### 1. `v2/.env.example`

Add the variable with a descriptive comment explaining what it does, what
format it expects, and when it is required vs optional. Follow the style of
the existing entries:

```bash
# Leave blank for local dev. Production must set a unique Redis key namespace,
# e.g. wiki-polis:prod:<random>:
RATELIMIT_KEY_PREFIX=
```

### 2. `v2/app.py` — startup validation

If the variable is required in production, add a check in `create_app()` that
raises `RuntimeError` with a clear message when it is missing. Pattern:

```python
_my_value = app.config.get('MY_VAR') or _read_secret('my-var')
if _my_value:
    app.config['MY_VAR'] = _my_value
elif not app.debug and not app.testing:
    raise RuntimeError(
        'MY_VAR is not set. Configure it before starting production.'
    )
```

### 3. `deploy.sh` — migration block

If the variable is needed for `flask db upgrade` to load the app (i.e. it is
validated at startup), export it in the migration block so it is available
when running migrations from the Toolforge bastion, where Toolforge-injected
env vars are not available:

```bash
export MY_VAR=$(_envvar MY_VAR)
```

Add it alongside the other exports in the `if [ "$MIGRATE" -eq 1 ]` block.

> **Why?** `flask db upgrade` runs on the bastion shell, not inside the
> webservice container. Toolforge only injects env vars into the container
> runtime — the bastion shell does not have them. The `_envvar` helper reads
> them from `toolforge envvars show`.

> **Exception:** Variables provided automatically by Toolforge at runtime
> (e.g. `TOOL_REDIS_URI`) cannot be fetched this way. For those, use
> `FLASK_DEBUG=1` to bypass the production startup check during migrations,
> as already done in the script.

### 4. `v2/guide_deployment.md` — env var reference table

Add a row to the environment variable reference table near the bottom of the
file. Include whether it is required, and a one-line description:

```markdown
| `MY_VAR` | yes (prod) | Description of what it does |
```

Also add the `toolforge envvars create MY_VAR` command to the setup section
if operators need to set it during first-time deployment.

### 5. Store secrets safely

If the variable is a **secret** (password, HMAC key, OAuth credential),
document this clearly in `.env.example` and remind operators to store the
value somewhere safe outside of the repository. Losing a secret like
`RATELIMIT_IDENTITY_SECRET` means all existing rate-limit counters reset;
losing `SECRET_KEY` invalidates all active sessions.

---

## Database migrations

### Generating a migration

After changing a model in `db.py`, generate a migration automatically:

```bash
cd v2
uv run flask db migrate -m "describe the change"
```

Review the generated file in `migrations/versions/` — Alembic auto-generation
is good but not perfect. Check that the `upgrade()` and `downgrade()` functions
are correct before committing.

### Applying migrations locally

Migrations run automatically when you restart the Flask app in dev mode.

### Applying migrations on Toolforge

Pass `--migrate` to `deploy.sh`:

```bash
bash ~/wiki-polis/deploy.sh <branch> --migrate
```

`deploy.sh` exports the required env vars from `toolforge envvars` and sets
`FLASK_DEBUG=1` inline on the `flask db upgrade` command to bypass
production startup checks that require Toolforge-injected vars unavailable
on the bastion shell.

---

## Submitting a pull request

1. **Open a PR** on GitHub against `main`.
2. **Describe the change** — what problem it solves, not just what it does.
   Link the related issue if there is one.
3. **Test locally** — run `uv run pytest` and verify the relevant flows work
   in the browser.
4. **Test on staging** for anything that touches live-backend paths (voting,
   statement submission, results, featured statements). See below.
5. **Don't merge your own PR** without a review unless it is a trivial docs
   fix.

---

## Deploying to staging

Staging lives at `wiki-polis-dev.toolforge.org`. It has its own database and
is safe to mutate.

```bash
ssh login.toolforge.org
become wiki-polis-dev
bash ~/wiki-polis/deploy.sh <your-branch>          # no schema change
bash ~/wiki-polis/deploy.sh <your-branch> --migrate # schema change
toolforge webservice status
```

After deploying, log in via Wikimedia OAuth and verify the affected flows.
The commit hash is shown in the bottom-right footer — confirm it matches
`git rev-parse --short HEAD` on your branch before trusting any result.

See [`v2/guide_runbook.md`](v2/guide_runbook.md) for staging topology,
log locations, and debugging tips.
