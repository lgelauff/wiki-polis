# Logging guide (contributor reference)

How logging works in wiki-polis and the rules for adding log statements. This is the
Phase 1 (foundation) slice; audit logging (Plan 2) and engagement instrumentation
(Plan 4) are documented separately when they land. The design rationale was captured in
an internal planning doc that was never committed to the repo.

## Where logs go

- **Dev / tests:** human-readable text on stderr, e.g.
  `2026-06-11 12:00:00 INFO [a1B2c3 pid=None] app: GET / -> 200 (4.1ms)`
- **Production (Toolforge):** one JSON object per line on stderr → `uwsgi.log`, e.g.
  `{"timestamp": "...", "level": "INFO", "service": "wiki-polis", "logger": "app", "message": "...", "request_id": "...", "participant_id": 42}`
  Format is chosen by `_on_toolforge` (the `TOOL_TOOLFORGE_API_URL` env var) — **not** by
  debug mode, so tests always get text.
- **Optional central aggregation:** set `LOKI_URL` to also send the same redacted JSON
  line to Loki through an async queue. The handler uses `RedactingJsonFormatter`, so the
  network copy has the same redaction backstop as `uwsgi.log`.

Configuration is in `logging_setup.py` (`configure_logging`), called once in `create_app`
before extensions init. It configures the **root** logger imperatively (no `dictConfig`),
so every logger — `app.logger`, `polis_admin`'s module logger, `werkzeug` — flows through
the same handler. Don't add per-module handlers.

## Central log aggregation (#49)

The supported aggregation path is additive:

- VPS containers: Fluent Bit tails Docker stdout and forwards to Loki.
- Toolforge Flask: the app posts already-redacted JSON records directly to Loki.
- Grafana reads Loki for a single time-ordered diagnostics view.

Configure Toolforge with:

| Variable | Purpose |
|---|---|
| `LOKI_URL` | HTTPS endpoint ending at either the Loki base URL or `/loki/api/v1/push` |
| `LOKI_USERNAME` / `LOKI_PASSWORD` | basic-auth credentials for the VPS nginx Loki endpoint |
| `LOKI_LABELS` | optional comma-separated low-cardinality labels, e.g. `stack=toolforge` |
| `LOKI_QUEUE_SIZE` | optional async queue size; default `1000` |
| `LOKI_TIMEOUT` | optional POST timeout in seconds; default `2.0` |
| `WIKI_POLIS_ENV` | optional environment label, e.g. `staging` or `prod` |

The Loki stream label `service="wiki-polis"` is forced by code and cannot be overridden.
Do not put `request_id`, `participant_id`, usernames, `xid`, statement text, or vote
values in Loki labels; `request_id` and `participant_id` stay inside the JSON line only.
Loki is diagnostic only with short retention. Audit events remain in the app DB and
engagement instrumentation must not be routed to Loki for convenience.

VPS sample config lives in `ops/logging/`:

- `docker-compose.loki.yaml`
- `loki-config.yaml` (30-day retention)
- `fluent-bit.conf` / `parsers.conf`
- `nginx-loki-grafana.conf`

## Levels — use them consistently

| Level | When | Example |
|-------|------|---------|
| `DEBUG` | Dev-only detail; never relied on in prod | tracing a value while developing |
| `INFO` | Normal operation worth a record | `request complete`, `startup`, a phase transition |
| `WARNING` | Soft failure / degraded but handled | a non-fatal external call failed and we fell back |
| `ERROR` / `logger.exception` | Hard failure | an unhandled exception (Flask logs these for you) |

Prefer `current_app.logger` in request code. Unhandled exceptions are logged by Flask
itself — **don't** add your own catch-all 5xx logger (it would double the stack).

## Request correlation

Every record automatically carries:
- `request_id` — minted per request (`secrets.token_urlsafe(8)`). An inbound `X-Request-Id`
  is honoured **only** behind a trusted proxy (`TRUST_PROXY_HEADERS`) and only if it matches
  `^[A-Za-z0-9_-]{1,64}$`; otherwise a fresh one is minted. It is echoed in the response
  `X-Request-Id` header.
- `participant_id` — the internal participant id, **best-effort** (only present when the
  request already resolved `g.participant`; the logging path never issues a query). This is
  how an error log ties back to the user who hit it.

Both are injected by a `LogRecord` factory, so they appear on *every* record (including
Flask's exception logs and pytest's `caplog`).

## Privacy — hard rules

- **Never log** statement text, vote values/direction, raw `xid`, `mw_user_id`,
  Wikimedia username, email, session contents, secrets, or tokens.
- Reference a participant by **internal `participant_id` only** — never their username/xid.
- A minimal `RedactingFormatter` scrubs URL-embedded credentials, sha256/`xid`-shaped hex,
  and `key: value` secrets (authorization / cookie / token / password / api-key) from the
  final line **including tracebacks**. This is a backstop, **not** a licence to log
  sensitive data — the full redaction catalogue is Plan 3. See `tests/test_logging.py`.
- The startup fingerprint logs only the DB **scheme** (`make_url(...).drivername`) and
  booleans — never a URL with a password or any credential.

## Audit events (#135)

Admin/moderation **write** actions are recorded in the append-only `audit_events` table
(durable governance trail) via `record_audit(...)`, which also emits a correlated
`audit <operation>` log line.

- **Call it after the action commits** — so a rolled-back action leaves no audit row.
- **Privacy contract — ids / enums / counts ONLY.** Never put statement text, vote values,
  usernames, `xid`, or any PII in `target_id` or `detail`. The audit *row* is not run through
  the RedactingFormatter (that only scrubs the log line) — this discipline is the control, and
  `tests/test_audit.py` enforces it. Reference participants by internal `participant_id`.
- **Admin identity is recorded openly** (`actor_participant_id`): an admin acting in an official
  capacity has a reduced expectation of privacy (privacy-statement disclosure #2). This is the
  one place a name-resolvable id is deliberately retained long-term.

Canonical operation names (keep stable; add here when you add a route):
`conversation.create|edit|pause|close`, `phase.set`, `phase.advance`, `phase6.init`,
`global_admin.grant|revoke`, `role.grant|revoke`, `invite.add|remove`,
`statement.moderate|seed|seed_import`, `strict_moderation.set`,
`featured.confirm|add|remove`, `argument.delete`.

## Adding a log statement — checklist

1. Right level (table above)?
2. No PII / secrets / vote content in the message or its `%`-args?
3. Reference participants as `participant_id`, not username/xid?
4. In the request path, no DB query just to enrich a log line.
