# Atomic statements: definition, detection, and effectiveness

*Synthesis across `wiki-polis` and `polis-study`, July 2026. Draft — cites internal docs whose own draft warnings still apply.*

---

## 1. Definition

A statement is the atomic unit participants vote Agree / Disagree / Pass on: **one declarative claim, one idea, one sentence.** It is not just content — it is a *measurement instrument*. Each vote is a data point; a badly formed statement produces unreliable data and a wrong opinion map.

> "A **statement** is the atomic unit participants vote on: a single declarative claim, one idea, that someone can Agree / Disagree / Pass on. Each vote is a data point, so a statement is really a *measurement instrument*." — `guidance/guide_organizer.md`

Operationally: **never join two claims with "and / but / because"**. If a sentence contains two claims joined by a coordinator, comma, or semicolon, it should almost certainly be split.

Two things atomicity is *not*:

- Not brevity. A short vague slogan is atomic but useless.
- Not syntactic single-clause-ness. "Wikipedia and Wikimedia are both affected by declining retention" contains one claim despite the "and". The test is **two claim-bearing clauses**, not the presence of a joining word.

Upstream Polis states the same rule in participant UI copy — "Keep it short — one idea per statement" (`polis-study/data/sources/screenshots/2024/voting.html`) — and CompDem's moderation recommendations reject "compound (multiple claims in one)" statements outright.

---

## 2. Why it matters — the mechanism

This is the part worth being precise about, because the two repos supply two halves of a causal chain that neither states in full.

**Half one (wiki-polis / Small et al. 2021): compound → Pass → lost signal.**
A participant who agrees with claim A but not claim B cannot vote accurately, so they Pass. Small et al. are explicit that compound statements "elicit more passes when participants agree with one point, but not others," and name this the most tractable common failure mode. The Pass removes that participant's row-entry from the vote matrix that PCA and k-means operate on.

**Half two (polis-study `docs/routing_mechanism.md`): Pass → suppressed exposure, squared.**
Polis's comment router scores each statement:

```
importance = (1 − p) · (E + 1) · a          p = smoothed pass rate
priority   = [ importance · (1 + 8·2^(−S/5)) ]²
```

Pass rate enters as `(1 − p)` and the whole thing is **squared**. So a high-pass statement is not merely uninformative — it is actively buried. Half the importance means a quarter the exposure. And the new-comment boost decays to ~1 by roughly 30 votes, so **the first ~10–30 votes decide a statement's fate**; suppression is early and self-reinforcing.

**The joint conclusion:** a compound statement is punished twice. It loses signal *and* loses the exposure it would need to recover. Atomicity failures are therefore not recoverable downstream — they must be prevented at authoring time. This also explains why the compound-statement problem concentrates in seed statements: seeds take a median 1.37× their fair share of votes (polis-study, 116-conversation cohort), they are the earliest content, and roughly 9 in 10 participants only vote and never submit. Seed quality is where most of the data comes from.

**A caveat the polis-study repo insists on:** pass officially means "no reaction / unsure", not "irrelevant" (Polis has a separate *trash* button for that). This makes pass-rate a defensible *clarity* proxy — but only net of per-participant pass tendency, since individual differences dominate. Raw pass rate confuses an unclear statement with a tired voter.

---

## 3. The five criteria

The working rubric, consistent across `guidance/`, `docs/research/02-statement-writing-guide.md`, `v2/statement_advisor.py`, and `guidance/statement-helper-prompt.md`:

| # | Criterion | Test | Failure example |
|---|---|---|---|
| 1 | **Atomicity** | Exactly one claim | "Wikipedia should require reliable sources **and** editors should disclose conflicts of interest." |
| 2 | **Neutrality** | Describes rather than argues; no loaded or evaluative wording | "Wikipedia's *bureaucratic* deletion process *unjustly silences* new editors." |
| 3 | **Concreteness** | Specific, ideally falsifiable or actionable; names a mechanism, action, or consequence | "Wikimedia should support a healthier community." |
| 4 | **Scope** | Not so broad it draws universal agreement, not so narrow it's irrelevant; avoid absolutes | "Wikipedia should be accurate and reliable." |
| 5 | **Form** | A declarative claim, not a question, topic, or title | "Shouldn't the Foundation be more transparent?" |

