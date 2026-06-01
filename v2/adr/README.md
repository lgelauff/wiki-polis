# Architecture Decision Records (ADRs)

Short, dated records of *why* non-obvious decisions were made, so the reasoning isn't
buried in commit history. One file per decision: **Context · Decision · Consequences.**
Superseded ADRs stay (their status changes) — we don't delete them.

The **doc-effort** decisions (D-PHASE, D-PRIV, D-STORE, D-NAMING, …) live in the
decisions register in [`../docs/plan_doc-improvement.md`](../docs/plan_doc-improvement.md);
the ADRs here capture the **architectural / product** decisions.

| # | Decision | Status |
|---|---|---|
| [0001](0001-self-host-polis.md) | Self-host Polis + Particiapi instead of hosted pol.is | Accepted |
| [0002](0002-auth-proxy-and-xid.md) | OAuth at Flask; auth-disabled Particiapi behind a proxy; xid identity | Accepted |
| [0003](0003-identity-pseudonyms-and-reveal.md) | Per-conversation pseudonyms + opt-in permanent reveal | Accepted |

**To backfill:** refactor-not-rewrite (from the audit's refactor plan); phase model kept
as a separate proposal (D-PHASE); two read-paths to one Polis store (D-STORE).
