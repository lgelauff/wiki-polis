> **⚠️ Draft — not fact-checked.** This document is a synthesis of external sources compiled for internal research purposes. Claims have not been independently verified against primary sources. Do not cite or publish externally without review. Sources are listed at the bottom; URLs are only included where access was confirmed.

---

# Writing good statements

## Why statement quality matters

Every statement feeds directly into the vote matrix the clustering algorithm operates on. A poorly formed statement does not just produce a bad data point — it degrades the integrity of the entire output.

The most common and most damaging failure mode is the **compound statement**: a statement that contains two separate claims. When a participant agrees with one claim but not the other, they cannot vote Agree or Disagree accurately — they vote Pass. The Small et al. (2021) paper is explicit: compound statements "elicit more passes when participants agree with one point, but not others," and identifies this as one of the most tractable problems to address. At scale, high Pass rates on compound statements deprive the system of the signal it needs to form meaningful clusters.

Seed statements — those written by facilitators before the conversation opens — have an outsized effect. They are the earliest content, receive the most votes, and frame what the conversation is about. Poorly written seed statements propagate through the entire opinion map.

---

## Principles

### 1. Atomicity — one claim per statement

Each statement should make exactly one claim. If a statement contains two claims joined by "and," "but," "because," or a comma, it should almost certainly be split into two statements.

**Why it matters:** A participant who agrees with one part but not the other cannot vote accurately. Their Pass vote removes their data from the algorithm without conveying any information.

| Bad (compound) | Good (atomic) |
|---|---|
| "Wikipedia should require reliable sources and editors should disclose conflicts of interest." | "Wikipedia should require articles to cite reliable sources." |
| | "Wikipedia editors should disclose conflicts of interest when editing related articles." |
| "Wikimedia should prioritise editor diversity because the current editor base is unrepresentative." | "Wikimedia should prioritise increasing the diversity of active editors." |
| | "The current Wikipedia editor base does not adequately represent the global reading public." |

---

### 2. Neutrality — describe, don't lead

The phrasing of a statement should not predispose a participant toward one answer. Loaded language, rhetorical questions, and embedded assumptions introduce noise by making it harder to separate agreement with the underlying claim from agreement with (or aversion to) the framing.

**Why it matters:** The Open Rights Group / Demos study found a measurable framing effect in a real Polis conversation: the same policy framed as "reducing red tape" received 56% support; a different framing of the same policy received opposition. Framing effects are not theoretical — they show up in the data.

| Bad (loaded / leading) | Good (neutral) |
|---|---|
| "Wikipedia's bureaucratic deletion process unjustly silences new editors." | "Wikipedia's articles-for-deletion process discourages new editors from contributing." |
| "Shouldn't the Wikimedia Foundation be more transparent about grant decisions?" | "The Wikimedia Foundation should make its grant decision process more transparent." |
| "Deleting unhelpful Wikipedia articles keeps the project high-quality." | "Wikipedia should maintain stricter standards for which articles are retained." |

---

### 3. Concreteness — avoid vague aspiration

Statements should refer to something specific enough that a vote conveys information. A statement like "Wikimedia should support a healthier community" is technically a claim, but near-universal agreement tells us almost nothing about opinion structure.

**Why it matters:** The algorithm finds genuine disagreements and areas of consensus. Vague statements produce uninformative agreement and waste participant attention without adding signal.

| Bad (vague) | Good (concrete) |
|---|---|
| "Wikimedia should support a healthier community." | "The Wikimedia Foundation should fund mental health resources for active Wikipedia editors." |
| "Wikipedia needs to do better on diversity." | "Wikipedia's paid fellowship programmes should prioritise recruiting editors from under-represented regions." |

---

### 4. Appropriate scope

A statement that almost everyone agrees with regardless of opinion group produces no useful clustering signal. A statement relevant to only a tiny slice of participants wastes the attention of everyone else.

**Why it matters:** Scope determines what kind of opinion structure the statement can reveal. Very broad statements ("Wikipedia should be accurate") and very narrow statements ("The font size on the disambiguation notice for 'Mercury' should be changed") both contribute little.

| Bad (too broad) | Good (scoped) |
|---|---|
| "Wikipedia should be accurate and reliable." | "Wikipedia should require secondary sources for biographical claims about living people." |

---

### 5. Statement form — make a claim, not a question or title

A statement is a declarative claim. Questions cannot be voted Agree or Disagree. Topics and titles are not claims.

| Bad (question) | Bad (title) | Good (statement) |
|---|---|---|
| "Should Wikipedia allow AI-generated content?" | "AI-generated content on Wikipedia." | "Wikipedia should allow AI-generated content if it meets the same sourcing standards as human-written content." |

---

## Seeding guidance

A well-seeded conversation typically starts with **10–15 statements** written by the facilitator (EA Forum practitioner guide). Too few and the conversation space is poorly defined; too many and the facilitator is over-determining the opinion landscape.

Seed statements should cover:
- The range of perspectives likely to exist — not just the facilitator's preferred framing
- Both diagnostic claims (what is the problem?) and policy claims (what should be done?)
- Areas where genuine disagreement is expected, not just easy consensus

Seed statements receive disproportionately more votes than participant-submitted statements because they are present from the start and routed to all participants. This makes their quality especially important.

**On moderation of participant-submitted statements:** The Computational Democracy Project recommends that moderators remove only abusive content, not statements they consider "off-topic," "duplicative," or low-quality. Removing non-abusive statements risks silencing perspectives that challenge the facilitator's framing — particularly those from communities whose views are less represented in the seed set.

---

## Sources

| Source | Used for | URL |
|---|---|---|
| Small, Bjorkegren, Erkkilä, Shaw, Megill (2021). "Polis: Scaling Deliberation by Mapping High Dimensional Opinion Spaces." *RECERCA*, 26(2). | Compound statement failure mode (Section 3.4.6), seed statement influence (3.4.1), moderation guidance (3.3) | https://gwern.net/doc/sociology/2021-small.pdf *(confirmed accessible)* |
| Saffron Huang, Divya Siddarth et al. (2023). "Opportunities and Risks of LLMs for Scalable Deliberation with Polis." arXiv:2306.11932. | Compound statement problem, framing requirements, seeding influence | https://arxiv.org/abs/2306.11932 *(confirmed accessible)* |
| EA Forum. "Polis: why and how to use it." | 10–15 seed statement recommendation, 1-in-10 participant ratio, 140-character limit | https://forum.effectivealtruism.org/posts/9jxBki5YbS7XTnyQy/polis-why-and-how-to-use-it *(confirmed accessible)* |
| Open Rights Group & Demos. "Democratic Innovations: Polis and the Political Process." (UK, 2020–21). | Framing effects (56% support example), 997-participant study | https://www.openrightsgroup.org/publications/democratic-innovations-polis-and-the-political-process/ *(confirmed accessible)* |
| Computational Democracy Project. "Lottery-Selected Assemblies." | Moderation policy; seed coverage of breadth of opinion | https://compdemocracy.org/polis/book/lottery-selected-assemblies/ *(confirmed accessible)* |
| UK Policy Lab. "Cutting through complexity using collective intelligence." openpolicy.blog.gov.uk. (2022). | Practitioner account: panel moderation approach for submitted statements | https://openpolicy.blog.gov.uk/2022/10/11/cutting-through-complexity-using-collective-intelligence/ *(confirmed accessible)* |
| PolisNL. "Hoe Polis werkt." polisnl.org. | Seed statement framing guidance | https://polisnl.org/hoe-polis-werkt *(confirmed accessible; limited content)* |