Plus a length convention: **≤280 characters** in wiki-polis (upstream Polis allows 400).

Neutrality has empirical backing, not just aesthetics: the Open Rights Group / Demos study found the same policy drew 56% support under one framing and opposition under another.

---

## 4. Detection

### 4.1 Implemented: deterministic heuristics

`v2/statement_advisor.py` is written and tested but **not wired into the app** (only importer is its test file). It returns five flags at OK / WARN severity, never blocks, and favours precision over recall — "a false positive (nagging a fine statement) is more harmful to trust than a missed compound."

The atomicity rule is two-stage:

1. Split on `\b(and|but|because|whereas|while|;)\b`.
2. WARN only if **≥2 of the resulting segments contain a claim cue** (`should|must|ought|needs to|is|are|will|can|requires|...`).

This is what defeats the noun-list false positive. The other four checks use curated lexicons: `_LOADED_TERMS` (neutrality), `_VAGUE_TERMS` + a "has a digit or ≥12 words" concreteness escape, `_ABSOLUTE_TERMS` (scope), and a trailing-`?` / short-fragment form check.

### 4.2 Designed but unbuilt: tiered detection

`.claude/drafts/issue-advising-agent.md` sets out the intended per-check allocation:

| Check | Approach |
|---|---|
| Question form | Rule-based |
| Compound claims | Rule-based first; dependency parse where rules produce false positives |
| Vague aspiration / scope | Lightweight NLP or LLM |
| Loaded language | LLM (lexicon alone too brittle) |
| Conduct / UCoC | Dedicated moderation model — separate concern, this is enforcement not coaching |

