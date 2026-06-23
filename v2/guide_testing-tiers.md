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
broken DB blocks everyone after you. Staging holds **no real data**, which is what makes the
recovery rules below safe: resetting or rolling back to a prior state is cheap and *expected*,
not a loss.

Two databases sit behind staging — keep them straight:
- **App DB — MySQL on Toolforge ToolsDB** (conversations, participations, audit, `alembic_version`).
  This is where **migration / Alembic** errors happen. **Toolforge keeps no user-accessible backup
  of it** — the ToolsDB replica is failover-only, and any admin restore is a slow Phabricator
  request, not a routine path. **So you are the backup.**
- **Polis backend — Postgres on the VPS** (votes/statements). Separate; it has an *intended* nightly
  `pg_dump` + restore drill (`v2/guide_runbook.md` → *Backups & restore*) — though that's ⚠️ flagged
  not-yet-confirmed-live, so don't assume a recent dump exists.

**Before any risky DB work (a migration, a bulk change) — snapshot first.** Record the current
Alembic head and take a logical dump of the app DB *before* you mutate it. This is what lets you
(a) pinpoint **when/what** broke and (b) roll back to a known-good state. (If the `mysql` /
`mysqldump` CLI hits the known Toolforge TLS error, use the SQLAlchemy approach from the runbook.
The exact ToolsDB dump/restore command isn't yet in the runbook — documenting it is a known gap.)

If you cause or hit a DB error — a half-applied/failed migration, a phantom `alembic_version`, a
schema/column mismatch, corrupt rows — follow this order. **It is bounded: "don't walk away" means
don't leave it *silently* broken; it does NOT mean keep trying forever.**

1. **Roll back to your pre-op snapshot** if you took one — the fastest, cleanest fix.
2. **Otherwise try the documented recovery once or twice** (runbook → *Staging MySQL + Alembic
   gotchas*: query via SQLAlchemy, repair a phantom `alembic_version`, re-run `flask db upgrade`).
3. **If that doesn't take, stop digging.** Repeated blind attempts against a live shared DB can
   make it worse. **Two or three failed attempts is your signal to cease and ask for help**, not to
   keep going.
4. **Reset rather than nurse a hopeless DB.** No real data is at stake — a clean rebuild or restore
   to a prior state is a perfectly good outcome, often better than a half-repaired DB.
5. **Document and escalate clearly.** As you go, **keep a short record of what you ran**; then tell
   the user plainly what broke, what you tried, and what state it's in (and that it needs a reset or
   their input). *Silent* breakage is the only real failure — flagging a DB you can't safely fix is
   the correct, expected ending.

When you're done, **restore the deployed branch** (`bash ~/wiki-polis/deploy.sh main`) unless the
user wants your branch left up.

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
