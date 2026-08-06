# Aggregation & representation — long-term direction (pointer)

The **long-term theoretical strategy** for how wiki-polis selects featured statements and
aggregates outcomes — Justified Representation (JR), divisiveness metrics, the three utility
definitions (vote / semantic / voting-pattern), and the **cross-round voting-pattern
carry-forward** idea — is documented as a private research/strategy note, kept out of the
product issues on purpose:

> **`polis-study/private/reimagining-aggregation.md`** (private repo)

It is **on hold** as an implementation direction — it depends on machinery the current
mechanics don't have (a stable opinion-group model, embeddings, cross-round state). It is
grounded in "Question the Questions: Auditing Representation in Online Deliberative Processes"
(De, Gelauff, Goel, Milli, Procaccia, Siu — [arXiv:2511.04588](https://arxiv.org/abs/2511.04588)).

The concrete product issues stay scoped to current mechanics and link back to that note for the
long view:

- **#268** — featured-candidate ranking (near-term: deduplicated counts + report the actual
  agreement %; the principled selection/representation objective is deferred to the note).
- **#226 / #228 / #230 / #231** — outputs model, initial clustering, report content, dataset
  export (the representation/aggregation theory was moved to the note).
- **#207 / #208** — the embedding sidecar the semantic-utility path depends on.