Two design constraints worth carrying forward: **no auto-rewriting** (surfacing a ready-made "better version" puts words in the author's mouth — surface the problem, let them fix it), and never signal a flag by colour alone.

### 4.3 LLM approach

`guidance/statement-helper-prompt.md` is the only prompt artifact and encodes the full pipeline: *extract distinct claims → check each against the five principles → show before/after → flag near-duplicates → flag over/under-scoped → hand back a numbered shortlist ≤280 chars.* Its worked example turns one loaded compound sentence into three atomic neutral statements, which is precisely the decomposition operation.

`polis-study` has **no prompt and no coding scheme** — its planned LLM pass (`hypotheses/RQ-moderation-natural-experiment.md`) would classify rejected statements as off-topic / compound / inflammatory / abusive / duplicate to derive a rejection taxonomy and false-positive rate, but is gate-3 blocked and unbuilt. `RQ-statement-novelty-and-authorship.md` explicitly notes the rubric doesn't exist yet and needs pre-registration plus an inter-rater check.

### 4.4 Adjacent: is this the same *idea*?

Atomicity's sibling problem. `polis-study` has built detectors here:

- TF-IDF char 3–5 gram cosine, language-agnostic. `seed_adoption.py` uses ≥0.90 as near-duplicate; `reseed_of_rejected.py` uses ≥0.60 as "re-seed of a prior participant statement".
- Multilingual mpnet sentence embeddings (`build_comment_embeddings.py`).
- The **Lowe ratio test** (NN2/NN1) as a principled three-way discriminator: *novel* = low NN1; *single-source derivative* = high NN1 + low ratio; *combination of ≥2 sources* = high NN1 + high ratio. With the important refinement that the ratio breaks under near-duplicate clusters and must be run over deduplicated idea-clusters.

The standing warning: **embedding similarity ≠ agreement.** SBERT scores "climate change is real" vs "climate change is not real" at ≈0.9 cosine. Text-near + stance-far is a *rebuttal*, not an echo. Keep the topic axis and the stance axis separate.

---

## 5. Set-level design — atomicity is necessary, not sufficient

A set of individually perfect statements can still be a bad instrument.

- **10–15 seed statements.** Fewer leaves the space ill-defined; many more over-determines it. (`guide_organizer.md`; upstream copy says at least 8–10.)
- **Cover the range of views, not just your own framing** — include positions the author disagrees with.
- **Mix diagnostic claims (what's the problem?) with policy claims (what should be done?).**
- **Deliberately include expected genuine disagreement**, not just easy consensus. "Not boring, not one-sided."
- Statement pools that are agree-skewed by construction are a documented failure: Demos found people "naturally seek to write their statements in ways likely to garner agreement", and that Polis "lends itself to consensus by construction."
- Large pools overwhelm participants and drive dropout (Klimarat, ~"100+ statements"); no-moderation runs flood with redundant statements (Scoop HiveMind NZ).

**Open question, flagged as unresolved in the repo:** what proportion of participants *should* agree with a good statement? The sources give no target. The 56% figure is a framing illustration, not a guideline.

---

## 6. Moderation posture

Distinct from authoring advice, and the two repos agree: **remove abuse, be reluctant about everything else.** CompDem recommends removing only abusive content — not "off-topic", "duplicate", or low-quality — because removing non-abusive statements risks silencing perspectives that challenge the facilitator's framing, disproportionately from under-represented groups.

polis-study measured what actually happens: across 261 conversations / 53,778 statements, ~36% never reach "accepted"; 1,579 removals were both exposed and net-agreed ≥50%. **Agreed statements did disappear.** Rejection rates range from 0% to ~69% by conversation. Demos: "speaking ≠ being heard — moderation drops lower-SES submissions."

So atomicity is properly an **authoring-time coaching signal**, not a moderation-time rejection criterion.

---

## 7. Known gaps

1. `v2/statement_advisor.py` has zero production callers. The facilitator-queue score display was designed and never built.
2. No LLM is used for statement checking anywhere in either codebase.
3. polis-study has no measured relationship between statement text properties and vote or cluster outcomes that has survived review — the ordering-effects numbers were withdrawn in June 2026 pending re-run with size-invariant estimators.
4. No pre-registered rubric or inter-rater agreement check exists for the new / rephrase / duplicate distinction.
5. The AT-3 test — *do rephrasings out-perform their originals on agreement?* — is named as "THE test for whether common ground is produced rather than revealed," and is unrun.

---

## Sources

**wiki-polis:** `guidance/guide_organizer.md`, `guidance/statement-helper-prompt.md`, `guidance/pub_participant-help.md`, `docs/research/01-objectives-and-statements.md`, `docs/research/02-statement-writing-guide.md`, `docs/research/04-arguments.md`, `docs/research/05-website-copy.md`, `v2/statement_advisor.py`, `v2/tests/test_statement_advisor.py`, `v2/spec_design-principles.md`, `v2/spec_functional-design.md`, `v2/templates/guidance_statement.html`, `.claude/drafts/issue-advising-agent.md`

**polis-study:** `docs/routing_mechanism.md`, `data/SOURCES.md`, `data/sources/screenshots/2024/voting.html`, `hypotheses/CLAIMS_INVENTORY.md`, `hypotheses/RQ-moderation-natural-experiment.md`, `hypotheses/RQ-statement-novelty-and-authorship.md`, `planning/ordering_effects_framework.md`, `planning/proposal_context_method.md`, `planning/moderation_lifecycle.md`, `literature/elicit_pass-design.md`, `literature/REVIEW_embeddings.md`, `analysis/seed_adoption.py`, `analysis/reseed_of_rejected.py`

**External:** Small et al. 2021 (RECERCA); Huang, Siddarth et al. 2023 (arXiv:2306.11932); Open Rights Group / Demos 2020–21; Computational Democracy Project; Lowe 2004 (SIFT §7.1).
