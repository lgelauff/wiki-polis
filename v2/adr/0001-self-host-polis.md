# ADR 0001 — Self-host Polis + Particiapi instead of hosted pol.is

**Status:** Accepted (v2) · **Date:** 2026-05

## Context

v1 wrapped a *hosted* pol.is conversation in an alpha embed behind Wikimedia OAuth. That
gave us no control over the frontend, the conversation lifecycle, or the data, and the
embed/xid path hit limits. We want full control of the voting UI, an argument layer,
phase toggles, and the data itself (for privacy commitments and export).

## Decision

Self-host the Polis stack — Polis + Particiapi + PostgreSQL — on a Cloud VPS via Docker
Compose, with our own Flask app (on Toolforge) wrapping it. Use **stock** Polis and
**stock** Particiapi (no forks); build only the wrapper.

## Consequences

- Full control of UI, lifecycle, and data; the argument layer and phase model are built
  on top in our app.
- We now run infrastructure — a VPS, backups, upgrades (see the runbook).
- Stock-no-fork keeps us upgradeable; all custom behaviour lives in the Flask app, not in
  Polis.
