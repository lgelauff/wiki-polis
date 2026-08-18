"""Comparison methods on top of the server's own clustering.

Two questions this module answers, both raised as the point of the analysis:

  1. **How much clustering is actually there?** Polis always returns 2–5 groups; it
     never says "there are no groups". So an independent method is needed to tell a
     real division from a partition of noise. Leiden community detection on a
     participant-agreement graph is that second opinion, plus a stability sweep
     that reports how many people sit on a boundary rather than inside a group.

  2. **Does phrasing move votes?** Consultations accumulate near-duplicate
     statements — one proposition in three wordings. For an organiser choosing
     which phrasing to put to a vote, the head-to-head between those variants is
     the decision, and it is invisible in a whole-conversation view.

Neither method replaces `math_main`. The server's clustering stays the headline;
these say how much weight it can bear.
"""
from __future__ import annotations

import collections
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pipeline import (MIN_DECIDED_FOR_HEAD_TO_HEAD, MIN_PAIR_OVERLAP, RAW_AGREE,
                      RAW_DISAGREE, SIMILARITY_THRESHOLD, Bundles, Matrix,
                      compare_labels, server_labels)

EMBEDDING_MODEL = os.environ.get(
    'ANALYSIS_EMBEDDING_MODEL',
    'sentence-transformers/paraphrase-multilingual-mpnet-base-v2')


# ── participant agreement graph ──────────────────────────────────────────────

def agreement_graph(matrix: Matrix, *, min_overlap: int = MIN_PAIR_OVERLAP,
                    restrict_pids: list[int] | None = None):
    """Participant × participant agreement, over statements both actually voted on.

    Deliberately sparse-aware rather than imputed: two people are compared only on
    the statements they both voted, and only if they share at least `min_overlap`
    of them. Passes are excluded — a pass is not an opinion, and counting it as
    agreement would inflate similarity between two people who simply skipped a lot.

    Edge weight rescales agreement from [0.5, 1] to [0, 1]; a pair agreeing at or
    below chance gets no edge, so the graph encodes attraction only.
    """
    pids = list(matrix.pids)
    values = matrix.values
    if restrict_pids is not None:
        keep = set(restrict_pids)
        idx = [i for i, pid in enumerate(pids) if pid in keep]
        pids = [pids[i] for i in idx]
        values = values[idx, :]

    opinion = np.where(np.isin(values, [RAW_AGREE, RAW_DISAGREE]), values, np.nan)
    n = len(pids)
    weights = np.zeros((n, n))
    overlaps = np.zeros((n, n), dtype=int)
    for i in range(n):
        for j in range(i + 1, n):
            both = ~np.isnan(opinion[i]) & ~np.isnan(opinion[j])
            k = int(both.sum())
            overlaps[i, j] = overlaps[j, i] = k
            if k < min_overlap:
                continue
            agree = float(np.mean(opinion[i, both] == opinion[j, both]))
            weight = max(0.0, (agree - 0.5) * 2)
            weights[i, j] = weights[j, i] = weight
    return pids, weights, overlaps


def leiden_communities(pids, weights, *, resolution: float = 1.0, seed: int = 20260606):
    """Leiden on the agreement graph. Returns {pid: community}."""
    import igraph as ig
    import leidenalg

    n = len(pids)
    edges, edge_weights = [], []
    for i in range(n):
        for j in range(i + 1, n):
            if weights[i, j] > 0:
                edges.append((i, j))
                edge_weights.append(float(weights[i, j]))

    graph = ig.Graph(n=n, edges=edges)
    graph.es['weight'] = edge_weights
    partition = leidenalg.find_partition(
        graph, leidenalg.RBConfigurationVertexPartition,
        weights='weight', resolution_parameter=resolution, seed=seed)
    return ({pids[i]: int(c) for i, c in enumerate(partition.membership)},
            float(partition.modularity))


