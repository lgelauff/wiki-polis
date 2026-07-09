# Testing tiers (for agents)

Three tiers, in increasing fidelity and cost. **Use the lowest tier that can actually
exercise the change** — and escalate only when that tier genuinely can't reach the path.

| Tier | What runs | Backend | Shared state? | Skill |
|---|---|---|---|---|
| 1. Unit | `v2/tests/` | mocked / absent | no (SQLite, per-test) | — (just run; `pr-check` gates it) |
| 2. Local integration | full stack on **your** machine | **real**, local Docker | no (private, torn down) | **`local-e2e`** |
| 3. Staging | a deployed branch on `wiki-polis-dev` | **real**, shared | **yes** | **`staging-chrome-test`** |

Pick the lowest tier that can actually exercise the change; escalate only when the tier below
genuinely can't reach the path (real backend, Toolforge proxy, OAuth, Polis-math timing). The
detail that matters for agents is **how to use tier 3 responsibly**, below.

## Tier 1 — Unit tests (pytest)

- **What:** `v2/tests/` against SQLite, with Polis/Particiapi mocked or absent.
- **When:** pure logic, helpers, routes that don't need the real backend.
- **How:** `cd v2 && uv run pytest` (hermetic; the canonical CI command).
- **Limits:** can't exercise real voting / results / clustering / featured-statement text —
  those degrade to fallbacks. A bug in a live-backend path **passes here**. That's the
  reason tiers 2 and 3 exist.

## Tier 1½ — Migration check on MariaDB (cheap pre-staging gate)

Tier 1 runs on SQLite, which does **not** enforce the FK/index, `ENUM`, or `JSON` DDL rules
that Toolforge's **MariaDB** does. A migration can pass `pytest` yet fail `flask db upgrade`
on deploy — e.g. err 1553, *"cannot drop index needed in a foreign key constraint"*. Until now
that only surfaced at tier 3 (staging), where a half-applied migration leaves the shared DB
broken for everyone (see `guide_runbook.md` → *Migration fails with "Duplicate column"
(alembic drift)*).

- **What:** runs the migration chain against a real, throwaway MariaDB — bootstraps the base
  schema, then applies the current branch's migrations exactly as a deploy would.
- **When:** any change that adds or edits a file under `v2/migrations/versions/`.
- **How (local):** `bash migration-check.sh` from the repo root (needs Docker; spins and tears
  down its own MariaDB). Pass a base ref as `$1` (defaults to `origin/main`).
- **CI:** the `migrations-mariadb` job in `.github/workflows/test.yml` runs the same script
  against a MariaDB service on every PR — so "SQLite-only CI" no longer misses this class of bug.
- **Known limitation:** the base schema is bootstrapped with SQLAlchemy's `create_all()` (from
  the current models) rather than by replaying the base ref's actual migration history from
  empty. This won't catch a bug that only depends on schema state produced by an intermediate
  historical migration rather than the final shape — a narrower gap than the SQLite-vs-MariaDB
  one above, but still a gap.

## Tier 2 — Local integration (you launch the whole platform)

- **What:** the full stack on your machine — Particiapi + Polis server + Polis math +
  Postgres (Docker) **plus** the Flask v2 app — driven end to end.
- **When:** the change touches paths mocked tests can't cover (voting, results, arguments,
  phase transitions, Phase-6 init, identity reveal) and you want to verify **before** staging.
- **How:** the **`local-e2e`** skill. It takes an exclusive lock, brings the stack up, asks
  which flows to drive, exercises them, and **always tears the containers down + releases the
  lock** when finished. State is private to your machine — nothing shared, nothing to clean up
  afterward.
- **Limits:** not the Toolforge front proxy, not multi-worker uwsgi, not real OAuth, not the
  shared staging data. For those, go to tier 3.

## Tier 3 — Staging (deploy any branch to `wiki-polis-dev`)

- **What:** deploy **any branch** to the shared Toolforge staging tool (`wiki-polis-dev`) and
  try it against the real backend. Confirm everything still works end to end.
- **When:** live-backend behaviour local can't reproduce (Toolforge proxy, multi-worker, real
  OAuth, real Polis-math timing), or a human-style smoke before merge.
- **Freedom — staging is a sandbox.** You may deploy any branch, **create new issues**, fix or
  change anything, and mutate data (the `test` conversation is throwaway). You don't need to ask
  permission to experiment on staging the way you would on prod.
- **Deploy:** present the commands for the user to run (you don't have SSH) — see
  `staging-chrome-test` skill, Step 0. `bash ~/wiki-polis/deploy.sh <branch> [--migrate]`;
  restore with `deploy.sh main` when done.
- **Login caveat:** dev-login is **disabled** on staging (#118) — authenticated flows need a
  real Wikimedia OAuth session already in the browser profile, or wait on #223 demo mode. See
  the `staging-chrome-test` skill.

### Database hygiene on staging (hard rule)

**Leave the staging database in a decent state for the next user.** Staging is shared, so a
broken DB blocks everyone after you.

- If you **cause or hit a database error** — a half-applied or failed migration, a phantom
  `alembic_version`, a schema/column mismatch, corrupt rows — **fix it before you leave.** Do
  not walk away from a broken staging DB.
- Recovery moves are documented in `v2/guide_runbook.md` → *Migration fails with "Duplicate
  column" (alembic drift)* (query staging MySQL via SQLAlchemy, repair a phantom
  `alembic_version`, re-run `flask db upgrade`).
- If the DB is broken **beyond a clean fix**, say so explicitly and stop — don't leave it
  silently broken or paper over it. Staging is meant to be rebuildable from the runbook; flag it
  so it can be reset, rather than letting the next user discover it the hard way.
- When you're done, **restore the deployed branch** (`bash ~/wiki-polis/deploy.sh main`) unless
  the user wants your branch left up.

### Test-data isolation (shared environment)

Standard practice for a shared test environment — don't clash with whatever else is there:

- **Namespace what you create.** New conversations / statements / arguments should carry a
  unique, identifiable marker (e.g. a slug like `test-<PR#>-<id>` plus a `[<PR#> staging test]`
  tag) so your data is distinguishable, removable, and not mistaken for someone else's.
- **Prefer the throwaway `test` conversation** for messy or destructive actions; spin up a fresh
  uniquely-named one only when you need isolation from it.
- **No real or sensitive data.** Staging is not anonymised production — never enter real personal
  data, credentials, or anything you wouldn't put in a public test fixture.

## Choosing the tier

- Logic only → **tier 1**.
- Touches the real backend, want a private check first → **tier 2** (`local-e2e`).
- Needs the real deployed/shared environment or a human-style smoke → **tier 3** (`staging-chrome-test`).
- Typical pre-merge flow: **tier 1 always → tier 2 if backend-touching → tier 3 only when needed.**
  `pr-check` orchestrates tier 1 + targeted verification and tells you when a tier-3 human smoke
  is warranted.
