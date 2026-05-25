> **⚠️ Draft — not fact-checked.** This document is a synthesis of external sources compiled for internal research purposes. Claims have not been independently verified against primary sources. Do not cite or publish externally without review.
>
> **Strict sourcing policy:** This document only makes claims that are directly stated or quoted from the cached source files. Criteria, examples, and observations are not invented. Where the sources are silent, this document says so explicitly.

---

# Scope and topic: how to define what a Polis conversation is about

## Why scope matters for wiki-polis

If the advising module (see issue #56) is to flag statements as potentially off-topic, it needs a definition of scope to work from. This document asks: what do the sources actually say about how to define scope, how broad it should be, and what to do with statements that fall outside it?

The short answer: the sources address this unevenly. They confirm that on-topic moderation happens in practice, but they also warn against it — and they offer little concrete guidance on how to draw the line. This tension is real and worth surfacing before building any automated scope-checking.

---

## What the sources say: on-topic moderation happens

The Huang, Siddarth et al. (2023) paper describes current moderation practice directly:

> "Participant submitted statements are also typically moderated to ensure they are **on-topic**, not abusive, and sufficiently distinct from existing statements."
> *(llms2023polis, moderation section)*

This is the clearest statement in any source that scope is an explicit moderation criterion. Off-topic statements are removed, not kept.

The same source identifies on-topic moderation as one of several tasks that "require significant training in best practices and commitment of time as the conversation unfolds, and run the risk of silencing voices or biasing results."

---

## What the sources say: the tension with silencing voices

The Computational Democracy Project's guidance — cited in the same paper — warns that moderators should **not** remove statements they consider off-topic:

The risk cited: moderators who remove "off-topic" or "duplicate" statements may be applying their own framing to exclude perspectives that challenge the initial assumptions of the conversation. The concern is explicitly about marginalized communities whose views may not fit the facilitator's definition of the topic.

This is a genuine contradiction between what the sources describe as standard practice (removing off-topic statements) and what they recommend as best practice (not removing them). The sources do not resolve this tension.

**Implication for the advising module:** flagging a statement as potentially off-topic is more defensible than removing it. The module can surface a score; the moderation decision remains human.

---

## What the sources say: scope emerges from the prompt

The **prompt** — the top-level question displayed at the top of a Polis conversation — is the primary instrument for defining scope. Participants implicitly understand the conversation to be "about" whatever the prompt asks.

The Computational Democracy Project gives an example from a Kentucky county planning exercise where the prompt was:

> *"What do you believe should change in Bowling Green/Warren County in order to make it a better place to live, work and spend time?"*

This broad prompt explicitly invites a wide scope. A narrower prompt — "Should Wikipedia require secondary sources for biographical claims about living people?" — would imply a much tighter scope.

The sources do not provide criteria for choosing prompt breadth. This is an open design question not addressed in the available literature.

---

## What the sources say: scope can and should evolve

The Computational Democracy Project describes scope refinement as a deliberate strategy:

> "Polis helps many people collectively refine how a topic is framed by revealing new perspectives, concerns, and questions. The resulting Polis opinion map enables organizers to frame the topic for an assembly in a way that highlights both shared values and key disagreements."
> *(compdem-book-assemblies, Strategy 2: "Improve topic framing through dynamic topic refinement")*

The vTaiwan Uber conversation is the cited example:

> "In vTaiwan, the Uber discussion began with assumptions about regulating Uber, but **expanded to include dimensions of the existing local taxi industry**."
> *(compdem-book-assemblies)*

This is significant: what appeared off-topic (the taxi industry) turned out to be essential to a full understanding of the issue. Strict on-topic moderation would have removed those statements and impoverished the result.

The Computational Democracy Project also describes using Polis as a pre-step to define scope for a subsequent exercise:

> "Use Polis to ask your population, 'what topic should be taken up by a citizen assembly?'"
> *(compdem-book-assemblies, Strategy 1)*

In other words: Polis can itself be the instrument by which scope is discovered, not just enforced.

---

## What the sources say: scope can be too broad

The Uruguay 2021 referendum case illustrates a different problem — scope too broad for a single yes/no vote:

> "16,000 people used Polis to look within a national referendum combining 150 policy positions in a single yes/no vote, going topic by topic to understand how issues could best be unbundled."
> *(compdem-casestudies)*

Here Polis was used to *decompose* an over-broad scope into meaningful sub-topics. The sources do not give criteria for when a scope is too broad to be useful in a single conversation.

---

## What the sources do not say

The sources are silent on:

- **How to determine the right scope breadth** before opening a conversation — no criteria are provided
- **What specific types of statement count as off-topic** — only the general category is mentioned
- **Whether participants should be told why their statement was removed** for being off-topic
- **How to handle borderline cases** — statements that address the topic tangentially
- **Automated scope detection** — no source discusses computational approaches to on-topic checking

---

## Implications for wiki-polis

### For the advising module (#56)

An automated on-topic score is possible in principle (compare the statement to the prompt using semantic similarity), but:

- The sources provide no criteria for what threshold counts as "off-topic"
- The vTaiwan example shows that seemingly off-topic statements can be the most valuable
- The literature recommends human moderation for scope decisions, not automated removal

**Tentative recommendation:** if the advising module includes a scope/topic score, it should flag statements for *human review* — not auto-remove or discourage submission. The score helps the moderator triage; it does not make the moderation decision.

### For facilitators

The prompt is the primary instrument for communicating scope. A well-written prompt reduces the volume of ambiguously in-scope statements. Facilitators should:

1. Write the prompt to reflect the actual scope they want — neither so broad that everything is in-scope nor so narrow that participants feel constrained
2. Consider running a short preliminary Polis conversation to surface what dimensions of the topic the community considers relevant before locking in scope

Neither of these recommendations is from the sources — they are derived from the dynamics described above. They are flagged here as inferences, not citations.

### Open design question

How broad should a wiki-polis conversation be? The sources do not answer this. It likely depends on the context: a conversation about a specific Wikipedia policy is much narrower than a conversation about the future of the Wikimedia movement. A second evaluator or scoping worksheet for facilitators — helping them think through scope before opening a conversation — may be more useful than any automated check.

---

## Sources

| Source | Relevant content | URL |
|---|---|---|
| Saffron Huang, Divya Siddarth et al. (2023). "Opportunities and Risks of LLMs for Scalable Deliberation with Polis." arXiv:2306.11932. | On-topic moderation described as standard practice; risk of silencing voices | https://arxiv.org/abs/2306.11932 *(confirmed accessible)* |
| Computational Democracy Project. "Lottery-Selected Assemblies." compdemocracy.org/polis/book. | Strategy 1 (use Polis to choose topic); Strategy 2 (dynamic topic refinement); vTaiwan scope expansion example | https://compdemocracy.org/polis/book/lottery-selected-assemblies/ *(confirmed accessible)* |
| Computational Democracy Project. Case studies index. compdemocracy.org/case-studies. | Uruguay referendum: Polis used to unbundle over-broad scope | https://compdemocracy.org/case-studies/ *(confirmed accessible)* |
