> **⚠️ Draft — not fact-checked.** This document is a synthesis of external sources compiled for internal research purposes. Claims have not been independently verified against primary sources. Do not cite or publish externally without review. Sources are listed at the bottom; URLs are only included where access was confirmed.

---

# Polis: objectives and the role of statements

## What Polis is trying to accomplish

Polis is a real-time system for gathering, analysing, and understanding what large groups of people think in their own words. Its core design goal is to surface **cross-group consensus** — positions that are broadly shared across opinion clusters, not just majority positions or the views of the most active participants.

This is a deliberate departure from most online discussion formats. Traditional forums, comment sections, and polls tend to amplify the loudest voices, reward engagement over thoughtfulness, and surface conflict rather than agreement. Polis inverts that dynamic: the algorithm is explicitly designed to find statements that bridge groups rather than divide them.

Audrey Tang, Taiwan's Digital Minister, described the effect: *"Polis is quite well known in that it's a kind of social media that instead of polarizing people to drive so-called engagement or addiction or attention, it automatically drives bridge-making narratives and statements. So only the ideas that speak to both sides or to multiple sides will gain prominence."* (Wikipedia article on Pol.is)

Polis is not a decision-making tool. It is a step in a process — a structured listening exercise that produces a map of where a community stands, which a facilitator or institution can then act on.

## How the algorithm works

Participants vote Agree, Disagree, or Pass on short statements. This produces a **vote matrix**: rows are participants, columns are statements, and cells contain votes. In practice, the matrix is over 90% empty for large conversations — most participants vote on only a fraction of statements.

The algorithm applies **PCA** (Principal Component Analysis) to reduce this sparse matrix to a lower-dimensional space, and then **K-means clustering** to group participants whose voting patterns are similar. The result is an opinion map showing where the major clusters of opinion lie, and — critically — which statements received high agreement across multiple clusters (cross-cluster consensus) versus which statements divided participants along cluster lines.

A statement that 78% of cluster A and 80% of cluster B both agree with is a genuine point of consensus. A statement that 95% of cluster A agrees with but only 20% of cluster B does is a point of division — still useful information, but not consensus.

## The role of statements

Statements are the atomic units that participants vote on. They are the primary input to the algorithm, and statement quality directly determines output quality.

A statement is not just a unit of content — it is a **measurement instrument**. Each vote on a statement is a data point. If the instrument is poorly designed, the data it produces is unreliable, and the opinion map built from that data will misrepresent where people actually stand.

The most common failure mode is the **compound statement** — a statement that contains two separate claims. When a participant agrees with one claim but not the other, they cannot vote Agree or Disagree accurately, so they vote Pass. At scale, compound statements systematically inflate the Pass rate and remove data from the clustering algorithm. The Small et al. (2021) paper identifies this explicitly as one of the most tractable and common problems in Polis conversations.

## The wikisurvey mechanic

Polis operates as a "wikisurvey": participants do not just vote on statements written by the facilitator — they can submit their own. In practice, roughly 1 in 10 participants submit a new statement; the other 9 vote. This ratio matters for two reasons:

1. **Facilitator seed statements have outsized influence.** They are the earliest content in the conversation, receive the most votes, and frame what the conversation is about. Poorly written seed statements propagate into the opinion map.
2. **Participant-submitted statements extend the opinion space.** They surface perspectives the facilitator did not anticipate. Moderation policies that remove "off-topic" or "duplicate" statements risk silencing these contributions.

## How Polis differs from other formats

| Format | Who sets the agenda | Captures nuance | Scales to thousands | Surfaces consensus |
|---|---|---|---|---|
| Survey / poll | Researchers | No | Yes | Partially |
| Forum / comment section | Anyone | Yes | Poorly | No |
| Citizens' assembly | Facilitators + lottery | Yes | No | Yes |
| Polis | Facilitators + participants | Partially | Yes | Yes |

---

## Sources

| Source | Used for | URL |
|---|---|---|
| Small, Bjorkegren, Erkkilä, Shaw, Megill (2021). "Polis: Scaling Deliberation by Mapping High Dimensional Opinion Spaces." *RECERCA, Revista de Pensament i Anàlisi*, 26(2). | Algorithm mechanics, compound statement failure mode, facilitator practices | https://gwern.net/doc/sociology/2021-small.pdf *(confirmed accessible)* |
| Saffron Huang, Divya Siddarth et al. (2023). "Opportunities and Risks of LLMs for Scalable Deliberation with Polis." arXiv:2306.11932. | Algorithm details (Sections 1.1, 2.3, 2.4, 3.4), participant scale statistics | https://arxiv.org/abs/2306.11932 *(confirmed accessible)* |
| Computational Democracy Project. "Polis." compdemocracy.org. | Platform overview, design philosophy | https://compdemocracy.org/polis/ *(confirmed accessible)* |
| Computational Democracy Project. "Lottery-Selected Assemblies." compdemocracy.org/polis/book. | Polis as a step in process; integration with citizen assemblies | https://compdemocracy.org/polis/book/lottery-selected-assemblies/ *(confirmed accessible)* |
| EA Forum. "Polis: why and how to use it." | Wikisurvey mechanic, 1-in-10 ratio, seeding guidance | https://forum.effectivealtruism.org/posts/9jxBki5YbS7XTnyQy/polis-why-and-how-to-use-it *(confirmed accessible)* |
| Open Rights Group & Demos. "Democratic Innovations: Polis and the Political Process." (2020–21, UK). | Validation with 997 participants; framing effects | https://www.openrightsgroup.org/publications/democratic-innovations-polis-and-the-political-process/ *(confirmed accessible)* |
| Wikipedia contributors. "Pol.is." Wikipedia. | Audrey Tang quote; history and reception | https://en.wikipedia.org/wiki/Pol.is *(confirmed accessible)* |
