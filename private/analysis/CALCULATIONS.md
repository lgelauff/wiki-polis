# How every number is calculated

Written so the figures can be checked rather than believed. For each statistic: what
it means, exactly how it is computed, which population it runs over, and where the
code is. Every threshold named here is declared at the top of `pipeline.py` under
"Thresholds" — none is buried in a function.

To reproduce anything below:

```bash
./.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
import pipeline as P, methods as M
b = P.load_bundles('2026-nlwiki-arbcom_bundle'); C = b.conversations[0]
print(P.participation_funnel(b, C))"
```

---

## Who is counted

**`machine_participants()` — `pipeline.py`.** A participant is machine-made when
*every* vote it cast landed within `MACHINE_LAG_MS` (2000 ms) of that statement being
created. Observed lags for the flagged accounts are 5–51 ms; the fastest human vote in
the data is orders of magnitude slower. Deliberately behavioural rather than based on
`identity_linked`, so a real person missing an identity record is not silently deleted.
Cross-check: the behavioural test flagged exactly the same 17 accounts as the identity
join, from independent evidence.

**Filtering.** `Bundles.phase()` drops them from every read by default. The only caller
that passes `include_machine=True` is `reproduction_gate()`, which must feed the replica
the same population the server had or it would be comparing two different things.

**Analysis population.** People with at least `POLIS_VOTE_THRESHOLD` (7) votes —
Polis's own clustering cutoff, `min(7, n_statements)` in `conversation.clj`. 22 people
here.

## Vote matrix

**`build_matrix()` — `pipeline.py`.** Rows are participants, columns statements, cells
raw Polis votes (`-1` agree, `+1` disagree, `0` pass, `NaN` did not vote).

- `mod_out='zero'` sets the *whole column* of a moderated-out statement to 0, including
  for people who never voted on it. This matches `named_matrix/zero-out-columns` in the
  engine. **It inflates the non-null count**, which is why in-conv must not be derived
  from this matrix — see below.
- `drop_unvoted=True` removes columns nobody voted on (43 of 107 here). These are
  all-`NaN`, contribute nothing to the PCA, and only make the statement count overstate
  what was deliberated.

**In-conv.** `replica_labels(..., vote_counts=…)` supplies real vote counts separately,
because `run_replica` otherwise counts non-null cells — and after zeroing, everybody
would clear the threshold. The engine computes `:in-conv` from `user-vote-counts`
(`conversation.clj:243`) while zeroing applies only to `:rating-mat`
(`conversation.clj:205`). Getting this wrong produced 46 clustered participants against
the server's 34.

## Agreement between two people

**`agreement_graph()` — `methods.py`.** For each pair, over statements *both* voted on
decisively (passes excluded — skipping is not agreeing):

```
agreement = mean(vote_i == vote_j)                     over shared decisive votes
weight    = max(0, (agreement - 0.5) * 2)              rescaled to [0, 1]
```

Pairs sharing fewer than `MIN_PAIR_OVERLAP` (5) statements get no edge. A pair agreeing
at or below chance gets weight 0, so the graph encodes attraction only.

## Group quality

| statistic | what it means | computed by |
|---|---|---|
| **silhouette** | how much closer a person sits to their own group than the nearest other, −1 to +1 | `polis_replica.silhouette`, the engine's own definition over base-cluster centres |
| **modularity** | how much more densely connected a group is than chance predicts, given the degree distribution. **≤ 0 means no community structure**; a single community scores exactly 0 by definition | `igraph`'s `Graph.modularity`, via `leidenalg` |
| **adjusted Rand index** | agreement between two groupings: 1.0 identical, 0.0 no better than chance | `sklearn.metrics.adjusted_rand_score`, over people labelled by both |

**Multilayer modularity — the trap.** `leidenalg.find_partition_multiplex` returns
`(membership, improvement)`. **The second value is the optimiser's improvement, not a
modularity.** It is unbounded and not comparable with anything; an earlier version of
this analysis reported it as 46.612. `multilayer_leiden()` now scores the joint
partition by the modularity it achieves *in each layer* and reports the mean (0.101),
which is directly comparable with the single-layer numbers.

