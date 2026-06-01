# Design Principles

These are stable. They should not be re-debated in each session; challenge them only if a new constraint forces a genuine trade-off.

## Core interaction model

1. **Voting loop is dominant.** See statement → Agree / Disagree / Pass → optional "propose a better alternative" → continue. Everything else is secondary.
2. **Statements are atomic.** One claim, one vote. No compound statements.
3. **No threading.** Arguments exist but are non-threaded, short, and accessible only via a separate tab.
4. **No herding.** Users do not see who voted what. Voter identity is hidden.

## Participation design

5. **Low friction.** Participating must be fast. Extra UI must not interrupt the voting loop.
6. **Curiosity-driven.** Discovery happens by engaging, not by browsing a social feed.
7. **Recurring.** Users should have reasons to return: new statements, new arguments, evolving clusters.

## What to avoid

8. **No Reddit dynamics.** No nested replies, no upvote races, no quote wars.
9. **No RfC dynamics.** No procedural debates, no closure pressure, no mixing voting and negotiating.
10. **No social signaling.** No likes, follower counts, or identity markers on votes.

## Wikimedia integration

11. **Wikimedia OAuth is the only login.** No separate accounts.
12. **xid bridges identities.** Wikimedia user ID → SHA-256 xid → Polis participant.
13. **Moderation follows Polis model.** Statement-level moderation (hide/show), not user silencing.

## Build discipline

14. **Phases are stable checkpoints.** Don't blend phases. Each phase must be independently deployable.
15. **No premature abstraction.** Build for the current phase; refactor when a real need emerges.
16. **Polis is the deliberation engine.** Don't reimplement clustering, PCA, or vote math. Own the wrapper, not the engine.
