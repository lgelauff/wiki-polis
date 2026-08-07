# Verification report

Step 7 of the extraction plan. 110 statements checked.

---

## 1. Five-criteria check

Ran `v2/statement_advisor.py` over all 110 statements — the first time that module has been used on real content, since it has no production callers.

**Result: 5 flagged on the first pass, 2 fixed, 3 accepted with rationale. No atomicity, neutrality, concreteness, or form failures remain.**

### Fixed

| # | Flag | Change |
|---|---|---|
| A-11 | scope — "any" | "…without returning **any**" → "…while returning **little in exchange**". The original claimed zero return, which is false: Wikimedia Enterprise exists and several AI developers pay. A statement that overstates its own case invites disagreement on the overstatement rather than the claim. |
| C-08 | atomicity | "…data on what readers ask about **and** where coverage is thin" bundled two data types someone could want separately. Reduced to "…data about what readers ask them." The coverage-gap claim was dropped rather than split — it added little that C-08 doesn't already carry. |

### Accepted with rationale

| # | Flag | Why kept |
|---|---|---|
| C-11 | scope — "every" | The universality *is* the claim. C-11 contrasts a uniform published standard against case-by-case negotiation; narrowing it would erase the distinction it exists to test. |
| D-05 | scope — "any" | "Any AI interface Wikimedia builds" means *whichever*, not a universal quantifier over the world. False positive of the lexical heuristic. |
| D-11 | scope — "never" | "even when they never visit Wikipedia" is the precise condition under which the claim bites. Softening it to "rarely" would let people agree without facing the trade-off. |

**Note on the advisor itself:** 3 of its 5 flags here were false positives, all from `_check_scope`'s flat lexicon. The design doc anticipated exactly this ("brittle at the edges") and the module is calibrated to advise rather than block, which is the right call — a blocking version would have mangled three statements that are correct as written. Worth feeding back into issue #56 as real-world calibration data.

---

## 2. Length

All 110 statements are under the 280-character limit. Longest is D-11 at 136 characters; median is around 105. No statement is close to the cap.

---

## 3. Cross-set near-duplicate check

TF-IDF char 3–5 gram cosine, the language-agnostic method used in `polis-study/analysis/seed_adoption.py`. Reference thresholds from that repo: **≥0.90** near-duplicate, **≥0.60** re-seed of a prior statement.

**Maximum observed similarity: 0.51.** Three pairs above 0.45; nothing approaching either threshold.

| Pair | Sim | Assessment |
|---|---|---|
| A-10 / G-06 | 0.51 | Closest genuine overlap. Both concern AI propagating Wikimedia's coverage bias. A-10 frames it as English dominance becoming the global default; G-06 frames it as existing gaps being frozen. Different enough to keep, and **they sit in different conversations, so they never compete in the same pool.** |
| E-03 / E-04 | 0.50 | Same set, deliberate: a policy proposal and the diagnostic premise it rests on. Whether the problem exists and whether to spend money on it are separate votes. Retained as a designed pair. |
| C-03 / F-05 | 0.48 | Lexical, not semantic — both contain "disclose". One is about AI developers disclosing training data, the other about editors disclosing AI use. A clean illustration of the caveat in `literature/REVIEW_embeddings.md`: text similarity is a topic measure, not a stance or content measure. |

---

## 4. Set balance

| Set | n | divisive | lean | consensus | diagnostic | policy | value |
|---|---|---|---|---|---|---|---|
| A | 14 | 6 | 6 | 2 | 13 | 0 | 1 |
| B | 13 | 8 | 4 | 1 | 5 | 5 | 3 |
| C | 14 | 7 | 5 | 2 | 3 | 10 | 1 |
| D | 13 | 8 | 5 | 0 | 5 | 6 | 2 |
| E | 14 | 6 | 7 | 1 | 3 | 11 | 0 |
| F | 14 | 7 | 4 | 3 | 4 | 7 | 3 |
| G | 14 | 8 | 4 | 2 | 9 | 4 | 1 |
| H | 14 | 5 | 8 | 1 | 4 | 10 | 0 |
| **Total** | **110** | **55** | **43** | **12** | **46** | **53** | **11** |

**Half the pool is predicted divisive**, which is the intent — a set that draws broad agreement produces no clustering signal. Only 12 statements are predicted consensus, and most are deliberate calibration anchors (C-01, E-01, H-01).

Two imbalances, both intentional:

- **Set A has no policy statements.** It is the diagnostic set by design; its job is to test premises.
- **Sets E and H have no value statements.** Both are operational — what to build, who pays. The value questions underlying them live in B and D.

**Set D has no predicted-consensus statement.** That is a genuine finding rather than a construction artifact: the paper's central proposal has no uncontested component. Worth noting to the authors.

---

## 5. Fidelity check

Every statement carries a page reference to the white paper and was checked against the source text after rewriting. Nothing in the sets asserts a position absent from the paper — including the counter-positions, all of which are drawn from views the paper explicitly names and argues against (defensive closure p. 49, passive acceptance p. 50, exclusive licensing p. 50, the enforceability objection p. 12, the neutrality cost p. 66).

**Three places where rewriting moved furthest from the source, flagged for review by anyone who knows the paper well:**

1. **A-13** compresses the entire "dark commons" argument (pp. 29, 69) into a claim about reader awareness. The original is broader — it concerns invisibility to the ecosystem, not only to readers.
2. **F-06** states the paper's implicit position on editor decline in order to make the *alternative* explanation voteable. The paper never states F-06 as such; it is assembled from what the paper attributes decline to across pp. 12 and 21.
3. **G-09** is close to verbatim but stripped of the framing that surrounds it on p. 37. Stated bare, it reads harder than it does in context. That was the intent under the sharpness decision, and it is the statement most likely to need a second opinion.

---

## 6. What was not verified

- **No inter-rater check.** The *Expected split* column is one person's prediction. `polis-study/hypotheses/RQ-statement-novelty-and-authorship.md` is explicit that judgments of this kind need a pre-registered rubric and an agreement check before percentages get reported. These predictions are recorded to be scored against actual results, not treated as findings.
- **No semantic-similarity pass.** The duplicate check is lexical (TF-IDF). A multilingual mpnet embedding pass, as in `analysis/build_comment_embeddings.py`, would catch same-idea/different-words pairs that char n-grams miss. Given the maximum observed similarity of 0.51 and the fact that the sets run as separate conversations, this is low-priority — but A-10 / G-06 is the pair most likely to move under a semantic measure.
- **No test with actual participants.** Predicted agreement levels are untested. The first conversation to run should be treated partly as an instrument test.