## Deduplication

**`redundant_pairs()` — `methods.py`.** Three signals, in this order:

1. **Normalised text equality** (`normalise_text`: lower-case, strip punctuation,
   number words → digits). Two statements identical after normalising are the same
   statement whatever the votes say. Catches `"2 weken"` / `"twee weken"`. Does *not*
   merge different numbers: `duizend` → 1000, `vijfhonderd` → 500.
2. **Vote concordance** — among people who voted decisively on both, the fraction
   voting the same way. `≥ 0.9` with at least 5 such people → redundant.
3. Otherwise **kept separate.** Preserving a real distinction is the safer error.

Candidate pairs come from `similar_statement_groups()` at `SIMILARITY_THRESHOLD` (0.85)
cosine similarity over `paraphrase-multilingual-mpnet-base-v2` embeddings — the same
model the app's similarity sidecar uses.

**Text similarity alone is not sufficient and gets this wrong.** In the nlwiki
consultation, *"at least a thousand edits"* vs *"at least five hundred edits"* scores
0.976, and a pair differing only in *"except when"* vs *"also when"* scores 0.993 —
glossed from the Dutch here, since statement text stays in the bundle rather than in
this repository. 36 pairs that look near-identical are ones participants demonstrably
voted differently on.

## Wording comparisons

**`head_to_head()` / `wording_effect()` — `methods.py`.** Each rewrite is compared with
its parent over people who voted decisively on *both*. Below
`MIN_DECIDED_FOR_HEAD_TO_HEAD` (7) such people, no comparison is attempted.

- per-pair test: exact binomial on the discordant pairs (`scipy.stats.binomtest`)
- across pairs: Benjamini–Hochberg correction, because a family of *k* variants yields
  *k(k−1)/2* comparisons over the same people — one family of 13 contributes 78
- the ordering effect (whether the earlier wording wins) is reported **separately**,
  because variants are compared in id order, so pooling the raw counts measures
  earlier-versus-later and not wording

**Counts of people, never counts of pairs.** `wording_participation()` reports how many
distinct people voted differently on two wordings (16). Summing discordant pairs gives
319, which is not a number of people — one person inside a 13-variant family can
generate 42 discordances alone.

## The refinement ladder

**`method_ladder()` — `methods.py`.** Both methods at three cumulative levels, all
starting from a matrix with unvoted statements already removed.

- **naive** — the method as the tool applies it
- **deduplicated** — redundant pairs merged as above, a participant's votes across
  merged columns averaged
- **layered** — statements split into topics by agglomerative clustering over
  embeddings (cosine, average linkage); layers with fewer than 4 statements are
  skipped. **Leiden uses true multilayer optimisation** (`multilayer_leiden`, one graph
  per topic optimised jointly). **k-means uses consensus across layers** — a
  co-classification matrix, then agglomerative clustering on `1 − co-occurrence`.

Those two are not the same method and the table says so in the `quality is` column.
Multilayer modularity is the direct approach for genuinely layered data; consensus
clustering (Lancichinetti–Fortunato) is designed for combining repeated runs of one
algorithm. k-means has no multilayer formulation, hence the difference.

**Singletons.** `split_outliers()` separates one-person communities and reports them as
`unplaced` rather than as groups — OSLOM's "homeless nodes", and Infomap refuses to emit
singletons at all. Zero on this data. *(Open: outliers deserve their own treatment
rather than only being excluded — see the note in `.claude/notes-clustering-findings.md`.)*

## Is any of it real

**`subset_search.py`.** Samples random subsets of statements at several sizes, records
the best modularity Leiden finds, and repeats the whole search on data where each
statement's votes have been shuffled across people — preserving that statement's
agree/disagree balance while destroying any relationship *between* statements.

Read the *distributions*, not the maxima: at 8 statements both real and shuffled reach
high modularity by chance (medians 0.062 and 0.063). The informative comparison is at
48 statements — 51 of 150 real subsets score above zero against 0 of 150 shuffled.

**This null is not the standard one.** The literature would use a configuration model
preserving both margins. Shuffle-within-statements preserves each statement's balance
and each person's vote count but not the joint degree structure.
