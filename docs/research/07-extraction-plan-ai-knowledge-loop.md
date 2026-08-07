# Extraction plan: atomic statements from *Wikimedia, the commons, and the new AI knowledge loop*

*Source: Tarkowski & Valdelli, White Paper v1.0, July 2026, 76pp, CC BY. Commissioned by Wikimedia CH.*
*Method basis: `docs/research/06-atomic-statements-synthesis.md`.*

---

## What the source is, and what that implies

The paper is a **mission proposal**, not a neutral survey. It argues for one posture (active stance) over two alternatives it explicitly rejects, and closes with "this paper should be read as the start of that process, not its conclusion. It proposes a direction; the coalition that forms around it will specify the detail." That is an unusually clean brief for a Polis consultation — the paper *wants* to be tested.

Three consequences for extraction:

1. **The source is already advocacy.** Its sentences are written to persuade, so nearly every candidate will fail the neutrality check on first pass and need rewriting. Extraction here is mostly *de-rhetoricising*.
2. **Its central claims are propositional, not empirical.** "Wikimedia should be one of the primary user-facing knowledge interfaces" is a direction to test consent on, not a fact to verify. Good — that's exactly what Polis measures.
3. **Some passages are framing, not proposal.** The three loops, the Paradox of Open, the Stack Overflow warning. These are diagnosis. Whether to include them is a scoping decision (see Question 1 below).

---

## Structure: eight candidate sets

Each set is a coherent decision area with its own logic of disagreement. Sizing target is 8–15 statements per set — but see the sizing warning further down.

### Set A — Diagnosis: is the loop actually broken?
*Optional; diagnostic rather than directional.*
The measurable claims: traffic decline attribution, crawl-to-referral ratios, the dark-commons thesis, the Stack Overflow analogy, whether the foundational source base (journalism, academic publishing) is degrading. **Genuine disagreement is likely here** — some of these are contested empirically, and the paper's causal attributions ("Google referral decline explains virtually all the reduction in human traffic") are strong.

### Set B — Strategic posture
The paper's core trichotomy: defensive closure / passive acceptance / active stance, and the claim that the first two converge on the same failure. Also: whether rate-limiting AI scrapers is defence or self-harm; whether exclusive licensing is closure or enclosure. High-value set — it forces a choice rather than collecting assent.

### Set C — Reciprocity and the terms of reuse
Attribution norms redesigned for AI contexts; Share Alike for AI; whether reciprocity should be conditional on access; non-financial reciprocity (AI platforms returning usage data on what readers ask and where coverage is thin); Wikimedia Enterprise as precedent vs as ceiling; whether $8.3M / 4% of revenue is a floor or evidence the model doesn't scale.

### Set D — Interface agency
The mission's sharpest and most contested claim: that Wikimedia must become a **user-facing knowledge interface**, not just a producer of the commons. Plus its two stated safeguards — interfaces must route readers back to Wikipedia (to sustain the editor and donor pipeline), and interfaces must be plural. Also the explicit disclaimer "the mission is not to build Wikimedia's own ChatGPT," which is itself a testable position.

### Set E — Wiki AI technical stack
Data layer (ground-truth corpus, Wikidata, Enterprise APIs, quality-signalling infrastructure, crowdsourced data collection, new content partnerships); model layer (whether a state-of-the-art public AI model is a genuine prerequisite; partnership vs in-house); application layer (editor augmentation vs reader interfaces); and the separate experimentation environment claim — that production infrastructure is poorly suited to AI experimentation.

### Set F — Collective intelligence and community health
That AI tools must augment rather than replace human editorial judgment; countering editor-pipeline erosion; protecting epistemic diversity; the claim that Wikimedia's value is the human process, not the data corpus; "designing participation that is meaningful without being tedious." **Most directly relevant to editors** — likely the set with the highest community engagement and the one where the paper's institutional voice is furthest from the volunteer voice.

### Set G — Equity and the Global Majority
Algorithmic colonisation; the movement's internal North/Majority asymmetry; the strong claim that "Global Majority solutions can still benefit the Global North, but not the other way around"; federated AI commons; whether investment should be geographically conditioned; building on the 2024 Global Majority Technology Priorities. Contains at least one deliberately provocative claim worth keeping provocative.

### Set H — Coordination, resourcing, and venue
The Wiki AI cluster; who leads and who convenes; co-financing so no single funder controls direction; Endowment seed funding; treating this as core priority vs side project; movement leaders taking visible external political positions; and the Switzerland / Geneva 2027 opportunity — including the paper's own careful line that Wikimedia CH's role "is not to lead the mission, but to open the space."

