# Wiki-Polis Phase Model — Extension Proposal

> **Status — partially implemented.** Phase 6 (informed voting) was adopted and
> shipped in PR #115 (2026-06-04). Phases 1–5 describe the current production behaviour.
> The data model section (second Polis conversation, mapping fields) reflects the
> implementation. For authoritative current behaviour see
> [`spec_functional-design.md`](spec_functional-design.md).

This document extends the functional design (`spec_functional-design.md`) to formalise the deliberation process as a set of composable phases. It replaces the four-toggle description in the Results section with a richer model that includes a sixth phase: informed voting.

---

## Design philosophy

A conversation does not have to complete every phase. Organizers choose an entry point and an exit point based on the goals of their process. The phases are designed so each one builds meaningfully on the previous, but none is mandatory. The toggles in the admin panel remain the mechanism for enabling each phase — the phase framing is the organizer's mental model for deciding which toggles to flip and in what order.

---

## The six phases

### Phase 1 — Seed

Performed entirely by the organizer before opening the conversation to participants. The organizer seeds an initial set of statements to ensure the voting loop is not empty on day one and to anchor the topic space. These are ordinary statements that participants will vote on alongside any they submit themselves.

No participant interaction in this phase.

### Phase 2 — Statement collection and refinement

**Toggle: Submission open**

The main data-collection phase. Participants vote on statements (agree / disagree / pass) and may propose new statements or suggest refined wording for existing ones. The post-vote triad is active. Opinion clusters form as votes accumulate.

The statement pool grows and evolves during this phase. Participants see no vote counts and no indication of how others voted — each vote is private and uninfluenced.

Organizers can end the process here. The output is a cluster map and a full opinion dataset. This is sufficient for a pure opinion poll.

### Phase 3 — Personal results

**Toggle: Personal results**

Participants can view their own position within the emerging cluster structure, but only for statements they have personally voted on. This is a read-only, reflective phase — no new input is collected. It rewards engagement: the more a participant has voted, the more of the picture they can see.

This phase can run concurrently with Phase 2 (submission still open) or after it closes.

### Phase 4 — Featured statement selection

Performed by the organizer. Using cluster analysis, the system suggests candidate statements that are most representative of the opinion landscape — statements that strongly divide clusters, anchor a cluster's position, or represent points of broad consensus. The organizer reviews these suggestions and confirms or dismisses each one. They may also manually feature any statement regardless of system suggestions.

The result is a small, curated set of statements — typically 8–12 — that will carry the argument mapping and informed voting phases. The quality of this curation directly determines the quality of what follows.

No participant interaction in this phase. Featured statements are not yet visible to participants.

### Phase 5 — Argument mapping

**Toggle: Argument mapping**

The curated featured statements become visible in the argument mapping tab. Participants read, submit, and vote on short pro and con arguments for each featured statement. Arguments are sorted by usefulness votes. There is no threading, no replies.

The argument mapping phase builds the deliberative layer: by the end, each featured statement has a ranked set of pro and con arguments that represent the community's best reasoning on both sides.

Organizers can end the process here. The output is a full argument map on top of the cluster data. This is sufficient for a deliberation process that does not require a final vote.

### Phase 6 — Informed voting

**Toggle: Informed voting**

A second, independent voting round on the featured statements only. This phase has no connection to Phase 2 votes — the slate is clean. Participants who did not take part in Phase 2 can enter here.

The statement set is fixed and small (the featured statements from Phase 4). No new statements can be proposed and no wording changes can be suggested. The post-vote triad does not appear.

Arguments are visible by default while participants consider each statement — the most useful arguments (ranked by Phase 5 votes) are shown prominently. The interface is designed for deliberation first: read the arguments, then vote. Participants vote agree / disagree / pass. Pass remains available and is meaningful data: it indicates a participant has considered both sides and genuinely cannot commit.

Because the statement count is small, the participation barrier is lower than Phase 2. Organizers can reach participants who found the full voting loop too demanding.

**Phase 6 is a commitment.** It should only be enabled once a substantive argument mapping phase has been completed. An organizer who does not want informed voting should end the process after Phase 5 or earlier.

---

## Composable pathways

Organizers are not required to run all six phases. Common pathways:

| Entry | Exit | Process type |
|---|---|---|
| Phase 1 (seed) | Phase 2 | Pure opinion poll — cluster map only |
| Phase 1 (seed) | Phase 3 | Opinion poll with personal reflection |
| Phase 1 (seed) | Phase 5 | Full deliberation — cluster map + argument layer |
| Phase 1 (seed) | Phase 6 | Full deliberative polling cycle — informed re-vote after argument exposure |
| Phase 1 (seed, large set) | Phase 5 or 6 | Organizer provides all statements; Phase 2 submission closed; participants go straight to arguments |

The last pathway — where the organizer provides the complete statement set and keeps submission closed — uses Phase 1 as a heavyweight seed. Participants never propose statements; the organizer defines the full agenda.

---

## Admin panel implications

The toggle panel should group controls by phase and label each group with a short description of what it enables. The current four toggles expand to five (adding informed voting). The recommended activation sequence matches the phase order, but no ordering is enforced.

**Phase 2 — Statement collection**
Toggle: Submission open

**Phase 3 — Personal results**
Toggle: Personal results

**Phase 5 — Argument mapping**
Toggle: Argument mapping

**Phase 6 — Informed voting**
Toggle: Informed voting

Phase 4 (featured statement selection) is an admin action, not a toggle — it is the curation step that unlocks the argument mapping and informed voting phases.

---

## Phase 6 data model

Phase 6 votes are stored in a dedicated Polis conversation, separate from the Phase 2 conversation. When the admin enables Phase 6, the app creates a new Polis conversation and seeds the featured statements into it. Polis handles vote storage and can produce a second cluster map representing post-deliberation opinion.

Because the two Polis conversations assign independent IDs, three mapping fields are needed:

| Field | Location | Purpose |
|---|---|---|
| `phase6_polis_conversation_id` | `Conversation` | The Polis conversation ID created for Phase 6 |
| `phase6_polis_statement_id` | `FeaturedStatement` | The Polis statement ID assigned within the Phase 6 conversation; links back to `polis_statement_id` (Phase 2) via our record |
| `phase6_polis_xid` | `Participation` | The XID used when registering this participant in Phase 6; expected to equal `Participant.xid` but stored explicitly for auditability |

These fields are all nullable and remain null until Phase 6 is initialised.

The argument layer (Phase 5) lives entirely in our database. Polis has no knowledge of arguments — the voting interface injects them from our DB alongside each statement. This is the same pattern used throughout Phase 5.

Phase 4 (argument votes) also stays in our database. Argument votes are usefulness signals on reasoning, not opinion positions, and have no meaningful representation in Polis. Our database is the authoritative store for everything outside the two Polis voting rounds.

The data split is therefore:
- **Polis conversation 1 (Phase 2)**: opinion votes on the full statement pool; source of cluster assignments
- **Our database**: featured statement curation, arguments, argument votes, participant records
- **Polis conversation 2 (Phase 6)**: opinion votes on the featured statement subset; source of post-deliberation cluster assignments

Comparing Phase 2 and Phase 6 — did argument exposure shift opinions? — is a join across both Polis datasets, keyed on `polis_statement_id` / `phase6_polis_statement_id` and on the shared XID.

---

## What is not in Phase 6

- No statement proposals
- No wording suggestions
- No post-vote triad
- No visible vote counts or cluster signals
- No per-vote explanation field (the argument mapping phase already captures reasoning)
