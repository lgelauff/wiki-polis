# Documentation standards — wiki-polis

How the project's docs are kept honest. The goal is to stop the drift that built up
during the prototype phase (a prose data model that fell behind the schema; a roadmap
and a changelog tangled in one file; specs that disagreed with each other).

The single most important idea here is **lifespan**: different docs change at
different rates and for different reasons. Knowing a doc's lifespan tells you when it's
allowed to be out of date, what triggers an update, and whether you can trust it today.

---

## Doc lifespans (read this first)

Every doc belongs to one of these classes. New docs should declare their class in a
banner at the top.

| Class | Changes… | Trigger to update | Trust rule | Examples |
|---|---|---|---|---|
| **Tracks-code reference** | whenever the code does | schema / API / dependency change | only trust with a current "verified against `<ref>`" stamp | data-model reference, `reference/particiapi-api.md`, `reference/web-components.md` |
| **Deliberate spec** | rarely, on purpose | a decision to change the product | authoritative for the *current* system | `functional_design.md`, `architecture.md`, `design_principles.md` |
| **Proposal (under discussion)** | during discussion | consensus reached → adopted or rejected | **not** describing what's built; do not implement from it | `phase_model_extension.md` |
| **Forward plan** | often (weekly-ish) | priorities shift | reflects intent, not commitments | roadmap |
| **Append-only history** | never edited retroactively | a release / merge happens | a faithful record; old entries stay as written | changelog / build log |
| **Operational** | when infra changes | provisioning / monitoring / backup changes | must match the live deployment | `deployment.md`, runbook |
| **Public-facing** | rarely, with review | product or policy change | nothing ships without human/comms (and for privacy, legal) review | privacy statement, participant help pages |
| **Draft research** | until verified | a fact-check pass | carries a "not fact-checked" banner until cleared | `docs/research/01–06` |

A doc that mixes classes is the warning sign — that's what produced the
roadmap/changelog tangle. When in doubt, split.

---

## Rules

- **Generate, don't transcribe.** Facts that live in code (the schema, route lists,
  API shapes) should be derived from the source, not hand-copied into prose. A
  hand-copied data model drifted within weeks. Where generation isn't practical, stamp
  the doc with the exact code ref it was verified against and a date.
- **One source per concept.** Each concept has exactly one canonical doc; everything
  else *links* to it instead of restating it. (Product behaviour → `functional_design.md`;
  system shape → `architecture.md`; schema → the data-model reference; what changed →
  the changelog; what's next → the roadmap.) Restatement is how two docs come to
  disagree.
- **Decisions get an ADR, not just a commit message.** The expensive question a future
  maintainer asks is "why is it like this?" Record non-obvious decisions (one short
  file each) so the answer isn't buried in git history.
- **Separate lifespans.** Don't put fast-moving and slow-moving content in one file.
  Roadmap, changelog, spec, and reference all change for different reasons — keep them
  apart.
- **Status banners.** Every doc states its class and status at the top. Drafts keep a
  "not fact-checked" banner until verified; references carry a "last verified" date;
  proposals say "under discussion, not yet adopted."
- **Public before private only after review.** Anything a participant or the wider
  community will read (privacy, help pages) goes through human review first; privacy
  commitments additionally need legal/policy review.

---

## Current canonical-source map

The one doc to trust for each concept (others should link here, not restate):

| Concept | Canonical source |
|---|---|
| What the app does today (product behaviour) | `functional_design.md` |
| Where the product might go next (not built) | `phase_model_extension.md` (proposal) |
| System shape, components, data flow | `architecture.md` |
| Database schema & data ownership | data-model reference (to be generated from `db.py`) |
| Stable design rules | `design_principles.md` |
| What changed and when | changelog / build-log (to be created) |
| What's planned next | roadmap (to be created) |
| How to run it in production | `deployment.md` + runbook (to be created) |
| How to develop locally | `local-dev.md` |
| Particiapi / web-component externals | `reference/*` (with version stamp) |

This map is itself maintained — when a canonical doc is created or moves, update the
row.
