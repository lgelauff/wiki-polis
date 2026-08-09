# ADR 0003 — Per-conversation pseudonyms + opt-in permanent reveal

**Status:** Accepted (reveal model clarified — decision D-PRIV) · **Date:** 2026-06

## Context

Participants vote under an identity that other participants and the public may see in
results, but votes must stay private during collection (anti-herding), and we don't want
a participant trackable across conversations.

## Decision

- Each participant picks a **pseudonym per conversation**, unique platform-wide and never
  reused — so a pseudonym can't link a person across conversations.
- During collection, no one sees who voted what; results are aggregate.
- After a conversation closes, a participant may **voluntarily and permanently** attach
  their Wikimedia username to their pseudonym (opt-in reveal; irreversible by their own
  choice).
- The **internal** account↔pseudonym link is removed within 180 days of close for
  participants who did *not* reveal (data minimisation).

## Consequences

- Strong per-conversation privacy; reveals are deliberate and permanent.
- Reveals are permanent in code: there is no longer any nullification path (the earlier
  ~60-day nullify was removed). Reveal *timing* is gated by a cooldown / opt-in window
  (`_REVEAL_COOLDOWN_DAYS` / `_REVEAL_WINDOW_DAYS`), but a reveal is never undone afterward.
- The 180-day account↔pseudonym link removal (data minimisation) depends on the
  xid-mapping rotation half of [#96](https://github.com/lgelauff/wiki-polis/issues/96),
  which is **not confirmed done** — see ADR 0002.
