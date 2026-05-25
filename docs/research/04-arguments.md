> **⚠️ Draft — not fact-checked.** This document is a synthesis of external sources compiled for internal research purposes. Claims have not been independently verified against primary sources. Do not cite or publish externally without review. Sources are listed at the bottom; URLs are only included where access was confirmed.

> **⚠️ Important scope note.** Arguments are **not part of standard Polis**. They are not discussed in any of the source documents as an existing feature. This document constructs principled guidance for an argument feature specific to wiki-polis, drawing on what the sources say about deliberation quality and the mechanics of the Polis system. Claims derived by inference rather than direct citation are labelled as such.

---

# Writing good arguments (wiki-polis feature)

## What arguments are for

In standard Polis, the only participant actions are voting (Agree / Disagree / Pass) and submitting new statements. Voting data produces the opinion map; the algorithm can show *what* people think but not *why*.

wiki-polis introduces an **arguments feature** — participants can write a supporting or opposing argument for a specific statement. Arguments are annotations on the voting data, not inputs to the clustering algorithm. Their purpose is to capture the reasoning behind votes, providing qualitative depth that the vote matrix cannot.

This distinction matters for how arguments should be written and moderated:
- Statements are neutral claims designed to be voted on. Arguments are directional by design.
- Statements are primary data for the algorithm. Arguments are supplementary material for human readers.
- Statement moderation criteria focus on form (atomicity, neutrality). Argument moderation criteria focus on quality of reasoning.

## Principles for writing good arguments

These principles are derived from the goals of the Polis system and from general deliberative standards. They are not directly stated in the source literature, which does not discuss arguments as a feature.

### 1. State your direction clearly

An argument is for or against a specific statement. Make clear which. An argument that could apply to either side adds no information.

| Unclear | Clear |
|---|---|
| "Sourcing is important for Wikipedia's credibility." | "**For:** Requiring secondary sources for biographical claims would reduce the number of unsourced assertions about living people, which is one of Wikipedia's most significant credibility risks." |

---

### 2. Add information — don't restate your vote

An argument that only says "I agree because this is important" contains no more information than the vote itself. A good argument adds a reason, an example, an implication, or a constraint that other participants may not have considered.

| Weak (restates vote) | Strong (adds information) |
|---|---|
| "I disagree because this would be bad for the project." | "**Against:** This would disproportionately affect new editors, who are less likely to know sourcing conventions and more likely to be discouraged by rejection. The burden should be on reviewers to guide, not just remove." |

---

### 3. One line of reasoning per argument *(atomicity applied to arguments)*

The same atomicity principle that applies to statements applies to arguments. An argument that makes multiple separate points makes it harder to identify which point was persuasive to other readers.

| Compound | Atomic |
|---|---|
| "This is good because it improves quality, and also because it aligns with WMF strategy, and it would help with editor retention too." | Write three separate arguments, one for each reason. |

---

### 4. Be specific

Vague arguments ("this matters," "this is complicated," "reasonable people disagree") add friction without adding signal. Specific arguments — naming a mechanism, citing a precedent, identifying a consequence — are more useful to readers and more likely to shift thinking.

---

### 5. Acknowledge tradeoffs

An argument that only presents the case for one side, without acknowledging what is being traded away, is less persuasive and less useful than one that engages with the tension. *(Derived from deliberative democracy literature on argument quality; not directly cited in sources.)*

---

### 6. Argue the claim, not the person

Arguments should engage with the statement, not with who submitted it or who is likely to agree with it. This is consistent with Wikimedia's existing community norms (assume good faith, no personal attacks).

---

## On moderation of arguments

Arguments are more sensitive to moderate than statements, because they contain explicit reasoning that may be disputed. The Open Rights Group / Demos study found that 52% of participant-submitted *statements* were non-constructive — the proportion for arguments may differ, but the moderation challenge is real.

The Computational Democracy Project's guidance for statements — remove only abusive content, not content that is merely off-topic or wrong — applies with even more force to arguments. Removing arguments because a moderator disagrees with the reasoning would undermine the purpose of the feature.

Recommended moderation standard for arguments:
- **Remove:** personal attacks, harassment, content that violates the Wikimedia Universal Code of Conduct
- **Keep:** arguments the moderator disagrees with, arguments that are poorly reasoned (but not abusive), arguments that are repetitive

---

## Sources

| Source | Used for | URL |
|---|---|---|
| Saffron Huang, Divya Siddarth et al. (2023). "Opportunities and Risks of LLMs for Scalable Deliberation with Polis." arXiv:2306.11932. | Polis output limitations (Section 2.2: automated report "not suitable for consumption without dozens of hours of manual human analysis"); group-informed consensus goal (Section 2.3) | https://arxiv.org/abs/2306.11932 *(confirmed accessible)* |
| Small, Bjorkegren, Erkkilä, Shaw, Megill (2021). "Polis: Scaling Deliberation by Mapping High Dimensional Opinion Spaces." *RECERCA*, 26(2). | Compound statement failure mode (applied by inference to compound arguments); moderation guidance | https://gwern.net/doc/sociology/2021-small.pdf *(confirmed accessible)* |
| Open Rights Group & Demos. "Democratic Innovations: Polis and the Political Process." (UK, 2020–21). | 52% non-constructive submission rate; high curation ratio in practice | https://www.openrightsgroup.org/publications/democratic-innovations-polis-and-the-political-process/ *(confirmed accessible)* |
| UK Policy Lab. "Cutting through complexity using collective intelligence." (2022). | Polis used to "stress-test existing policy"; role of qualitative reasoning alongside voting | https://openpolicy.blog.gov.uk/2022/10/11/cutting-through-complexity-using-collective-intelligence/ *(confirmed accessible)* |
