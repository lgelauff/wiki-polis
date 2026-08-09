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
- The participant identity passed to Polis is the **xid**. Originally `sha256(mw_user_id)`;
  since the [#96](https://github.com/lgelauff/wiki-polis/issues/96) fix it is an **HMAC**
  keyed by a server secret — `xid = HMAC(secret, mw_user_id)`, versioned by
  `xid_key_version` (v2 is the default; v1 is the legacy plain-sha256 form). What is
  actually forwarded to Particiapi/Polis is a further **conversation-scoped** subject,
  `HMAC(secret, "{xid}:{conv.id}")`, so the same person resolves to a *different* Polis uid
  in each conversation (no cross-conversation linkage).

## Consequences

- One login; Particiapi is never publicly reachable — the proxy + internal network are
  the trust boundary.
- The proxy is security-load-bearing (origin checks, `pa_session` cookie rename,
  403→200 rewrite on `/results/`).
- **xid is an identity bridge, not anonymity.** The plain-`sha256` form was
  enumerable/brute-forceable from public Wikimedia user IDs; HMAC keying (the "salt the
  hash" half of [#96](https://github.com/lgelauff/wiki-polis/issues/96)) removes that, and
  conversation-scoping prevents cross-conversation correlation. The *other* half of #96 —
  rotating/deleting the xid↔uid mapping at the data-retention window — is **not confirmed
  done**; treat it as still open until verified.