---

## Method

**Step 1 — Harvest.** Pass through the paper section by section, pulling every sentence that asserts a priority, direction, obligation, or contested diagnosis. Keep the page number and the source sentence verbatim alongside each candidate. Expect ~120–180 raw candidates.

**Step 2 — Decompose.** Split every compound. The paper is dense with them — e.g. *"attribution that makes the commons visible rather than a hidden substrate; transparency about how commons-derived knowledge is used and transformed; and contributions back that strengthen the shared resource"* is three statements, and someone can plausibly support attribution while rejecting mandatory contribution-back. Apply the ≥2-claim-bearing-clauses test, not a naive split on "and".

**Step 3 — De-rhetoricise.** Strip the advocacy register. "Wikimedia is becoming a *dark commons*: an invisible substrate feeding proprietary systems" → "Wikimedia content is increasingly used by AI systems without readers being aware of its role." Strip: *must*, *urgent*, *only way*, *risks remaining*, *parasitic*, *hollow out*. Keep the claim, drop the pressure.

**Step 4 — Concretise.** Reject vague aspirations that would draw 90%+ agreement and teach us nothing. "Wikimedia should have agency in the AI ecosystem" is unvoteable. "Wikimedia should require AI companies to display attribution to Wikipedia in generated answers" is voteable.

**Step 5 — Deduplicate across sets.** The paper repeats its core propositions in the summary, the principles, the mission statement, and the closing. Cluster by meaning, keep the sharpest phrasing of each idea, note which page it appeared on. Check for cross-set near-duplicates specifically — attribution appears in both C and E.

**Step 6 — Balance each set.** For every set, verify it contains (a) statements the paper's authors would disagree with, (b) at least some where I'd expect a genuine split rather than consensus, and (c) a mix of diagnostic and policy claims. If a set reads as a list of things everyone will agree with, it's a bad set — the paper's own framing choices need to be voteable, not just its conclusions. Where the paper rejects a position (defensive closure, passive acceptance), write that position in its **strongest sympathetic form**, not as the paper's caricature of it.

**Step 7 — Verify.** Run every statement through the five checks: atomicity, neutrality, concreteness, scope, form. Plus ≤280 characters. Plus a fidelity check — does the statement still represent something actually in the paper, or did rewriting invent a position? Cite the source page for each.

---

## Output format

One markdown file per set plus an index, or a single file with eight sections — your preference. Each statement carries:

```
| # | Statement | Source p. | Type | Expected split |
```

where *Type* is diagnostic / policy / value, and *Expected split* is my guess at whether it draws consensus or division — useful for checking set balance before publication, and worth recording as a prediction to compare against actual results later.

I'd also produce a **residue log**: claims from the paper deliberately *not* turned into statements, with the reason (too vague to concretise, purely factual, out of scope, unresolvably compound). That log is where the framing decisions are visible, and the synthesis doc is clear that a mission "must make its framing choices explicit rather than assume consensus."

---

## Two warnings from the research

**Sizing.** The guidance says 10–15 seeds per conversation. Eight sets × 10 = 80 statements. If these are run as one conversation, that's a pool large enough to cause the dropout documented in the Klimarat case, and the routing formula's new-comment boost decays by ~30 votes so late statements may never get exposure. **Eight sets probably means eight conversations, or a deliberate subset.** This is the main open decision.

**Provenance visibility.** The Klimarat finding: a visible "Climate Council" prefix biased voting. If these statements are presented as *the white paper's proposals*, that framing itself will move votes — plausibly toward deference. Worth deciding consciously whether authorship is disclosed, and noting that the paper's own legitimacy argument ("build legitimacy through participatory formulation, especially with editor communities") cuts toward disclosure even at the cost of some bias.

---

## Decisions taken (LL, July 2026)

1. **Diagnosis is in, as its own set.** Set A stays. The paper's premises get tested alongside its conclusions.
2. **Each set is its own conversation.** Eight sets, eight conversations, each sized to the 10–15 seed guidance. The sizing warning above is resolved rather than worked around.
3. **Sharp, including the provocative claims.** Global Majority conditionality, whether Wikimedia should build reader-facing AI at all, and the paper's rejected postures all stated at full strength. The rule from Step 6 applies with force: positions the paper argues *against* get written in their strongest sympathetic form, not as the paper's caricature of them.

Consequence of (3): the residue log matters more, not less. If a claim is too sharp to state neutrally, that belongs in the log with the reason — sharpness is about the substance of the claim, not the temperature of the wording. A statement can split the room while still passing the neutrality check.