def leiden_sweep(b: Bundles, gate: dict, *,
                 resolutions=(0.4, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0),
                 min_overlap: int = MIN_PAIR_OVERLAP) -> pd.DataFrame:
    """Leiden across resolutions, compared with the server's groups at each one.

    The resolution parameter, not the data, decides how many communities Leiden
    returns — so a single run proves nothing. The informative reading is the shape
    of this table: if the server's split is real, agreement with it should peak
    sharply at whatever resolution yields the same K, and K should be stable across
    a broad band of resolutions rather than climbing steadily.
    """
    server = gate['server']
    matrix = gate['matrix']
    in_conv = gate['replica']['in_conv']
    pids, weights, overlaps = agreement_graph(matrix, min_overlap=min_overlap,
                                              restrict_pids=in_conv)

    rows = []
    for resolution in resolutions:
        labels, modularity = leiden_communities(pids, weights, resolution=resolution)
        sizes = pd.Series(list(labels.values())).value_counts()
        singletons = int((sizes == 1).sum())
        ari, n_common = compare_labels(server['labels'], labels)
        rows.append({
            'resolution': resolution,
            'K_leiden': len(sizes),
            'K_server': server['K'],
            'largest_community': int(sizes.iloc[0]) if len(sizes) else 0,
            'singletons': singletons,
            'modularity': round(modularity, 4),
            'ari_vs_server': round(ari, 4) if ari == ari else float('nan'),
            'n_compared': n_common,
        })
    out = pd.DataFrame(rows)
    out.attrs['n_nodes'] = len(pids)
    out.attrs['n_edges'] = int((weights > 0).sum() // 2)
    out.attrs['median_overlap'] = float(np.median(overlaps[np.triu_indices(len(pids), 1)]))
    return out


def cluster_stability(b: Bundles, gate: dict, *,
                      resolutions=(0.6, 0.8, 1.0, 1.25, 1.5),
                      seeds=(1, 2, 3, 4, 5), min_overlap: int = MIN_PAIR_OVERLAP) -> dict:
    """How reliably does each person land with the same people?

    Runs Leiden over a grid of resolutions and seeds and measures, for every pair,
    how often they end up in the same community. A person whose co-assignment is
    consistently near 0 or 1 sits inside a group; one hovering near 0.5 sits on a
    boundary and should not be described as belonging to either.
    """
    matrix = gate['matrix']
    # `gate` deliberately keeps machine accounts: reproducing the server's clustering
    # means feeding the replica the population the server had. Stability is a different
    # question — it describes people — and machine accounts wreck it. Each votes once,
    # so it shares no statements with anyone, gets no graph edge, and sits as an
    # isolated singleton that never moves between runs: trivially "decided", and here
    # they supplied most of the decided pairs. Drop them before measuring.
    machine = set(b.machine.get((gate['conv_key'], gate['phase']), {}))
    in_conv = [p for p in gate['replica']['in_conv'] if p not in machine]
    pids, weights, _ = agreement_graph(matrix, min_overlap=min_overlap,
                                       restrict_pids=in_conv)
    n = len(pids)
    if n < 2:
        return {'available': False, 'reason': 'too few in-conv participants'}

    together = np.zeros((n, n))
    runs = 0
    for resolution in resolutions:
        for seed in seeds:
            labels, _ = leiden_communities(pids, weights, resolution=resolution, seed=seed)
            member = np.array([labels[p] for p in pids])
            together += (member[:, None] == member[None, :]).astype(float)
            runs += 1
    together /= runs

    triu = np.triu_indices(n, 1)
    pair_scores = together[triu]
    # A pair is "decided" if the runs nearly always agree, either way.
    decided = float(np.mean((pair_scores > 0.9) | (pair_scores < 0.1)))

    # Self-comparisons are trivially 1.0 and must not drag the boundary score, so
    # they are excluded here — but the returned matrix keeps them, because a blank
    # diagonal in the heatmap reads as "never grouped with themselves".
    scored = together.copy()
    np.fill_diagonal(scored, np.nan)
    per_person = np.nanmean(np.minimum(scored, 1 - scored), axis=1)
    boundary = pd.DataFrame({'pid': pids, 'boundary_score': per_person.round(3)})
    boundary = boundary.sort_values('boundary_score', ascending=False)

    server = gate['server']
    key_by_pid = dict(zip(b.phase('participants', gate['conv_key'], gate['phase'])['pid'],
                          b.phase('participants', gate['conv_key'], gate['phase'])['person_key']))
    boundary['person_key'] = boundary['pid'].map(key_by_pid)
    boundary['server_group'] = boundary['pid'].map(server['labels'])

    return {
        'available': True,
        'n_runs': runs,
        'n_people': n,
        'pairs_decided': round(decided, 4),
        'mean_boundary_score': round(float(np.nanmean(per_person)), 4),
        'n_on_boundary': int((per_person > 0.25).sum()),
        'boundary': boundary,
        'co_assignment': pd.DataFrame(together, index=pids, columns=pids),
    }


# ── near-duplicate statement groups ──────────────────────────────────────────

@dataclass
class StatementGroup:
    group_id: int
    tids: list[int]
    texts: dict[int, str]
    declared_links: list[tuple[int, int]]

    def __len__(self) -> int:
        return len(self.tids)


def embed_statements(texts: list[str], model_name: str = EMBEDDING_MODEL) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    return model.encode(texts, normalize_embeddings=True)


def similar_statement_groups(b: Bundles, conv_key: str, phase: int = 2, *,
                             threshold: float = SIMILARITY_THRESHOLD,
                             include_declared: bool = True) -> tuple[list[StatementGroup], pd.DataFrame]:
    """Group statements that say near enough the same thing.

    Similarity is cosine over multilingual sentence embeddings (the same model the
    app's similarity sidecar uses, so "similar" means here what it means in the
    product). Groups are connected components at `threshold`: A~B and B~C puts all
    three together, which is what a chain of successive rewordings looks like.

    Declared provenance links are unioned in when present — a participant saying
    "this improves on that" is stronger evidence than any threshold.

    Returns the groups and the full pairwise table, so the threshold can be
    checked against the actual similarity distribution rather than assumed.
    """
    statements = b.phase('statements', conv_key, phase)
    statements = statements[statements['active'] & (statements['mod'] >= 0)]
    statements = statements[statements['txt'].notna() & (statements['txt'] != '')]
    if statements.empty:
        return [], pd.DataFrame()

    tids = statements['tid'].tolist()
    texts = statements['txt'].tolist()
    text_by_tid = dict(zip(tids, texts))
    vectors = embed_statements(texts)
    similarity = vectors @ vectors.T

    pairs = []
    n = len(tids)
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append({'tid_a': tids[i], 'tid_b': tids[j],
                          'similarity': float(similarity[i, j]),
                          'text_a': texts[i], 'text_b': texts[j]})
    pair_table = pd.DataFrame(pairs).sort_values('similarity', ascending=False)

    # union-find over the threshold graph, plus declared provenance
    parent = {tid: tid for tid in tids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, bb):
        ra, rb = find(a), find(bb)
        if ra != rb:
            parent[rb] = ra

    for row in pair_table.itertuples():
        if row.similarity >= threshold:
            union(row.tid_a, row.tid_b)

    declared: list[tuple[int, int]] = []
    prov = b.app['statement_provenance']
    if include_declared and not prov.empty:
        prov = prov[prov['conv_key'] == conv_key]
        for link in prov.itertuples():
            child, par = int(link.polis_statement_id), int(link.derived_from_tid)
            if child in parent and par in parent:
                declared.append((child, par))
                union(child, par)

    members: dict[int, list[int]] = {}
    for tid in tids:
        members.setdefault(find(tid), []).append(tid)

    groups = []
    for gid, (_, member_tids) in enumerate(
            sorted((r, sorted(m)) for r, m in members.items() if len(m) > 1)):
        member_set = set(member_tids)
        groups.append(StatementGroup(
            group_id=gid, tids=member_tids,
            texts={t: text_by_tid[t] for t in member_tids},
            declared_links=[(c, p) for c, p in declared
                            if c in member_set and p in member_set]))
    return groups, pair_table


def statement_families(b: Bundles, conv_key: str, phase: int = 2) -> list[dict]:
    """Families of statements linked by *declared* provenance.

    Different from the near-duplicate groups above, and worth having both. A
    near-duplicate group is what an embedding model judges to say the same thing. A
    family is what participants said they were doing: "this improves on that". The
    two disagree in both directions — someone rewrites a statement into something
    genuinely different, or two people independently write near-identical statements
    with no link between them.

    A family also has shape that a similarity group does not: a root, and generations
    descending from it. That makes a question available which flat grouping cannot
    ask — *did successive rewriting build support, or lose it?*
    """
    prov = b.app['statement_provenance']
    if prov.empty:
        return []
    prov = prov[prov['conv_key'] == conv_key]
    if prov.empty:
        return []

    parent_of = {int(r.polis_statement_id): int(r.derived_from_tid)
                 for r in prov.itertuples()}
    children: dict[int, list[int]] = {}
    for child, parent in parent_of.items():
        children.setdefault(parent, []).append(child)

    statements = b.phase('statements', conv_key, phase).set_index('tid')
    votes = b.phase('votes_latest', conv_key, phase)

    def root_of(tid: int) -> int:
        seen, cur = {tid}, tid
        while cur in parent_of:
            nxt = parent_of[cur]
            if nxt in seen:
                break
            seen.add(nxt)
            cur = nxt
        return cur

    members_by_root: dict[int, set[int]] = {}
    for tid in set(parent_of) | set(children):
        members_by_root.setdefault(root_of(tid), set()).add(tid)

    families = []
    for root, members in sorted(members_by_root.items(), key=lambda kv: -len(kv[1])):
        depth = {root: 0}
        queue = [root]
        while queue:
            cur = queue.pop()
            for child in children.get(cur, []):
                if child not in depth:
                    depth[child] = depth[cur] + 1
                    queue.append(child)
        for tid in members:                     # anything unreachable from the root
            depth.setdefault(tid, 0)

        rows = []
        for tid in sorted(members, key=lambda t: (depth[t], t)):
            block = votes[votes['tid'] == tid]
            decided = int(((block['vote'] == RAW_AGREE) |
                           (block['vote'] == RAW_DISAGREE)).sum())
            rows.append({
                'tid': tid,
                'generation': depth[tid],
                'improves_on': parent_of.get(tid),
                'n_voters': len(block),
                'n_decided': decided,
                'agree_pct': round(int((block['vote'] == RAW_AGREE).sum()) / decided * 100, 1)
                             if decided else np.nan,
                'text': statements['txt'].get(tid, ''),
            })
        families.append({
            'root': root,
            'size': len(members),
            'generations': max(depth.values()) + 1,
            'members': pd.DataFrame(rows),
        })
    return families


def statement_descendants(b: Bundles, conv_key: str, phase: int = 2) -> pd.DataFrame:
    """Which statements provoked rewriting, and how much.

    `n_children` counts direct rewrites; `n_descendants` counts the whole subtree
    beneath a statement, so a statement whose rewrite was itself rewritten gets
    credit for both. Statements nobody rewrote are included with zeros, because the
    absence of rewriting is as informative as its presence.

    A high descendant count marks a proposition people kept trying to get right —
    which is a different signal from disagreement, and often more useful to an
    organiser deciding what still needs work.
    """
    prov = b.app['statement_provenance']
    statements = b.phase('statements', conv_key, phase)
    votes = b.phase('votes_latest', conv_key, phase)

    parent_of: dict[int, int] = {}
    if not prov.empty:
        sub = prov[prov['conv_key'] == conv_key]
        parent_of = {int(r.polis_statement_id): int(r.derived_from_tid)
                     for r in sub.itertuples()}
    children: dict[int, list[int]] = {}
    for child, parent in parent_of.items():
        children.setdefault(parent, []).append(child)

    def descendants(tid: int) -> int:
        total, stack, seen = 0, list(children.get(tid, [])), set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            total += 1
            stack.extend(children.get(cur, []))
        return total

    rows = []
    for row in statements.itertuples():
        tid = int(row.tid)
        block = votes[votes['tid'] == tid]
        decided = int(((block['vote'] == RAW_AGREE) | (block['vote'] == RAW_DISAGREE)).sum())
        rows.append({
            'tid': tid,
            'n_children': len(children.get(tid, [])),
            'n_descendants': descendants(tid),
            'improves_on': parent_of.get(tid),
            'is_seed': bool(row.is_seed),
            'moderated_out': int(row.mod) == -1,
            'n_voters': len(block),
            'agree_pct': round(int((block['vote'] == RAW_AGREE).sum()) / decided * 100, 1)
                         if decided else np.nan,
            'text': row.txt,
        })
    out = pd.DataFrame(rows)
    return out.sort_values(['n_descendants', 'n_children', 'n_voters'],
                           ascending=False).reset_index(drop=True)


def family_generations(families: list[dict]) -> pd.DataFrame:
    """Does support rise or fall as a family is rewritten?

    Weighted by decided votes, so a much-voted statement counts for more than one
    that two people saw. Compares generations *across* families, which is only
    meaningful because the question is about the act of rewriting rather than about
    any particular proposition.
    """
    rows = []
    for family in families:
        for member in family['members'].itertuples():
            if member.n_decided:
                rows.append({'root': family['root'], 'generation': member.generation,
                             'agree_pct': member.agree_pct, 'n_decided': member.n_decided})
    table = pd.DataFrame(rows)
    if table.empty:
        return table

    def weighted(block):
        return pd.Series({
            'n_statements': len(block),
            'total_clear_opinions': int(block['n_decided'].sum()),
            'weighted_agree_pct': round(
                float(np.average(block['agree_pct'], weights=block['n_decided'])), 1),
            'median_agree_pct': round(float(block['agree_pct'].median()), 1),
        })

    return (table.groupby('generation').apply(weighted, include_groups=False)
                 .reset_index().astype({'n_statements': int, 'total_clear_opinions': int}))


def family_vs_similarity(families: list[dict], groups: list[StatementGroup]) -> dict:
    """How much do declared families and embedding groups actually agree?

    Reported because the two are routinely conflated. Where they diverge is
    informative in itself: a declared link the model does not see is a rewrite that
    changed the meaning; a similarity group with no declared link is duplication
    nobody noticed.
    """
    family_pairs, group_pairs = set(), set()
    for family in families:
        tids = sorted(family['members']['tid'])
        for i, a in enumerate(tids):
            for bb in tids[i + 1:]:
                family_pairs.add((a, bb))
    for group in groups:
        tids = sorted(group.tids)
        for i, a in enumerate(tids):
            for bb in tids[i + 1:]:
                group_pairs.add((a, bb))

    both = family_pairs & group_pairs
    return {
        'pairs_declared_family': len(family_pairs),
        'pairs_similarity_group': len(group_pairs),
        'pairs_in_both': len(both),
        'declared_but_not_similar': len(family_pairs - group_pairs),
        'similar_but_not_declared': len(group_pairs - family_pairs),
        'jaccard': round(len(both) / len(family_pairs | group_pairs), 3)
                   if (family_pairs | group_pairs) else float('nan'),
    }


def head_to_head(b: Bundles, conv_key: str, group: StatementGroup, phase: int = 2,
                 use_groups: bool = True) -> dict:
    """Compare the variants in one near-duplicate group, head to head.

    Two views, because they answer different questions:

      * **All voters** — what an organiser sees on the results page. Confounded:
        different variants were live for different lengths of time, so they were
        seen by different people.
      * **Common voters** — only people who voted on both variants. This is the
        one that can support a claim about wording, because the population is held
        fixed and each person acts as their own control.

    Discordant pairs (agreed with one wording, not the other) are tested with an
    exact binomial test — the paired form, since the same people voted both.
    """
    from scipy.stats import binomtest

    votes = b.phase('votes_latest', conv_key, phase)
    votes = votes[votes['tid'].isin(group.tids)]
    server = server_labels(b, conv_key, phase) if use_groups else {'available': False}

    per_variant = []
    for tid in group.tids:
        v = votes[votes['tid'] == tid]
        row = {
            'tid': tid, 'text': group.texts[tid], 'n_voters': len(v),
            'agree': int((v['vote'] == RAW_AGREE).sum()),
            'disagree': int((v['vote'] == RAW_DISAGREE).sum()),
            'pass': int((v['vote'] == 0).sum()),
        }
        decided = row['agree'] + row['disagree']
        row['agree_pct'] = round(row['agree'] / decided * 100, 1) if decided else np.nan
        if server.get('available'):
            key_by_pid = dict(zip(b.phase('participants', conv_key, phase)['pid'],
                                  b.phase('participants', conv_key, phase)['person_key']))
            group_by_key = {key_by_pid[pid]: lab for pid, lab in server['labels'].items()
                            if pid in key_by_pid}
            v = v.assign(opinion_group=v['person_key'].map(group_by_key))
            for gid in sorted({g for g in group_by_key.values()}):
                sub = v[v['opinion_group'] == gid]
                dec = int((sub['vote'] == RAW_AGREE).sum() + (sub['vote'] == RAW_DISAGREE).sum())
                row[f'agree_pct_group{gid}'] = (
                    round(int((sub['vote'] == RAW_AGREE).sum()) / dec * 100, 1)
                    if dec else np.nan)
                row[f'n_group{gid}'] = len(sub)
        per_variant.append(row)

    comparisons = []
    for i, tid_a in enumerate(group.tids):
        for tid_b in group.tids[i + 1:]:
            va = votes[votes['tid'] == tid_a][['person_key', 'vote']]
            vb = votes[votes['tid'] == tid_b][['person_key', 'vote']]
            both = va.merge(vb, on='person_key', suffixes=('_a', '_b'))
            decided = both[both['vote_a'].isin([RAW_AGREE, RAW_DISAGREE]) &
                           both['vote_b'].isin([RAW_AGREE, RAW_DISAGREE])]
            a_only = int(((decided['vote_a'] == RAW_AGREE) &
                          (decided['vote_b'] == RAW_DISAGREE)).sum())
            b_only = int(((decided['vote_a'] == RAW_DISAGREE) &
                          (decided['vote_b'] == RAW_AGREE)).sum())
            discordant = a_only + b_only
            p_value = (binomtest(a_only, discordant, 0.5).pvalue
                       if discordant else float('nan'))
            comparisons.append({
                'tid_a': tid_a, 'tid_b': tid_b,
                'n_common_voters': len(both), 'n_common_decided': len(decided),
                'agreed_with_a_only': a_only, 'agreed_with_b_only': b_only,
                'n_discordant': discordant,
                'shift_pct_points': (
                    round((b_only - a_only) / len(decided) * 100, 1) if len(decided) else np.nan),
                'p_value': round(p_value, 4) if p_value == p_value else np.nan,
            })

    return {'group_id': group.group_id,
            'variants': pd.DataFrame(per_variant),
            'comparisons': pd.DataFrame(comparisons),
            'declared_links': group.declared_links,
            'n_declared': len(group.declared_links)}


def wording_participation(b: Bundles, conv_key: str, groups: list[StatementGroup],
                          phase: int = 2) -> dict:
    """How many actual people are behind the wording comparisons.

    Exists because the pair counts are treacherous in prose. Summing discordant
    pairs across comparisons counts one person once per pair they appear in, and a
    family of 13 variants generates 78 pairs, so a handful of people can produce
    several hundred "disagreements". These are counts of people.
    """
    votes = b.phase('votes_latest', conv_key, phase)
    decided = votes[votes['vote'].isin([RAW_AGREE, RAW_DISAGREE])]

    voted_multiple, split, instances = set(), set(), 0
    for group in groups:
        block = decided[decided['tid'].isin(group.tids)]
        for person, rows in block.groupby('person_key'):
            if len(rows) > 1:
                voted_multiple.add(person)
                if rows['vote'].nunique() > 1:
                    split.add(person)
                    instances += 1

    return {
        'n_participants': int(votes['person_key'].nunique()),
        'n_voted_on_multiple_variants': len(voted_multiple),
        'n_voted_differently': len(split),
        'n_person_family_instances': instances,
    }


def wording_effect(head_to_heads: list[dict]) -> dict:
    """Per-pair tests of whether two wordings of one proposition draw different support.

    Three things this deliberately does NOT do, each of which would manufacture
    significance out of nothing:

    **It does not pool discordant counts into one binomial test.** Variants are
    compared in tid order, so "side A" is always the earlier-submitted wording. A
    pooled test of A-versus-B therefore measures whether *earlier* statements draw
    more agreement than later ones — an ordering effect — and answers it in the
    voice of a wording effect. That result is reported below under its own name,
    separately, because it is a real question and a different one.

    **It does not treat the pairs as independent.** A group of k variants yields
    k(k-1)/2 pairs over the same statements and the same people; one group of 13
    contributes 78 of them. Each pair is tested on its own and the p-values are
    Benjamini-Hochberg corrected across the family.

    **It does not report a median shift over pairs with almost no data.** A pair
    where two people happened to disagree can show a 100-point "shift". Pairs below
    `min_decided` are reported but excluded from the headline.
    """
    from scipy.stats import binomtest

    rows = []
    for h2h in head_to_heads:
        for comparison in h2h['comparisons'].itertuples():
            rows.append({'group_id': h2h['group_id'], 'tid_earlier': comparison.tid_a,
                         'tid_later': comparison.tid_b,
                         'n_common_decided': comparison.n_common_decided,
                         'n_discordant': comparison.n_discordant,
                         'agreed_earlier_only': comparison.agreed_with_a_only,
                         'agreed_later_only': comparison.agreed_with_b_only,
                         'shift_pct_points': comparison.shift_pct_points,
                         'p_value': comparison.p_value})
    table = pd.DataFrame(rows)
    if table.empty or table['n_discordant'].sum() == 0:
        return {'available': False,
                'reason': 'no participant voted on two variants of the same statement',
                'table': table}

    min_decided = MIN_DECIDED_FOR_HEAD_TO_HEAD
    tested = table[(table['n_discordant'] > 0) &
                   (table['n_common_decided'] >= min_decided)].copy()

    if tested.empty:
        return {'available': True, 'n_pairs_tested': 0, 'n_significant': 0,
                'table': table, 'min_decided': min_decided,
                'reading': (f'No pair had at least {min_decided} people who voted '
                            f'decisively on both wordings, so no comparison here can '
                            f'support a claim about wording.')}

    # Benjamini-Hochberg across the family of pair tests.
    tested = tested.sort_values('p_value')
    m = len(tested)
    tested['q_value'] = (tested['p_value'] * m /
                         np.arange(1, m + 1)).cummin().clip(upper=1).round(4)
    significant = tested[tested['q_value'] < 0.05]

    # The ordering question, asked in its own right rather than smuggled in.
    total_earlier = int(tested['agreed_earlier_only'].sum())
    total_discordant = int(tested['n_discordant'].sum())
    order_test = binomtest(total_earlier, total_discordant, 0.5)

    shifts = tested['shift_pct_points'].dropna()
    return {
        'available': True,
        'n_pairs_tested': m,
        'n_pairs_dropped_thin': int(len(table) - m),
        'min_decided': min_decided,
        'n_significant': len(significant),
        'significant': significant,
        'median_abs_shift_pct_points': round(float(shifts.abs().median()), 1),
        'max_abs_shift_pct_points': round(float(shifts.abs().max()), 1),
        'order_effect_p': round(float(order_test.pvalue), 5),
        'order_effect_share_earlier': round(total_earlier / total_discordant, 3),
        'table': table, 'tested': tested,
        'reading': (
            f'{len(significant)} of {m} comparisons survive correction for multiple '
            f'testing. These pairs are not independent — variants of one proposition '
            f'are compared against each other repeatedly and by the same people — so '
            f'read them as pointers to specific wording choices, not as a count of '
            f'discoveries.'),
    }


def family_representatives(b: Bundles, conv_key: str, families: list[dict],
                           min_decided: int = 5) -> pd.DataFrame:
    """For each family of rewrites, which wording best represents it.

    A family is one proposition written several ways. Carrying all of them into a
    next round asks people to vote repeatedly on the same idea; carrying none loses
    the idea. So each family needs one representative.

    Chosen by support among people who took a side, with a floor on how many did:
    the highest-agreement variant in a family is often one that three people saw.
    Where no variant clears the floor the family is reported as undecided rather
    than given a representative on thin evidence — an explicit "needs a decision"
    is more useful to an organiser than a confident wrong pick.
    """
    rows = []
    for family in families:
        members = family['members']
        eligible = members[members['n_decided'] >= min_decided]
        if eligible.empty:
            best = members.sort_values('n_decided', ascending=False).iloc[0]
            rows.append({
                'family': family['root'], 'n_variants': family['size'],
                'representative_tid': None,
                'status': f'undecided — no variant reached {min_decided} decisive votes',
                'best_seen_tid': int(best['tid']), 'n_decided': int(best['n_decided']),
                'agree_pct': best['agree_pct'], 'is_rewrite': best['generation'] > 0,
                'text': best['text'],
            })
            continue
        best = eligible.sort_values(['agree_pct', 'n_decided'], ascending=False).iloc[0]
        spread = eligible['agree_pct'].max() - eligible['agree_pct'].min()
        rows.append({
            'family': family['root'], 'n_variants': family['size'],
            'representative_tid': int(best['tid']),
            'status': ('clear' if spread >= 15 else
                       'variants are close — any of them would do'),
            'best_seen_tid': int(best['tid']), 'n_decided': int(best['n_decided']),
            'agree_pct': best['agree_pct'], 'is_rewrite': bool(best['generation'] > 0),
            'text': best['text'],
        })
    out = pd.DataFrame(rows)
    return out.sort_values(['agree_pct', 'n_decided'], ascending=False).reset_index(drop=True)


NUMBER_WORDS = {
    'een': '1', 'één': '1', 'twee': '2', 'drie': '3', 'vier': '4', 'vijf': '5',
    'zes': '6', 'zeven': '7', 'acht': '8', 'negen': '9', 'tien': '10', 'elf': '11',
    'twaalf': '12', 'dertien': '13', 'veertien': '14', 'vijftien': '15',
    'twintig': '20', 'dertig': '30', 'vijftig': '50', 'honderd': '100',
    'tweehonderd': '200', 'driehonderd': '300', 'vijfhonderd': '500',
    'duizend': '1000', 'tweeduizend': '2000',
}


def normalise_text(text: str) -> str:
    """Reduce a statement to what it *says*, ignoring how it is written.

    Lower-cases, strips punctuation and repeated whitespace, and writes number words
    as digits — so "ten laatste 2 weken" and "ten laatste twee weken" come out the
    same. It deliberately does NOT map different numbers onto each other: "duizend"
    becomes 1000 and "vijfhonderd" becomes 500, so a real difference in threshold
    survives normalisation and the two statements stay distinct.
    """
    import re
    tokens = re.findall(r"[\w']+", (text or '').lower())
    return ' '.join(NUMBER_WORDS.get(t, t) for t in tokens)


def unvoted_statements(b: Bundles, conv_key: str, phase: int = 2) -> pd.DataFrame:
    """Statements nobody voted on. No data exists about them, so they are set aside
    before anything else — they cannot be compared, merged or clustered, and leaving
    them in the deduplication lists only buries the pairs that can be judged."""
    statements = b.phase('statements', conv_key, phase)
    votes = b.phase('votes_latest', conv_key, phase)
    voted = set(votes['tid'])
    out = statements[~statements['tid'].isin(voted)][['tid', 'txt', 'mod', 'is_seed']]
    return out.reset_index(drop=True)


def redundant_pairs(b: Bundles, conv_key: str, pairs: pd.DataFrame, *,
                    text_threshold: float = SIMILARITY_THRESHOLD,
                    concordance: float = 0.9, min_common: int = 5,
                    phase: int = 2) -> pd.DataFrame:
    """Which similar-looking statements are genuinely the *same* statement.

    Text similarity alone is not enough and gets this badly wrong: "at least a
    thousand edits" and "at least five hundred edits" score 0.976 together while
    proposing different things. Merging that pair would delete a real disagreement.

    So similarity only nominates a pair; the votes decide. Among people who voted
    decisively on both, a pair is redundant when they voted the *same* way almost
    every time — then the second column carries no information the first does not,
    and counting it twice simply doubles that proposition's weight in the maths.
    Where too few people voted on both to tell, the pair is left alone: keeping a
    real distinction is the safer error.
    """
    votes = b.phase('votes_latest', conv_key, phase)
    decisive = votes[votes['vote'].isin([RAW_AGREE, RAW_DISAGREE])]
    unvoted = set(unvoted_statements(b, conv_key, phase)['tid'])

    rows = []
    for pair in pairs[pairs['similarity'] >= text_threshold].itertuples():
        a, bb = int(pair.tid_a), int(pair.tid_b)
        va = decisive[decisive['tid'] == a][['person_key', 'vote']]
        vb = decisive[decisive['tid'] == bb][['person_key', 'vote']]
        both = va.merge(vb, on='person_key', suffixes=('_a', '_b'))
        n = len(both)
        agree = float((both['vote_a'] == both['vote_b']).mean()) if n else float('nan')

        # Wording differences that carry no meaning are settled without votes: if the
        # two say the same thing once spelling and number-format are normalised, they
        # are the same statement whatever anybody did or did not vote. Where the
        # meaning might genuinely differ and the votes cannot settle it, they stay
        # apart — keeping a real distinction is the safer error.
        same_after_normalising = normalise_text(pair.text_a) == normalise_text(pair.text_b)

        # Normalisation is checked first: two statements that differ only in spelling
        # are the same statement, and that is true whether or not anyone voted.
        if same_after_normalising:
            verdict = 'redundant — identical apart from spelling or number format'
        elif a in unvoted or bb in unvoted:
            verdict = 'set aside — nobody voted on one of them'
        elif n < min_common:
            verdict = 'undecided — too few voted on both'
        elif agree >= concordance:
            verdict = 'redundant — same statement, reworded'
        else:
            verdict = 'distinct — people voted differently on them' 
        rows.append({'tid_a': a, 'tid_b': bb, 'similarity': round(pair.similarity, 3),
                     'n_common': n,
                     'vote_concordance': round(agree, 3) if agree == agree else np.nan,
                     'verdict': verdict, 'text_a': pair.text_a, 'text_b': pair.text_b})
    return pd.DataFrame(rows).sort_values('similarity', ascending=False).reset_index(drop=True)


def deduplication_map(redundant: pd.DataFrame, tids: list[int]) -> dict[int, int]:
    """{tid: representative tid}, merging only pairs judged redundant."""
    parent = {int(t): int(t) for t in tids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for row in redundant[redundant['verdict'].str.startswith('redundant')].itertuples():
        a, bb = int(row.tid_a), int(row.tid_b)
        if a in parent and bb in parent:
            ra, rb = find(a), find(bb)
            if ra != rb:
                parent[rb] = ra
    return {t: find(t) for t in parent}


#: Communities of one person are outliers, not groups. OSLOM calls these "homeless"
#: nodes — vertices not significantly linked to any cluster — and Infomap refuses to
#: emit singletons at all. Reporting "a group of 1" invites a reader to treat one
#: person as a faction.
MIN_COMMUNITY_SIZE = 2


def split_outliers(labels: dict) -> tuple[dict, list]:
    """Separate real communities from single-person outliers."""
    sizes = collections.Counter(labels.values())
    outliers = [p for p, g in labels.items() if sizes[g] < MIN_COMMUNITY_SIZE]
    kept = {p: g for p, g in labels.items() if sizes[g] >= MIN_COMMUNITY_SIZE}
    return kept, outliers


def multilayer_leiden(layer_matrices: list, pids: list, *, resolution: float = 1.0,
                      seed: int = 20260606, min_overlap: int = 3):
    """Leiden over several layers at once, the way the multilayer literature does it.

    One graph per topic, all on the same set of people, optimised jointly rather than
    separately-then-combined. This is the direct multilayer method (Mucha et al.);
    the alternative — clustering each layer and merging the results through a
    co-classification matrix — is Lancichinetti–Fortunato consensus clustering, which
    is designed for combining repeated runs of one algorithm for robustness, not for
    data that is genuinely layered.

    The distinction matters here: consensus clustering asks "where do these partitions
    agree?", which presumes one underlying partition. Multilayer modularity allows the
    layers to disagree and scores the result accordingly.
    """
    import igraph as ig
    import leidenalg

    graphs = []
    for values in layer_matrices:
        holder = Matrix(conv_key='layer', phase=2, values=values, pids=pids,
                        tids=list(range(values.shape[1])), person_keys=[])
        graph_pids, weights, _ = agreement_graph(holder, min_overlap=min_overlap)
        index = {p: i for i, p in enumerate(graph_pids)}
        edges, edge_weights = [], []
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                a, bb = index.get(pids[i]), index.get(pids[j])
                if a is None or bb is None:
                    continue
                if weights[a, bb] > 0:
                    edges.append((i, j))
                    edge_weights.append(float(weights[a, bb]))
        graph = ig.Graph(n=len(pids), edges=edges)
        graph.es['weight'] = edge_weights
        graphs.append(graph)

    if not graphs:
        return {}, float('nan')
    membership, _improvement = leidenalg.find_partition_multiplex(
        graphs, leidenalg.RBConfigurationVertexPartition,
        resolution_parameter=resolution, weights='weight', seed=seed)

    # NOT the second return value: that is the optimiser's improvement, which is
    # unbounded and not comparable with anything. Score the joint partition by the
    # modularity it achieves in each layer, and report the mean — directly comparable
    # with the single-layer numbers above it.
    per_layer = []
    for graph in graphs:
        if graph.ecount():
            per_layer.append(graph.modularity(membership, weights='weight'))
    quality = float(np.mean(per_layer)) if per_layer else float('nan')
    return {pids[i]: int(c) for i, c in enumerate(membership)}, quality


def method_ladder(b: Bundles, conv_key: str, *, phase: int = 2, n_topics: int = 5) -> dict:
    """Both grouping methods at three levels of refinement, side by side.

    The levels are cumulative, and every one of them starts from a matrix with
    statements nobody voted on already removed — those carry no information at any
    level, so including them would only be a fourth way of being wrong.

      naive        the method as the tool applies it
      deduplicated near-identical statements merged, so one proposition written
                   several ways stops counting several times
      layered      statements split into topics, each topic grouped on its own, and
                   the results combined by how often two people land together across
                   topics. This is the only level that can represent people who
                   agree on one subject and disagree on another; a single partition
                   cannot.

    Reported per cell: how many groups, their sizes, the method's own quality score,
    and how far the result has moved from the naive version. Comparing a method
    against itself down the column shows how much of the answer was an artefact of
    the preprocessing rather than the opinions.
    """
    import warnings as _w

    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import adjusted_rand_score

    import pipeline as P
    from analysis.polis_replica import run_replica

    matrix = P.build_matrix(b, conv_key, phase)          # unvoted already dropped
    counts = P.real_vote_counts(b, conv_key, phase)
    eligible = [p for p in matrix.pids
                if counts.get(p, 0) >= P.POLIS_VOTE_THRESHOLD]
    rows_idx = [i for i, p in enumerate(matrix.pids) if p in set(eligible)]
    base = matrix.values[rows_idx, :]
    tids = list(matrix.tids)

    groups, pairs = similar_statement_groups(b, conv_key)
    redundant = redundant_pairs(b, conv_key, pairs)
    mapping = deduplication_map(redundant, tids)
    column = {t: j for j, t in enumerate(tids)}
    merged: dict[int, list[int]] = {}
    for tid in tids:
        merged.setdefault(mapping[tid], []).append(column[tid])
    dedup_keys = sorted(merged)
    dedup = np.full((len(eligible), len(dedup_keys)), np.nan)
    for j, key in enumerate(dedup_keys):
        with _w.catch_warnings():
            _w.simplefilter('ignore')
            dedup[:, j] = np.nanmean(base[:, merged[key]], axis=1)

    statements = b.phase('statements', conv_key, phase).set_index('tid')
    texts = [statements['txt'].get(t, '') for t in dedup_keys]
    vectors = embed_statements(texts)
    topics = AgglomerativeClustering(n_clusters=min(n_topics, len(texts) - 1),
                                     metric='cosine', linkage='average'
                                     ).fit_predict(vectors)

    def kmeans_partition(values):
        result = run_replica(values)
        labels = {eligible[i]: int(x) for i, x in enumerate(result['labels']) if x != -1}
        quality = result.get('silhouettes', {}).get(result['K'], float('nan'))
        return labels, result['K'], quality

    def leiden_partition(values):
        holder = Matrix(conv_key=conv_key, phase=phase, values=values, pids=eligible,
                        tids=list(range(values.shape[1])), person_keys=[])
        pids, weights, _ = agreement_graph(holder, min_overlap=3)
        if (weights > 0).sum() == 0:
            return {}, 0, float('nan')
        best = (-9.0, None)
        for resolution in (0.8, 1.0, 1.2):
            labels, modularity = leiden_communities(pids, weights, resolution=resolution)
            if modularity > best[0]:
                best = (modularity, labels)
        labels = best[1] or {}
        return labels, len(set(labels.values())), best[0]

    def layered(values, partition_fn):
        """Group inside each topic, then combine by how often two people co-occur."""
        n = len(eligible)
        together = np.zeros((n, n))
        used = 0
        for topic in sorted(set(topics)):
            cols = [j for j, t in enumerate(topics) if t == topic]
            if len(cols) < 4:
                continue
            labels, k, _ = partition_fn(values[:, cols])
            if k < 2:
                continue
            member = np.array([labels.get(p, -1) for p in eligible])
            same = (member[:, None] == member[None, :]) & (member[:, None] >= 0)
            together += same.astype(float)
            used += 1
        if used < 2:
            return {}, 0, float('nan'), used
        together /= used
        distance = 1 - together
        np.fill_diagonal(distance, 0.0)
        best = (-9.0, None, 0)
        for k in (2, 3, 4):
            labels = AgglomerativeClustering(n_clusters=k, metric='precomputed',
                                             linkage='average').fit_predict(distance)
            # How cleanly the layers agree on this grouping: mean co-occurrence
            # inside groups minus mean co-occurrence between them.
            inside, between = [], []
            for i in range(n):
                for j in range(i + 1, n):
                    (inside if labels[i] == labels[j] else between).append(together[i, j])
            score = (np.mean(inside) - np.mean(between)) if inside and between else np.nan
            if score == score and score > best[0]:
                best = (score, labels, k)
        if best[1] is None:
            return {}, 0, float('nan'), used
        return ({eligible[i]: int(x) for i, x in enumerate(best[1])},
                best[2], best[0], used)

    rows, partitions = [], {}
    for method, fn, quality_name in (('k-means on the opinion map', kmeans_partition, 'silhouette'),
                                     ('Leiden communities', leiden_partition, 'modularity')):
        naive_labels = None
        for level, values in (('naive', base), ('deduplicated', dedup)):
            labels, k, quality = fn(values)
            if naive_labels is None:
                naive_labels, ari = labels, 1.0
            else:
                shared = [p for p in labels if p in naive_labels]
                ari = (adjusted_rand_score([naive_labels[p] for p in shared],
                                           [labels[p] for p in shared])
                       if len(shared) > 1 else float('nan'))
            labels, outliers = split_outliers(labels)
            k = len(set(labels.values()))
            partitions[(method, level)] = labels
            rows.append({'method': method, 'level': level,
                         'statements': values.shape[1], 'groups': k,
                         'group sizes (people)': ' / '.join(str(v) for v in sorted(
                             pd.Series(list(labels.values())).value_counts().values,
                             reverse=True)) if labels else '—',
                         'unplaced (people)': len(outliers),
                         'quality': round(quality, 3) if quality == quality else np.nan,
                         'quality is': quality_name,
                         'agreement with naive (ARI)': round(ari, 3) if ari == ari else np.nan})
        if method.startswith('Leiden'):
            layer_values, used = [], 0
            for topic in sorted(set(topics)):
                cols = [j for j, t in enumerate(topics) if t == topic]
                if len(cols) >= 4:
                    layer_values.append(dedup[:, cols])
                    used += 1
            labels, score = (multilayer_leiden(layer_values, eligible)
                             if used >= 2 else ({}, float('nan')))
            labels, outliers = split_outliers(labels)
            k = len(set(labels.values()))
        else:
            labels, k, score, used = layered(dedup, fn)
            labels, outliers = split_outliers(labels)
            k = len(set(labels.values()))
        shared = [p for p in labels if p in naive_labels]
        ari = (adjusted_rand_score([naive_labels[p] for p in shared],
                                   [labels[p] for p in shared])
               if len(shared) > 1 else float('nan'))
        partitions[(method, 'layered')] = labels
        rows.append({'method': method, 'level': f'layered ({used} topics)',
                     'statements': dedup.shape[1], 'groups': k,
                     'group sizes (people)': ' / '.join(str(v) for v in sorted(
                         pd.Series(list(labels.values())).value_counts().values,
                         reverse=True)) if labels else '—',
                     'unplaced (people)': len(outliers),
                     'quality': round(score, 3) if score == score else np.nan,
                     'quality is': ('multilayer modularity'
                                    if method.startswith('Leiden') else 'layer agreement'),
                     'agreement with naive (ARI)': round(ari, 3) if ari == ari else np.nan})

    return {'table': pd.DataFrame(rows), 'partitions': partitions,
            'eligible': eligible, 'n_topics': len(set(topics))}


def shuffle_within_statements(values: np.ndarray, rng) -> np.ndarray:
    """Permute each statement's votes across people.

    Preserves how many people voted on each statement and how that statement's
    agree/disagree balance looks, while destroying any relationship *between*
    statements. So a shuffled dataset is what this conversation would look like if
    people's opinions on one statement told you nothing about their opinions on
    another — i.e. no groups, same overall shape.
    """
    out = values.copy()
    for j in range(out.shape[1]):
        column = out[:, j]
        voted = ~np.isnan(column)
        if voted.sum() > 1:
            picks = column[voted].copy()
            rng.shuffle(picks)
            column[voted] = picks
    return out


def significance_of_grouping(values: np.ndarray, pids: list, score_fn,
                             *, n_permutations: int = 100, seed: int = 20260606) -> dict:
    """Could this grouping have arisen from votes with no group structure at all?

    A clustering method always returns a score, and on 22 people that score is often
    respectable by luck alone. The only way to know whether it means anything is to
    run the identical procedure on data known to have no structure, and see how often
    chance does as well.

    p is the fraction of shuffled datasets scoring at least as high as the real one
    (with the standard +1 correction, so p is never reported as 0). A large p means
    the grouping is indistinguishable from one computed on noise — which is not the
    same as proving no groups exist, but does mean this data cannot show them.
    """
    rng = np.random.default_rng(seed)
    observed = score_fn(values, pids)
    if observed != observed:
        return {'observed': float('nan'), 'p_value': float('nan'), 'null_scores': []}

    null = []
    for _ in range(n_permutations):
        score = score_fn(shuffle_within_statements(values, rng), pids)
        if score == score:
            null.append(score)
    if not null:
        return {'observed': observed, 'p_value': float('nan'), 'null_scores': []}

    at_least_as_good = sum(1 for s in null if s >= observed)
    return {
        'observed': round(float(observed), 4),
        'null_median': round(float(np.median(null)), 4),
        'null_95th': round(float(np.percentile(null, 95)), 4),
        'n_permutations': len(null),
        'p_value': round((at_least_as_good + 1) / (len(null) + 1), 4),
        'null_scores': null,
    }
