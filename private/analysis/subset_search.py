#!/usr/bin/env python3
"""Is there ANY set of statements on which real communities appear?

Searching for a subset that produces good modularity will always succeed given
enough attempts — with 22 people, some subset of votes will look clustered by luck
alone. The search on its own therefore proves nothing.

So the same search is run twice: once on the real votes, and once on data where each
statement's votes have been shuffled across people. Shuffling destroys any relationship
*between* statements while preserving each statement's own agree/disagree balance and
each person's number of votes — so the shuffled data is what "no communities, same
overall shape" looks like. If the best subset of real votes scores no better than the
best subset of shuffled votes, there is nothing to find.
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, '.')
warnings.filterwarnings('ignore')

import methods as M  # noqa: E402
import pipeline as P  # noqa: E402

RESOLUTIONS = (0.8, 1.0, 1.2)
SIZES = (8, 16, 24, 32, 48)
SAMPLES = 150


def best_modularity(values, pids, tids_idx, rng):
    sub = values[:, tids_idx]
    matrix = P.Matrix(conv_key='x', phase=2, values=sub, pids=pids,
                      tids=list(range(sub.shape[1])), person_keys=[])
    graph_pids, weights, _ = M.agreement_graph(matrix, min_overlap=3)
    if (weights > 0).sum() == 0:
        return float('nan')
    best = -1.0
    for resolution in RESOLUTIONS:
        labels, modularity = M.leiden_communities(graph_pids, weights,
                                                  resolution=resolution,
                                                  seed=int(rng.integers(1, 10_000)))
        if len(set(labels.values())) > 1:
            best = max(best, modularity)
    return best if best > -1 else float('nan')


def shuffle_within_statements(values, rng):
    """Permute each column independently, keeping its votes but breaking any
    relationship between statements."""
    out = values.copy()
    for j in range(out.shape[1]):
        column = out[:, j]
        voted = ~np.isnan(column)
        if voted.sum() > 1:
            picks = column[voted].copy()
            rng.shuffle(picks)
            column[voted] = picks
    return out


def main() -> int:
    rng = np.random.default_rng(20260606)
    b = P.load_bundles('2026-nlwiki-arbcom_bundle')
    conv = b.conversations[0]
    matrix = P.build_matrix(b, conv, 2)
    counts = P.real_vote_counts(b, conv, 2)
    eligible = [p for p in matrix.pids if counts.get(p, 0) >= P.POLIS_VOTE_THRESHOLD]
    idx = [i for i, p in enumerate(matrix.pids) if p in set(eligible)]
    real = matrix.values[idx, :]
    print(f'{real.shape[0]} people x {real.shape[1]} statements\n')

    shuffled = shuffle_within_statements(real, rng)
    rows = []
    for size in SIZES:
        if size > real.shape[1]:
            continue
        for label, values in (('real votes', real), ('shuffled votes', shuffled)):
            scores = []
            for _ in range(SAMPLES):
                pick = rng.choice(values.shape[1], size=size, replace=False)
                score = best_modularity(values, eligible, pick, rng)
                if score == score:
                    scores.append(score)
            if scores:
                rows.append({'statements in subset': size, 'data': label,
                             'subsets tried': len(scores),
                             'best modularity found': round(max(scores), 4),
                             '95th percentile': round(float(np.percentile(scores, 95)), 4),
                             'median': round(float(np.median(scores)), 4),
                             'any above zero': int(sum(1 for s in scores if s > 0))})
    table = pd.DataFrame(rows).sort_values(['statements in subset', 'data'])
    print(table.to_string(index=False))

    real_best = table[table['data'] == 'real votes']['best modularity found'].max()
    null_best = table[table['data'] == 'shuffled votes']['best modularity found'].max()
    print(f'\nbest over every real subset tried    : {real_best:+.4f}')
    print(f'best over every shuffled subset tried: {null_best:+.4f}')
    print('\n' + ('Real votes do no better than shuffled ones — no subset of statements '
                  'reveals communities that are not there.'
                  if real_best <= null_best else
                  'Some subset of real votes beats the shuffled baseline — worth '
                  'inspecting which statements it uses.'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
