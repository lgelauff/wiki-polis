# Documentation Improvement Plan — wiki-polis

_Prepared 2026-06-01. Scope: take wiki-polis documentation from its current state
(planning docs written during the build) to a coherent, maintainable set that can
carry the software to maturity — covering internal technical docs, operator/admin
material, and participant-facing copy._

This is a **plan**, not the docs themselves. Each item below states audience,
the decisions that must be settled before writing, rough scope, and dependencies.

---

## 0. How this plan was produced & two corrections to the brief

Read: every tracked `v2/*.md`, `v2/reference/*`, the repo-root `README.md` /
`plan.md` / `notes.md`, `docs/research/01–06`, and the audit artifacts. Cross-checked
against `db.py`, the live route map, open issues (#11–#94) and recent PRs.

Two things the originating brief got slightly wrong — worth fixing in everyone's
mental model:

1. **The two audit files named in the brief are not on `main`.** There is no
   `v2/audit/codebase-audit.md` or `v2/audit/refactor-plan.md` in the working tree.
   They live on branch `docs/audit-and-refactor-plan` in **open PR #94**, alongside
   `runtime-audit.md`. The whole `v2/audit/` directory is **git-ignored** (see
   `.gitignore`). **Resolved (D-AUDIT):** merge PR #94 to keep the audits in version
   control, but treat them as a *point-in-time* record — archive or delete once
   obsolete — and migrate their durable findings into the maintained docs. See N1.
2. **The "three open questions" are in `spec_functional-design.md` itself**, not in the
   audit. They are the §"Open questions (not yet decided)" under the voting state
   machine: (a) should "change vote" reopen voting or silently allow Polis re-vote;
   (b) should "Submitted" auto-advance; (c) is a required "Move on" click the right
   friction. These are tracked as resolvable decisions in this plan (see Decisions D-VOTE).

The audit content itself is solid and is treated here as the technical ground truth
the user-facing and architecture docs must be reconciled against.

---

## 1. Current documentation inventory

| Doc | Audience | Tracked? | State |
|---|---|---|---|
| `README.md` (root) | newcomer / contributor | yes | **Stale** — still frames v1 as "live" and v2 as "in development"; see §2 |
| `v2/README.md` | contributor | yes | OK as a doc index; minor drift (references archived dirs) |
| `v2/spec_architecture.md` | maintainer | yes | **Partly stale** — data model out of date (C3); "phase plan" reads as a roadmap though the build is done. Documents *current* toggles only (6-phase model stays in the proposal, per D-PHASE) |
| `v2/spec_functional-design.md` | product / organizer / maintainer | yes | Mostly current; the 3 open questions are now resolved (D-VOTE); still carries a dual (old + current) voting spec to collapse |
| `v2/spec_design-principles.md` | everyone | yes | Stable & good; one gap (informed voting / deliberation depth) |
| `v2/next_steps.md` | maintainer | yes | **Conflated** — half roadmap, half changelog; step numbering broken (no Step 3); contains resolved TODOs |
| `v2/prop_phase-model.md` | product / maintainer | **no (untracked)** | Forward-looking proposal, under discussion (D-PHASE) — kept *separate* from current-truth specs; needs a status banner + tracking |
| `v2/guide_deployment.md` | maintainer | yes | Strong & detailed; missing the staging tool, monitoring/runbook, secrets rotation |
| `v2/guide_local-dev.md` | contributor | yes | Current and good |
| `v2/reference/particiapi-api.md` | maintainer | yes | Reference snapshot (2026-05-11); needs a "verified against version X" stamp |
| `v2/reference/web-components.md` | maintainer | yes | Same as above |
| `plan.md` (root) | maintainer | yes | Deployment plan w/ a "current state" table that goes stale fast; overlaps next_steps + deployment |
| `notes.md` (root) | maintainer | yes | Early research notes; largely superseded by `docs/research/` |
| `docs/research/01–06` (root) | organizer / product | yes | Useful synthesis, all marked **"Draft — not fact-checked"**; `05-website-copy.md` is the source for participant copy (issue #57) |
| `v2/audit/codebase-audit.md` | maintainer | no (PR #94) | Accurate static audit; ground truth for refactor |
| `v2/audit/runtime-audit.md` | maintainer | no (PR #94) | Accurate runtime audit |
| `v2/audit/refactor-plan.md` | maintainer | no (PR #94) | Steps 1–4 done (PR #88); 5–9 = issues #89–93 |
| `v2/audit/walk-1.md` | maintainer | no | Browser walk of public/entry paths |

**Missing entirely** (no doc exists): privacy policy / data-handling statement,
organizer guide, operator runbook (incident/restore/monitoring),
data-model & API reference derived from code, CONTRIBUTING / testing guide, security
& threat model, participant help pages (only draft copy exists), CHANGELOG, a docs
home/index, and an ADR (decision record) trail.

---

## 2. Cross-cutting problems to fix first

These affect multiple docs and should be resolved before fine-grained editing.

- **C1 — v1/v2 "live" drift (decided: see D-V1).** Despite merged PR #87 ("correct
  stale v1/v2 labelling"), the root `README.md` Project-structure block on `main`
  still labels root `app.py` as "Flask app (v1, live)" and `v1/` as "Current live
  deployment," while `wsgi.py` / `deploy.sh` / `v2/guide_deployment.md` all deploy **v2**.
  **Resolution (per maintainer):** v1 is a historical **archive** only — not expected
  to be used or maintained; **v2 is where the app lives** and where design happens; a
  **v3 may follow** someday. The README needs a **full review** so it reflects this
  plainly, but v1's archive status should be a brief footnote, not a prominent theme.
  This is the single most misleading sentence in the docs and is cheap to fix.
- **C2 — Two phase docs, intentionally separate (decided: see D-PHASE).**
  `spec_functional-design.md` (4 toggles) and `prop_phase-model.md` (6 phases incl.
  informed voting) are **not** rival drafts to be merged. **Resolution (per
  maintainer):** `spec_functional-design.md` is the **source of truth for the current,
  implemented version**; `prop_phase-model.md` is a **forward-looking proposal,
  currently under discussion with colleagues** and seeking consensus before any
  implementation. The fix is therefore **labelling, not merging**: each doc must state
  its status up front (current-truth vs proposal-under-discussion), and current-truth
  docs must not absorb the unimplemented model. Open issues #78/#79/#83 belong to the
  *forward* track and should be tagged as not-yet-adopted so they don't read as
  committed work.
- **C3 — Data model documented in prose has drifted from `db.py`.**
  `spec_architecture.md` lists a data model missing `paused`, `closed_at`,
  `public_username`, `revealed_at`, `argument_vote_method`, `argument_vote_data`,
  `ArgumentSideState`, and the proposed `phase6_*` fields. Prose data models rot;
  this one already has. The fix is structural (see N3), not a one-time edit.
- **C4 — Roadmap and history are tangled (decided: split).** `next_steps.md` mixes
  "what to build next" with "what we built and how we fixed it." Forward planning and
  history have different audiences and lifespans. **Resolution (per maintainer):**
  split them. Completed work moves into a clearly-marked **historical section** so
  humans can see at a glance what is outdated vs current and discuss it without it
  *accidentally informing future decisions*; `next_steps.md` (→ roadmap, N7) then
  contains only genuine next steps. A **CHANGELOG (N8)** is welcome as the
  best-practice form of that historical record — the historical section and the
  changelog can be the same artifact.
- **C5 — Doc home / navigation.** There are now ~20 docs across three locations
  (root, `v2/`, `docs/research/`). There is no single entry point that says "if you
  are X, read Y." `v2/README.md` is the closest but only indexes `v2/`.

---

## 3. Per-existing-doc assessment

### `README.md` (root)
- **Gaps/stale:** C1 above; "Project structure" block lists only the root app's
  files and omits the v2 tree that actually ships; no link to deployment, local-dev,
  or functional design; no status/badges; no "what is this / who is it for."
- **Decision (settled, D-V1):** v1 is kept as a **historical archive** — not deleted,
  not maintained, not expected to be used. v2 is the live app. A future v3 is possible
  but is not a documentation concern today.
- **Scope:** full review → rewrite to ~1 page: one-line pitch, accurate architecture
  diagram, "run it locally" + "deploy it" links, doc map, project status. Mention v1's
  archive status only as a brief footnote — don't make it a theme. Audience: first-time
  visitor.

### `v2/README.md`
- **Gaps:** indexes only `v2/`; doesn't point to root research docs, the audits, or
  participant/operator material that this plan adds.
- **Scope:** small — extend the index after the new docs exist; or fold into the
  top-level doc home (C5 / N0).

### `v2/spec_architecture.md`
- **Gaps/stale:** describes the **current** system, so it documents the 4 implemented
  toggles only (the 6-phase model stays in the proposal, per D-PHASE — at most a
  forward pointer); C3 (data model out of date); "Phase plan" §135–164 reads as a
  build roadmap but the build is largely done — it should describe the *system as
  built*, not a forward plan. Does not capture the **data-ownership reality** the
  runtime audit found (SQLite vs Polis-Postgres vs Particiapi-HTTP serve the *same*
  concept to different callers; the much-discussed PG→HTTP fallback never fires while
  PG is up). Does not mention the staging deployment.
- **Decisions before editing:** D-STORE (document the dual-store statement reads as
  intended design or as tech-debt to remove).
- **Scope:** medium rewrite. Keep the system diagram (good), refresh the tech table,
  **replace the prose data model with a link to the generated data-model reference
  (N3)**, add a data-ownership section sourced from the runtime audit, drop the
  "phase plan as roadmap" framing in favour of "architecture as built" + a pointer to
  the roadmap (N7).

### `v2/spec_functional-design.md`
- **Role (decided):** this is the **source of truth for the current, implemented
  version**. It should describe what the app does *today* and must not absorb the
  forward-looking phase model (that stays in `prop_phase-model.md`). Add a short
  status banner saying exactly this, with a pointer to the proposal for "where this may
  go next."
- **Gaps:** the §Voting section keeps both the superseded original spec and the
  current state machine — the stale half should move to history (N8); 3 open questions
  (D-VOTE) still embedded; "information-gain routing" is described aspirationally but
  isn't implemented (noted in next_steps but not here); several behaviours now have
  authoritative issues (#69 change-vote, #70 closed-window date, #11/#12 arguments
  unlock) that should be cross-referenced.
- **Decisions before editing:** D-VOTE (the three open questions).
- **Scope:** medium. Keep it as the canonical *current* spec: resolve or explicitly
  defer each open question, collapse the dual voting spec to one, and add the
  status/pointer banner. Audience: product + organizer + maintainer.

### `v2/spec_design-principles.md`
- **Gaps:** very minor — it predates informed voting / "deliberation depth" as a
  principle. Otherwise stable and should stay deliberately terse.
- **Scope:** tiny — and only **if/when** the phase-model proposal is adopted (D-PHASE):
  one optional principle on argument-informed re-voting. Not before.

### `v2/next_steps.md`
- **Gaps:** C4; broken step numbering (1, 2, 4, 4b–4f, 5 — no 3); contains completed
  TODOs and resolved bugs; the "TODO: open GitHub issue" items (§89, Bug 8) are stale
  now that issues exist. It's valuable as *history* but unusable as a *plan*.
- **Scope:** split. Migrate "done" content into the build log / CHANGELOG (N8);
  migrate live forward items into the roadmap (N7); then retire or archive the file.

### `v2/prop_phase-model.md`
- **Status (decided):** this is the **forward-looking proposal**, under active
  discussion with colleagues and seeking consensus before implementation. It stays a
  separate document — do **not** fold it into the current-truth specs. Track it (it is
  currently untracked) so the discussion has a stable reference, and add a banner:
  "Proposal — under discussion, not yet adopted or implemented."
- **Scope:** small. Add the status banner; track the file; cross-link from
  `spec_functional-design.md` as "where this may go next." Once (if) consensus lands and
  it's implemented, *that* is the moment its content migrates into the current-truth
  specs and an ADR (N6) records the decision — not before.

### `v2/guide_deployment.md`
- **Gaps:** excellent for first-time provisioning, but missing: the **staging tool**
  (`wiki-polis-dev.toolforge.org`, used in the audits) and how prod/staging differ;
  **monitoring/alerting** (issue #49 wants log aggregation; `/health` exists per PR
  #73 but the runtime audit shows it reports "ok" even when its own probe 404s —
  document that limitation); **backup *restore* drill** (backups are documented,
  restore is not); **secrets rotation**; **buildservice migration** (issue #55).
- **Decisions before editing:** is staging a permanent fixture? what's the monitoring
  stack (issue #49)?
- **Scope:** medium add-ons. Split the one-time "provision" content from the recurring
  "operate" content (the latter seeds the runbook, N5).

### `v2/guide_local-dev.md`
- **Gaps:** current and good. Only add a pointer to the testing guide (N9) and note
  the `/dev-login` live `meta.wikimedia.org` call (runtime audit §4) so contributors
  aren't surprised that "local" login isn't offline.
- **Scope:** tiny.

### `v2/reference/particiapi-api.md` & `web-components.md`
- **Gaps:** snapshots dated 2026-05-11 with no "verified against commit/version"
  stamp; risk of silent drift against the upstream Particiapp project.
- **Scope:** tiny — add a provenance/version header and a "last verified" date; set a
  re-verify trigger (on dependency bump).

### `plan.md` & `notes.md` (root)
- `plan.md`: its "current state" table is already partly outdated (e.g. PRs since #22)
  and overlaps `next_steps.md` + `guide_deployment.md`. **Recommend folding** its live
  content into the roadmap (N7) and deployment runbook (N5), then archiving.
- `notes.md`: early research, superseded by `docs/research/`. Archive with a pointer.

### `docs/research/01–06`
- **Gaps:** all carry a "Draft — not fact-checked" banner. They are good raw material
  but cannot be cited or surfaced to participants until reviewed. `05-website-copy.md`
  is explicitly the source for participant help pages (issue #57).
- **Decisions before editing:** who fact-checks against primary sources; which of
  these become public-facing vs stay internal.
- **Scope:** a verification pass (separate from this doc work) → then `02`, `04`, `05`
  feed the participant help pages (N4) and organizer guide (N10).

---

## 4. New documents needed

Ordered roughly by how much they unblock other work. Each: **why · audience ·
decisions-first · scope.**

### N0 — Documentation home / `docs/README.md` (index + reading paths)
- **Why:** C5 — ~20 docs, no single entry. A short "if you are a participant /
  organizer / maintainer, start here" map.
- **Audience:** everyone. **Decisions:** final doc taxonomy (where things live).
- **Scope:** S. One page of links + audience routing. Write last-ish (it indexes the
  others) but stub early.

### N1 — Land the audits, then migrate their durable findings (D-AUDIT: resolved)
- **Why:** the audits are the most accurate description of the system, but they're a
  *point-in-time* record (D-AUDIT) — they'll be archived/deleted once obsolete. The
  lasting value has to move into the maintained docs before that happens.
- **What:** (1) merge PR #94 so the audits are committed; (2) fold the durable
  findings into the docs that *are* maintained — data-ownership map + N+1 + dead-code
  notes → `spec_architecture.md` and the data-model reference (N3); (3) when the audits no
  longer match reality, archive or delete them rather than maintaining them in place.
- **Audience:** maintainers.
- **Scope:** S to land + M to migrate findings (overlaps the `spec_architecture.md` rewrite
  and N3, so do it as part of those).

### N2 — Privacy policy / data-handling statement  ⭐ launch blocker
- **Why:** the accept page ships a *placeholder* privacy section; memory and
  `next_steps.md` both flag this as required before any public launch. The
  identity-reveal timeline, pseudonym uniqueness, xid-is-not-anonymous caveat, and
  operator data retention all need a public, plain-language commitment.
- **Audience:** participants (public), with an internal annex for maintainers.
- **Decisions:** retention commitment **settled (D-PRIV): 180 days** (internal
  nullification target stays at day 60). Still to draft within N2 and bring back for
  review: what is logged, who can see raw identity links, lawful basis /
  Wikimedia-aligned framing.
- **Scope:** M. Drives real participant-facing copy + the accept-page text. Highest
  external-risk doc — **not publishable until human/legal review.**

### N3 — Data model & schema reference (generated from `db.py`)
- **Why:** C3 — prose data models have already drifted. Make `db.py` the single
  source and generate/maintain a reference beside it (tables, columns, constraints,
  the `UniqueConstraint` semantics, naive-UTC datetime convention, the
  `ArgumentVote.value`/"ranking" dead field, the proposed `phase6_*` fields).
- **Audience:** maintainers. **Decisions:** generated vs hand-maintained; include the
  data-ownership map (which store is authoritative per concept) from the runtime audit.
- **Scope:** M. Replaces the data-model prose in `spec_architecture.md` with a link.

### N4 — Participant help pages ("How voting works", "Writing good statements/arguments")
- **Why:** issue #57 asks for these; `05-website-copy.md` + `02` + `04` are the draft
  source. Participants currently get only in-product microcopy.
- **Audience:** participants. **Decisions:** in-app pages vs on-wiki vs static;
  terminology locked ("statement," per `03-terminology.md`); fact-check of the source
  research (§3 research).
- **Scope:** M. Depends on the research verification pass and N2 (privacy links).

### N5 — Operator runbook (day-2 operations)
- **Why:** `guide_deployment.md` covers *provisioning*; nothing covers *running it* —
  backup **restore** drill, responding to a down VPS/Particiapi, the `/health`
  caveat, log locations (Toolforge `uwsgi.log` + VPS docker logs), updating the Polis
  stack, rotating secrets, the nightly `pg_dump` verification.
- **Audience:** maintainer. **Decisions:** monitoring stack (issue #49);
  on-call expectations (likely "best effort, single maintainer").
- **Scope:** M. Seeded by splitting the recurring half out of `guide_deployment.md`.

### N6 — Architecture Decision Records (ADR) trail
- **Why:** many hard decisions are buried in commit messages, review files in
  `.claude/`, and `spec_design-principles.md`. New maintainers need the *why*: why
  self-host vs hosted pol.is, why auth-disabled Particiapi behind a proxy, why xid,
  why per-conversation pseudonyms, why the 403→200 `/results/` rewrite, why
  refactor-not-rewrite (refactor-plan.md already states this), the phase-model decision
  (C2).
- **Audience:** maintainers. **Decisions:** lightweight format (1 file per
  decision, ~1 page); seed set to backfill.
- **Scope:** M as a backfill, then S per future decision. Note: the phase-model ADR
  is written **if/when** the proposal is adopted and implemented — until then
  `prop_phase-model.md` stays a live proposal, not a recorded decision.

### N7 — Roadmap (forward-looking only)
- **Why:** C4 — extract the still-live "what next" from `next_steps.md` and `plan.md`
  into one ordered, dependency-aware roadmap, cross-linked to the open issues
  (#11–#94) and the refactor steps (#89–93).
- **Audience:** maintainer/contributor. **Decisions:** milestone **settled (D-GA):
  feature-complete + hardened** (agreed scope + refactor #89–93 + CI/tests + monitoring).
  Still to sequence: refactor (#89–93) vs feature work vs the launch-blocking docs (N2).
- **Scope:** M.

### N8 — CHANGELOG / build log
- **Why:** C4 — the completed history in `next_steps.md` is genuinely useful but
  belongs in a changelog, keyed to PRs/releases.
- **Audience:** maintainer. **Decisions:** Keep-a-Changelog format vs narrative log;
  start point.
- **Scope:** S-M (mostly migration of existing content).

### N9 — CONTRIBUTING + test strategy & guide
- **Why:** bigger than a write-up. 107 tests exist but with real structural problems
  the audit surfaced (a whole module uncollectable §3a, drift §3b — fixed in PR #88 —
  and genuinely untested high-risk paths §5: the Polis-Postgres raw SQL, the proxy
  cookie-rename / 403→200 rewrite, the quota row-lock race, time-based reveal
  nullification). Documenting "how to run the tests" on top of that would paper over
  the real question: **how do we want to test this going forward?** So N9 is two
  things — a **test-strategy rethink** (a decision, D-TEST below) and *then* the
  CONTRIBUTING/testing guide that documents the agreed approach (run flow, what to
  cover, CI gate, ruff/C901, branch/PR norms).
- **Audience:** contributors + maintainer. **Decisions:** **D-TEST** — target coverage
  philosophy, what must be tested (the untested-but-risky paths), whether there's CI
  and what gates merges.
- **Scope:** L (strategy + doc), not S-M. The doc is small; the rethink is the work.

### N10 — Organizer guide ⭐ maturity-critical
- **Why:** the product is only as good as the consultations run on it. Nothing tells
  an organizer how to scope a topic (`06-scope-and-topic.md`), write seed statements
  (`02`), sequence the phase toggles (the phase model, C2), curate featured
  statements, interpret cluster results, and run identity-reveal responsibly. This is
  the difference between "deployed software" and "a tool people can actually use."
- **Audience:** organizers — people who run consultations (create conversations, seed statements, sequence phases, read results).
- **Decisions:** which research docs are promoted; the min-N (currently 25) and
  reveal-window guidance.
- **Scope:** M — **mostly restructuring, not net-new writing.** The raw material
  already exists in `docs/research/01–06`; the work is reorganising and re-framing it
  into a coherent organizer-facing guide (and a verification pass on the source —
  D-RESEARCH). Describe the *current* phase toggles, not the forward proposal.

### N11 — Security & threat model — ⏸ parked (owned by colleague, in parallel)
- **Status:** a colleague is working on this in parallel. **Not in scope for this doc
  effort** — left on the list for completeness and so the other docs know to link to
  it once it lands. Coordinate rather than duplicate.
- **Why (for reference):** security hardening is scattered across `next_steps.md` §4b
  and `.claude/` review files; a consolidated doc (trust boundaries, the proxy as the
  only path to Particiapi, CSRF/origin model, rate limits, what xid does and does
  *not* protect) + a `SECURITY.md` is worth having.
- **Audience:** security reviewers, maintainers.

---

## 5. Decisions register (settle these before writing the dependent docs)

| ID | Decision | Blocks | Owner |
|---|---|---|---|
| ~~**C2 / D-PHASE**~~ ✅ | **Resolved:** keep both docs separate. `spec_functional-design.md` = current truth; `prop_phase-model.md` = forward proposal under discussion, not yet adopted. Label each by status; do not merge. | (unblocked) | product |
| ~~**D-V1**~~ ✅ | **Resolved:** keep v1 as a historical archive (not deleted, not maintained). v2 is live; v3 possible later but not a doc concern now. **v1/ may be restructured or relocated** (e.g. into an archive area) as part of cleanup — it need not stay where it is. | (unblocked) | maintainer |
| ~~**C4**~~ ✅ | **Resolved:** split next_steps into a forward roadmap (N7) + a historical record / changelog (N8) so outdated work can't accidentally drive future decisions. | (unblocked) | maintainer |
| ~~**D-VOTE**~~ ✅ | **Resolved:** (1) "change vote" **reopens the statement and resubmits** the new vote to Polis (fixes #69); (2) after a **proposal submission**, auto-advance to the next statement after a brief pause — make that pause **a bit longer** than a default; (3) after a **plain vote**, keep the **explicit "Move on"** click. (Implementation note: #69 needs a code change, not just docs.) | (unblocked) | product |
| ~~**D-PRIV**~~ ✅ | **Resolved (clarified).** A participant's voluntary public reveal of their username↔pseudonym is **permanent and irreversible — never nullified.** Separately, the **internal** account↔pseudonym link (held by platform managers, for technical/dedup purposes) is removed within **180 days** of close (internal target sooner). ⚠️ `spec_functional-design.md` and the current code still *nullify reveals* — both need reconciling to this model (spec edit + a code change to `_nullify_expired_reveals`). N2 drafts toward it; not publishable until legal/comms review. | N2, functional_design, code | maintainer + review |
| ~~**D-AUDIT**~~ ✅ | **Resolved:** merge PR #94 to keep the audits in version control, but treat them as a **point-in-time record** — archive or delete once obsolete. Durable findings must be folded into `spec_architecture.md` / the data-model reference so their value survives the audits' eventual removal. | (unblocked) | maintainer |
| ~~**D-STORE**~~ ✅ | **Resolved: intended design.** The two read paths are **routes to the same store, not separate stores** — admins read Polis Postgres directly (moderation buckets + vote counts the participant API doesn't expose); participants get the live Particiapi-HTTP view of the same data. Documented in `spec_architecture.md`; the inconsistent client shapes are a minor cleanup, not a redesign. | (unblocked) | maintainer |
| ~~**D-MON**~~ ✅ | **Resolved (split):** monitoring/log-aggregation (#49) is **deferred** — runbook keeps a monitoring TODO until the production VPS is provisioned; document `/health` and its reachability-only limitation in the meantime. **Staging is permanent** — document `wiki-polis-dev` as a standing environment incl. prod-vs-staging differences (dev-login, separate DB). | deployment, N5 | maintainer |
| ~~**D-RESEARCH**~~ ✅ | **Resolved:** Claude runs the verification pass — re-check each claim against primary sources (web + MediaWiki API), mark verified/uncertain — then **human sign-off** before any public use. | N4, N10 | product (sign-off) |
| **D-TEST** 🟡 | **Leaning CI gate, pending colleague discussion.** Recommendations written up in `.claude/testing-strategy-recommendations.md` (phased: CI-on-PR → hermetic suite → backfill risky paths). Finalise after that discussion; then N9 documents the agreed approach. | N9 | maintainer |
| ~~**D-GA**~~ ✅ | **Resolved: feature-complete + hardened.** Launch = the agreed planned scope shipped + blueprint refactor (#89–93) + CI/tests (D-TEST) + monitoring (D-MON) in place. (Note: "planned scope" = the current/agreed feature set; the forward 6-phase proposal is **not** auto-included — its inclusion depends on C2 consensus.) Roadmap (N7) orders toward this bar. | N7 | maintainer |
| ~~**D-NAMING**~~ ✅ | **Resolved:** role-prefix filenames (`spec_`/`ref_`/`guide_`/`plan_`/`prop_`/`log_`/`pub_`/`research_`) + mutable status in banners; transient inline refs tagged `*(pending — #NN)*`. Recorded in `documentation-standards.md`. **New docs adopt it immediately; renaming the existing docs to the scheme is its own wave** (link updates + `git mv`). | all new/renamed docs | maintainer |

---

## 6. Suggested order (waves)

Dependencies drive this. Each wave is independently shippable.

**Wave 0 — Unblock & de-confuse (do first, cheap, high-value)**
1. Fix C1 (README v1/v2 labels) — verify against PR #87, finish it; v1 → archive
   footnote per D-V1.
2. Add status banners: `spec_functional-design.md` = "current truth," and track +
   banner `prop_phase-model.md` = "proposal under discussion" (C2 is decided —
   this is labelling, not a debate).
3. Merge PR #94 (N1); plan to migrate the durable findings into `spec_architecture.md` /
   N3 (D-AUDIT: audits are point-in-time, archive/delete later).
4. Stub **N0** (doc home) so new docs have a place to be linked.

**Wave 1 — Make the core specs true again**
5. Bring `spec_functional-design.md` up to date as the *current* spec; resolve **D-VOTE**;
   collapse the dual voting spec. (Do **not** import the 6-phase model — it stays in
   the proposal until consensus + implementation.)
6. Generate **N3** (data-model reference) and link it from `spec_architecture.md`; resolve
   **D-STORE**; add the data-ownership section.

**Wave 2 — Separate history from plan**
7. Split `next_steps.md` → **N7** (roadmap) + **N8** (changelog / historical record);
   fold in `plan.md`'s live content; archive `plan.md`/`notes.md`.
8. Write **N9** (CONTRIBUTING + testing) — unblocks outside contributors.

**Wave 3 — Operate & launch-readiness**
9. Split `guide_deployment.md` recurring content → **N5** (runbook); add staging,
   monitoring (D-MON), restore drill.
10. Write **N2** (privacy) — **launch blocker**; needs **D-PRIV** + review.
11. ⏸ **N11** (security/threat model) — tracked by colleague in parallel; not part of
    this effort. Link to it when it lands.

**Wave 4 — Make it usable by humans (maturity)**
12. Research verification pass (**D-RESEARCH**) on `docs/research/*`.
13. Write **N4** (participant help) and **N10** (organizer guide) — the docs that
    turn "running software" into "a tool a community can actually adopt."
14. Finalize **N0** (doc home) now that everything it points to exists.

### How to review (checkpoints — so the output matches your intent)

Not every doc needs the same scrutiny. Proposed gate by stake:

- **Review-gated (you approve an outline/redline before I write the full thing):**
  the README rewrite, any `spec_functional-design.md` change, **N2 (privacy)**, and
  **N10 (organizer guide)**. These are either public-facing or define the product —
  cheap to course-correct at outline stage, expensive after a full draft.
- **Decision-gated (you settle the linked decision, then I proceed):** all are now
  resolved except **D-TEST** (leaning CI gate, pending your colleague discussion).
  For any future decision I'll bring it first with context, then draft.
- **Draft-then-review (I write, you skim the result):** mechanical or low-stakes work
  — N3 (generated reference), N8 (changelog migration), the reference-doc version
  stamps, status banners. Fast to verify after the fact.

Suggested rhythm: for review-gated docs I'll post a short outline (headings +
1-line intent each) and wait for your go; for decision-gated docs I'll bring the
decision with context one at a time; everything else I'll just do and show you.

---

## 7. Audience coverage check

| Audience | Has today | Will have after this plan |
|---|---|---|
| **Organizer** (runs consultations) | scattered research drafts | organizer guide (N10) + verified research |
| **Maintainer** (builds, deploys & operates — one technical role) | local-dev, deployment, audits-in-PR, commit archaeology | runbook (N5 ✓), data-model ref (N3), CONTRIBUTING/testing (N9), ADRs (N6), changelog (N8 ✓), roadmap (N7 ✓), tracked audits (N1) |
| Participant (uses the website, not the repo) | in-app microcopy | help pages (N4) + privacy statement (N2, draft) — delivered via the website |
| First-time visitor | stale README | accurate README + doc home (N0) |

---

## 8. Doc-hygiene & standards

These were extracted into their own living document — **[documentation-standards.md](documentation-standards.md)** —
so they can be maintained independently of this one-off plan. That doc makes
**doc lifespans explicit at the top** (which docs track code, which are append-only,
which change deliberately, which are public-facing) and records the rules that keep
the set from rotting again: generate-don't-transcribe, one-source-per-concept,
decisions-get-ADRs, separate-lifespans, and status banners.
