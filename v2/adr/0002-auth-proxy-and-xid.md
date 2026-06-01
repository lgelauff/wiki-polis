# ADR 0002 — OAuth at Flask, auth-disabled Particiapi behind a proxy, xid identity

**Status:** Accepted · **Date:** 2026-05

## Context

Polis/Particiapi has its own auth, but we want a **single login** (Wikimedia OAuth), we
don't want to expose Particiapi publicly, and we need a stable participant identity to
pass to Polis without handing it Wikimedia usernames.

## Decision

- Wikimedia OAuth is handled **entirely by the Flask app** (one consumer registration).
- Particiapi runs with `PARTICIAPI_AUTHENTICATION_DISABLED=True` on an internal network;
  the browser never talks to it directly — **Flask proxies** all voting calls.
- The participant identity passed to Polis is the **xid** = `sha256(mw_user_id)`.

## Consequences

- One login; Particiapi is never publicly reachable — the proxy + internal network are
  the trust boundary.
- The proxy is security-load-bearing (origin checks, `pa_session` cookie rename,
  403→200 rewrite on `/results/`).
- **xid is not anonymous** — Wikimedia user IDs are enumerable, so it's brute-forceable.
  It's an identity *bridge*, not a privacy guarantee
  ([#96](https://github.com/lgelauff/wiki-polis/issues/96)).
