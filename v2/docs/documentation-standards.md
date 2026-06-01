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
| **Deliberate spec** | rarely, on purpose | a decision to change the product | authoritative for how the system is *meant to work*; divergences are bugs/gaps tracked elsewhere | `spec_functional-design.md`, `spec_architecture.md`, `spec_design-principles.md` |
| **Proposal (under discussion)** | during discussion | consensus reached → adopted or rejected | **not** describing what's built; do not implement from it | `prop_phase-model.md` |
| **Forward plan** | often (weekly-ish) | priorities shift | reflects intent, not commitments | roadmap |
| **Append-only history** | never edited retroactively | a release / merge happens | a faithful record; old entries stay as written | changelog / build log |
| **Operational** | when infra changes | provisioning / monitoring / backup changes | must match the live deployment | `guide_deployment.md`, runbook |
| **Public-facing** | rarely, with review | product or policy change | nothing ships without human/comms (and for privacy, legal) review | privacy statement, participant help pages |
| **Draft research** | until verified | a fact-check pass | carries a "not fact-checked" banner until cleared | `docs/research/01–06` |

A doc that mixes classes is the warning sign — that's what produced the
roadmap/changelog tangle. When in doubt, split.

---

## File naming

Encode the **stable role** in the filename via a prefix; keep **mutable lifecycle
status** (draft → active → deprecated → archived) in the top-of-file banner, never in
the name — renaming on every status change rots links and git history. After the
prefix, names are lowercase with hyphens.

| Prefix | Role (lifespan class) | Examples |
|---|---|---|
| `spec_` | deliberate spec — current truth | `spec_functional-design.md`, `spec_architecture.md`, `spec_design-principles.md` |
| `ref_` | tracks-code / external reference | `ref_data-model.md`, `ref_particiapi-api.md`, `ref_web-components.md` |
| `guide_` | how-to for humans | `guide_local-dev.md`, `guide_deployment.md`, `guide_organizer.md`, `guide_contributing.md` |
| `plan_` | forward-looking plan | `plan_roadmap.md`, `plan_doc-improvement.md` |
| `prop_` | proposal under discussion | `prop_phase-model.md` |
| `log_` | append-only history | `log_changelog.md` |
| `pub_` | public-facing participant copy | `pub_privacy.md`, `pub_participant-help.md` |
| `research_` | draft research synthesis | `research_statements.md`, `research_terminology.md` |

- **Role change = deliberate rename.** When a proposal is adopted, `prop_` → `spec_`
  is an intentional rename that signals the transition; update inbound links in the
  same change.
- **Retirement = move, not rename.** Send superseded docs to `archive/` rather than
  renaming them in place — location carries the terminal status.
- **Directory-grouped sets keep the directory as their role marker.** `reference/` and
  `docs/research/` are classified by folder, so files inside them aren't individually
  prefixed (e.g. `reference/particiapi-api.md`, `docs/research/02-…`).

---

## Rules

- **Specs describe intent, not the build.** A `spec_` / `architecture` /
  `design_principles` doc says how the system is *meant to work* — the agreed design.
  Don't narrate current-but-wrong behaviour, and don't compare to superseded designs,
  in a permanent doc. Where intent isn't built yet (or the build diverges), state the
  intended behaviour and flag the gap with a transient `*(pending — …)*` marker. The
  markers **are** the record of known gaps — there is no aggregated deviations list;
  find them with `grep -rn "pending —"`. A marker may link a tracking issue, but isn't
  required to.
- **Operational docs mark per-procedure liveness.** In a runbook/ops doc people follow
  to *run* things, any procedure not yet live or unverified in production carries an
  inline **⚠️ not live yet** tag; unmarked steps are live. Clear the tag once it's been
  run for real. (Different axis from `pending`: `pending` flags a doc/spec gap; **⚠️ not
  live yet** flags operational readiness.)
- **Generate, don't transcribe.** Facts that live in code (the schema, route lists,
  API shapes) should be derived from the source, not hand-copied into prose. A
  hand-copied data model drifted within weeks. Where generation isn't practical, stamp
  the doc with the exact code ref it was verified against and a date.
- **One source per concept.** Each concept has exactly one canonical doc; everything
  else *links* to it instead of restating it. (Product behaviour → `spec_functional-design.md`;
  system shape → `spec_architecture.md`; schema → the data-model reference; what changed →
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
- **Mark transient references.** Inline pointers to open issues/PRs or other
  not-yet-resolved work are *temporary* — they should be removed, or folded into the
  spec as permanent text, once the item resolves. Tag them so they read as provisional
  and are greppable: `*(pending — [#NN](url))*`. Run `grep -rn "pending —" docs/` to
  find everything due for cleanup. Permanent cross-references (to another doc or a
  stable concept) are **not** marked.
- **Public before private only after review.** Anything a participant or the wider
  community will read (privacy, help pages) goes through human review first; privacy
  commitments additionally need legal/policy review.

---

## Current canonical-source map

The one doc to trust for each concept (others should link here, not restate):

| Concept | Canonical source |
|---|---|
| What the app does today (product behaviour) | `spec_functional-design.md` |
| Where the product might go next (not built) | `prop_phase-model.md` (proposal) |
| System shape, components, data flow | `spec_architecture.md` |
| Database schema & data ownership | data-model reference (to be generated from `db.py`) |
| Stable design rules | `spec_design-principles.md` |
| What changed and when | changelog / build-log (to be created) |
| What's planned next | roadmap (to be created) |
| How to run it in production | `guide_deployment.md` + runbook (to be created) |
| How to develop locally | `guide_local-dev.md` |
| Particiapi / web-component externals | `reference/*` (with version stamp) |

This map is itself maintained — when a canonical doc is created or moves, update the
row.
