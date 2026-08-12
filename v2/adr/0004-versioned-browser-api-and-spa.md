# ADR 0004 — Versioned browser API and React/TypeScript SPA

**Status:** Accepted · **Date:** 2026-08

## Context

The current browser interface is server-rendered Jinja with forms, redirects, flash
messages, inline JavaScript, and permission-aware template branches. This works as a
single Flask application, but the browser/backend contract is implicit and difficult to
mock, test independently, or replace. Product experiments therefore require knowledge
of Flask route internals even when business behavior is unchanged.

## Decision

- Introduce a same-origin, versioned JSON API under `/api/v1` as the only application
  contract consumed by the future React/TypeScript SPA.
- Keep Flask as the authentication, authorization, application-service, and Polis /
  Particiapi boundary. The browser never calls Polis or Particiapi directly.
- Make OpenAPI 3.1 the machine-readable contract and generate TypeScript client types
  from it once the initial vertical slices stabilize.
- Return capabilities and structured error codes; the frontend must not reproduce
  authorization or phase-transition rules.
- Extract application services incrementally. Existing HTML routes and new API routes
  call the same services during migration.
- Serve and deploy frontend and backend together. Separate hosting or microservices are
  explicitly not required for architectural decoupling.

## Consequences

- The old Jinja frontend can remain live while React replaces it route by route.
- Business rules and transaction boundaries become independently testable.
- API compatibility becomes a maintained product surface; breaking changes require a
  new version or an explicit migration.
- Some near-term duplication at the HTTP presentation layer is accepted while HTML and
  JSON routes coexist, but domain logic may not be duplicated.
