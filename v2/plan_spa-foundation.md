# SPA foundation and migration plan

> **Forward plan — active, 2026-08.** This records dependency order and acceptance
> criteria, not shipped behavior. Architecture decision: [ADR 0004](adr/0004-versioned-browser-api-and-spa.md).

## Outcome

A React/TypeScript frontend can be developed against generated types and realistic mocks
without reading Flask internals or running Polis. Flask remains the same-origin backend,
owns all authorization and transactions, and exposes Polis only through application-level
contracts.

## Architectural rules

1. OpenAPI 3.1 is the public browser contract; SQLAlchemy and upstream Polis shapes never
   cross it.
2. API reads return capabilities, not inputs from which the browser re-derives permission.
3. API commands return updated state or structured errors, never flash-and-redirect.
4. Application services own use cases and transaction boundaries; HTML and JSON adapters
   are thin callers.
5. The browser owns transient presentation state. Flask/Polis own durable and server state.
6. Same-origin session cookies + CSRF remain the authentication model.
7. Commands that may be retried define idempotency and concurrency behavior explicitly.

## Work sequence

### 0. Guardrails and behavior baseline

- Add critical Playwright journeys for login, join, vote, argument, phase transition, and
  moderation before replacing their UI.
- Add the Jinja/CSS syntax gates from [#300](https://github.com/lgelauff/wiki-polis/issues/300).
- Make a Phase-6-ready local fixture turnkey ([#301](https://github.com/lgelauff/wiki-polis/issues/301)); avoid duplicating the active implementation in [PR #302](https://github.com/lgelauff/wiki-polis/pull/302).
- Preserve accessibility assertions while retiring templates ([#157](https://github.com/lgelauff/wiki-polis/issues/157)).

**Exit:** critical behavior can be verified locally and in CI without hand-built data.

### 1. API kernel and identity boundary — in progress

- Versioned `/api/v1`, OpenAPI document, success/error conventions, request IDs, and
  no-store caching for user-specific responses.
- Session/current-user contract with CSRF token and site-wide capabilities.
- Keep stored xid immutable after participant creation ([#290](https://github.com/lgelauff/wiki-polis/issues/290)); never expose xid, Wikimedia numeric IDs, or identity linkage in browser DTOs.
- Audit pseudonym/username boundaries while defining DTOs ([#261](https://github.com/lgelauff/wiki-polis/issues/261), [#96](https://github.com/lgelauff/wiki-polis/issues/96)).

**Exit:** a generated/mock client can distinguish anonymous, authenticated, and demo
sessions without duplicating auth rules.

### 2. Application-service and command foundation

- Extract use cases from Flask handlers, beginning with invitations and flagging.
- Standardize validation errors (`code`, `message`, optional field details).
- Define SQLAlchemy transaction ownership and nested/savepoint policy.
- Make invite batches non-destructive under concurrency and report partial outcomes
  ([#242](https://github.com/lgelauff/wiki-polis/issues/242), [#241](https://github.com/lgelauff/wiki-polis/issues/241)).
- Enforce flag invariants server-side ([#299](https://github.com/lgelauff/wiki-polis/issues/299)).
- Normalize unavailable/unconfigured upstream errors ([#237](https://github.com/lgelauff/wiki-polis/issues/237)).

**Exit:** HTML and JSON adapters invoke the same transactional commands and receive typed
outcomes rather than interpreting exceptions.

### 3. Participant read model

- Conversation lanes/listing, detail, participation status, phase state, scheduled
  transition, and capability DTOs.
- Move participant-specific bucketing into a tested read-model service while addressing
  [#253](https://github.com/lgelauff/wiki-polis/issues/253) and [#270](https://github.com/lgelauff/wiki-polis/issues/270).
- Add conversation information and output DTOs with privacy-safe aggregation
  ([#277](https://github.com/lgelauff/wiki-polis/issues/277), [#222](https://github.com/lgelauff/wiki-polis/issues/222)).

**Exit:** the main participant screens run entirely from mockable API reads.

### 4. Participant commands

- Join/accept, vote, statement, argument, importance vote, flag, and reveal commands.
- Keep Particiapi session/CSRF/cookie translation inside Flask.
- Specify idempotency and 409 conflict responses for double-submit and phase changes.

**Exit:** one React participant journey reaches feature parity without direct proxy or
Jinja dependencies.

### 5. Admin contracts

- Conversation lifecycle, phase transitions, statements/import, featured selection,
  participants, roles, invitations, moderation, and reports.
- Model long-running/upstream-dependent commands explicitly rather than mirroring forms.

**Exit:** the admin SPA needs no HTML endpoints and every mutation has an audit/transaction
test.

### 6. React/TypeScript platform and strangler migration

- Strict TypeScript, generated API client, TanStack Query for server state, accessible
  component primitives, existing message catalogs, Storybook/fixture scenarios, and
  Playwright parity tests.
- Build route-by-route behind an explicit switch; participant reads first, the complex
  conversation workflow later, and admin last.
- Remove each Jinja route only after its parity and accessibility checks pass.

## Delivery slices

| Slice | Deliverable | Indicative effort |
|---|---|---:|
| A | API kernel + session + identity invariant | 3–5 days |
| B | Service/error/transaction conventions + first command | 5–8 days |
| C | Participant read API + generated TS client/mocks | 8–12 days |
| D | Participant command API | 10–15 days |
| E | Admin API | 15–25 days |

The backend foundation is about 6–10 engineer-weeks. The React parity migration remains
roughly 10–14 additional engineer-weeks; design exploration is separate.

## Definition of done for every endpoint

- OpenAPI request/response/error schemas and stable operation ID.
- Capability/authorization computed server-side.
- No ORM/upstream objects or sensitive identifiers serialized.
- Contract, authorization, transaction rollback, and concurrency tests as applicable.
- Generated fixture usable without Flask/Polis.
- Request ID in logs and a documented cache/idempotency policy.
