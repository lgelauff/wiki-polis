# Wiki-Polis v2

The live wiki-polis app. Replaces the retired hosted pol.is embed with a self-hosted
Polis + Particiapi stack.

Start here: [`guide_local-dev.md`](guide_local-dev.md) to run it,
[`guide_testing-tiers.md`](guide_testing-tiers.md) to test it, and
[`docs/route_authorization_matrix.md`](docs/route_authorization_matrix.md) if you are
reviewing a route or an authorization change.

## How it fits together

- Flask on Toolforge: Wikimedia OAuth, conversation administration, roles, arguments,
  vouchered/demo access, and a same-origin JSON API at `/api/v1/*`.
- React 19 SPA in [`frontend/`](frontend/) — the only browser surface. Flask serves the
  shell document; the SPA owns client routing and types itself from
  [`openapi.json`](openapi.json).
- Polis + Particiapi on a VPS: statements, votes, clustering. They are reached
  server-side only; the browser never talks to them.
- MariaDB (ToolsDB) in prod, SQLite in dev: conversations, participants, participations,
  roles, arguments, vouchers, audit events. Schema in
  [`ref_data-model.md`](ref_data-model.md).

Full picture and the reasoning behind it:
[`spec_architecture.md`](spec_architecture.md).

## Documents

Following the classes and naming rules in
[`docs/documentation-standards.md`](docs/documentation-standards.md).

| File | Class | Purpose |
|---|---|---|
| `spec_functional-design.md` | deliberate spec | Full product specification — what the platform does, from the user's perspective |
| `spec_architecture.md` | deliberate spec | Technical architecture, components, data flow, technology decisions |
| `spec_design-principles.md` | deliberate spec | Stable design rules — not to be re-debated per feature |
| `spec_accessibility.md` | deliberate spec | Accessibility conventions; states plainly that they are unenforced today |
| `ref_data-model.md` | tracks-code | Database schema reference (derived from `db.py`) |
| `ref_polis-data-model.md` | tracks-code (external) | Polis's own Postgres schema, and how wiki-polis writes into it |
| `ref_polis-routing.md` | tracks-code (external) | How a Polis conversation id is derived and routed |
| `ref_cross-device-identity.md` | tracks-code | The `PARTICIAPI_SUB_SECRET` ↔ `TRUSTED_SUB_SECRET` trusted-subject mechanism |
| `docs/route_authorization_matrix.md` | tracks-code | Which route requires which authorization. Verified against a named commit; see its banner for how to keep it true |
| `docs/documentation-standards.md` | operational | Doc lifespans, naming rules, and the canonical-source map |
| `openapi.json` | contract | The browser/API contract. The SPA's TypeScript types are generated from it |
| `log_changelog.md` | append-only | What was built, and when. Never edited retroactively |
| `plan_roadmap.md` | forward plan | What's planned next — intent, not commitment |
| `plan_i18n.md` | forward plan | The i18n workstream |
| `plan_spa-foundation.md` | forward plan | The SPA migration plan (largely shipped; kept for context) |
| `guide_local-dev.md` | operational | Local development: docker backend + Flask + SPA |
| `guide_testing-tiers.md` | operational | The three test tiers, and how to run tier 1 |
| `guide_deployment.md` | operational | Step-by-step deployment (Toolforge + VPS) |
| `guide_runbook.md` | operational | Day-2 operations and incident response |
| `guide_logging.md` | operational | Structured logging, redaction, Loki/Grafana |
| `i18n/README.md` | operational | How message catalogues work and how to translate |
| `embedding_sidecar/README.md` | operational | The optional semantic-similarity service |
| `frontend/README.md` | operational | The SPA's own build and layout |
| `adr/` | decisions | One file per non-obvious "why is it like this?" |
| `reference/particiapi-api.md` | external reference | Particiapi API notes, with a version stamp |
| `ops/` | operational | uWSGI config, backup scripts, logging stack, load and smoke tooling |
| `pub_privacy.md` | **public-facing** | Privacy and data-handling statement (draft, pre-publication — needs review) |

> The organizer guide and participant help live in
> [`/guidance`](../guidance/) —
> [`../guidance/guide_organizer.md`](../guidance/guide_organizer.md),
> [`../guidance/pub_participant-help.md`](../guidance/pub_participant-help.md),
> [`../guidance/statement-helper-prompt.md`](../guidance/statement-helper-prompt.md).
> `pub_privacy.md` and the participant help page change only with human review.

## Directories

| Directory | Purpose |
|---|---|
| `api/` | The two JSON blueprints: participant (`v1.py`) and admin (`admin_routes.py`). Thin adapters — request validation and error envelopes, no authorization logic |
| `services/` | Domain logic, one module per feature. This is where authorization decisions and business rules live |
| `frontend/` | The React SPA: `src/api` (generated client + queries), `src/features` (admin / participant / results), `src/i18n` |
| `tests/` | pytest suite; SQLite per test, no services required |
| `migrations/` | Alembic chain (`versions/`). One head — see the runbook if a deploy reports drift |
| `i18n/` | Message catalogues (`en`, `nl`, `qqq` documentation) and the translatewiki group |
| `embedding_sidecar/` | Optional FastAPI + sentence-transformers service for statement similarity |
| `static/` | Flask-served assets: `img/`, `fonts/`, `redesign.css`, `style.css`, and `spa/` (the built bundle, git-ignored) |
| `ops/` | uWSGI config (`uwsgi.ini`), Postgres/ToolsDB backup scripts, Loki/Grafana config, and the load/smoke/repair tooling |
| `docs/` | Documentation standards and the route authorization matrix |
| `reference/` | External API references |
| `adr/` | Architecture decision records |
| `figures/` | Diagrams |

`cache/`, `tmp/`, `archive/`, `private/` and `design_handoff_propose_and_arguments/` are
git-ignored, so they are absent from a fresh clone.

## Tests and lint

```bash
cd v2
export DATABASE_URL="sqlite:///:memory:"
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export FLASK_DEBUG=1
uv sync && uv run pytest -q
uvx ruff check .          # pyflakes only

cd frontend && npm ci && npm run typecheck && npm test && npm run build
```

The three environment variables are required because `app.py` builds the app at import
time; `guide_testing-tiers.md` explains why `FLASK_DEBUG=1` is the non-obvious one.
