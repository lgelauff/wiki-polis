#!/usr/bin/env python3
"""Build both reports from a bundle. One command, so the numbers can be re-derived.

    ./.venv/bin/python build_reports.py                       # default bundle
    ./.venv/bin/python build_reports.py <bundle_dir> [--copy-to ~/Downloads]

Every statistic it prints is documented in CALCULATIONS.md, with the function that
computes it. Nothing here decides anything — it wires the analysis modules to the
report writer and shows the headline numbers on the way past, so a wrong figure is
visible in the terminal rather than only buried in 350 KB of HTML.
"""
from __future__ import annotations

import argparse
import collections
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings('ignore')

import methods as M  # noqa: E402
import pipeline as P  # noqa: E402
import report as R  # noqa: E402

DEFAULT_BUNDLE = '2026-nlwiki-arbcom_bundle'
PERMUTATIONS = 100


def deduplicated_matrix(base, matrix, redundant, eligible):
    """Merge redundant statements into one column each, averaging a person's votes."""
    mapping = M.deduplication_map(redundant, matrix.tids)
    column = {t: j for j, t in enumerate(matrix.tids)}
    merged: dict[int, list[int]] = {}
    for tid in matrix.tids:
        merged.setdefault(mapping[tid], []).append(column[tid])
    keys = sorted(merged)
    out = np.full((len(eligible), len(keys)), np.nan)
    for j, key in enumerate(keys):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            out[:, j] = np.nanmean(base[:, merged[key]], axis=1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('bundle', nargs='?', default=DEFAULT_BUNDLE)
    ap.add_argument('--copy-to', help='also copy both reports here')
    ap.add_argument('--permutations', type=int, default=PERMUTATIONS)
    args = ap.parse_args()

    from analysis.polis_replica import run_replica
    from sklearn.metrics import adjusted_rand_score

    b = P.load_bundles(args.bundle)
    conv = b.conversations[0]
    print(f'{conv}: {len(b.phase("participants", conv, 2))} real participants, '
          f'{len(b.phase("statements", conv, 2))} statements, '
          f'{len(b.phase("votes_latest", conv, 2)):,} votes '
          f'({len(b.machine.get((conv, 2), {}))} machine accounts excluded)')

    checks = P.integrity_checks(b)
    failed = [c for c in checks if not c.passed]
    print(f'data checks: {len(checks) - len(failed)}/{len(checks)} passed')
    for check in failed:
        print(f'  {check}')

    matrix = P.build_matrix(b, conv, 2)
    counts = P.real_vote_counts(b, conv, 2)
    eligible = [p for p in matrix.pids if counts.get(p, 0) >= P.POLIS_VOTE_THRESHOLD]
    rows_idx = [i for i, p in enumerate(matrix.pids) if p in set(eligible)]
    base = matrix.values[rows_idx, :]

    groups, pairs = M.similar_statement_groups(b, conv)
    redundant = M.redundant_pairs(b, conv, pairs)
    dedup = deduplicated_matrix(base, matrix, redundant, eligible)
    print(f'statements: {matrix.values.shape[1]} voted-on, {dedup.shape[1]} after '
          f'merging {int(redundant["verdict"].str.startswith("redundant").sum())} '
          f'redundant pairs')

    # --- the two methods, scored the way each is meant to be scored ---------
    def kmeans_score(values, _pids):
        result = run_replica(values)
        return result['silhouettes'].get(result['K'], float('nan'))

    def leiden_score(values, pids):
        holder = P.Matrix(conv_key=conv, phase=2, values=values, pids=pids,
                          tids=list(range(values.shape[1])), person_keys=[])
        graph_pids, weights, _ = M.agreement_graph(holder, min_overlap=3)
        if (weights > 0).sum() == 0:
            return float('nan')
        return max(M.leiden_communities(graph_pids, weights, resolution=r)[1]
                   for r in (0.8, 1.0, 1.2))

    significance = []
    for level, values in (('naive', base), ('deduplicated', dedup)):
        for name, fn in (('k-means (silhouette)', kmeans_score),
                         ('Leiden (modularity)', leiden_score)):
            result = M.significance_of_grouping(values, eligible, fn,
                                                n_permutations=args.permutations)
            significance.append({
                'level': level, 'method': name, 'real data': result['observed'],
                'scrambled: typical': result['null_median'],
                'scrambled: best 5%': result['null_95th'],
                'p (permutation test)': result['p_value']})
    significance = pd.DataFrame(significance)
    print('\nsignificance:')
    print(significance.to_string(index=False))

    ladder = M.method_ladder(b, conv)['table']
    print('\nrefinement ladder:')
    print(ladder.to_string(index=False))

    # --- head to head -------------------------------------------------------
    replica = run_replica(base)
    polis = {eligible[i]: int(x) for i, x in enumerate(replica['labels']) if x != -1}
    graph_pids, weights, _ = M.agreement_graph(matrix, restrict_pids=eligible)
    leiden, leiden_modularity = M.leiden_communities(graph_pids, weights, resolution=1.0)
    shared = [p for p in graph_pids if p in polis]
    crosstab = pd.crosstab(
        pd.Series([polis[p] + 1 for p in shared], name='k-means group'),
        pd.Series([leiden[p] + 1 for p in shared], name='Leiden community'))
    comparison = {
        'k_polis': replica['K'],
        'sizes_polis': ' / '.join(str(v) for _, v in
                                  sorted(collections.Counter(polis.values()).items())),
        'k_leiden': len(set(leiden.values())),
        'sizes_leiden': ' / '.join(str(v) for _, v in
                                   sorted(collections.Counter(leiden.values()).items())),
        'ari': adjusted_rand_score([polis[p] for p in shared],
                                   [leiden[p] for p in shared]),
        'crosstab_html': crosstab.to_html(border=0, classes='data'),
        # Each method's own score for the partition in the row above it. Leiden's is
        # the point of the section: at a fixed resolution it returns two communities
        # like k-means does, but scores them below zero — worse than no split at all.
        # Without the number beside it the row reads as a second method agreeing that
        # there are two groups.
        'silhouette_polis': replica['silhouettes'].get(replica['K'], float('nan')),
        'modularity_leiden': leiden_modularity,
        'n_analysed': len(eligible),
    }
    print(f'\nhead to head: k-means K={comparison["k_polis"]} '
          f'(silhouette {comparison["silhouette_polis"]:.3f}) vs '
          f'Leiden K={comparison["k_leiden"]} '
          f'(modularity {comparison["modularity_leiden"]:.4f}), '
          f'ARI {comparison["ari"]:.3f}')

    sweep_rows = [{'resolution': r,
                   'modularity': M.leiden_communities(graph_pids, weights, resolution=r)[1],
                   'K_leiden': len(set(M.leiden_communities(graph_pids, weights,
                                                            resolution=r)[0].values()))}
                  for r in (0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0)]
    figure = R.plot_method_comparison(b, conv, polis, leiden, pd.DataFrame(sweep_rows),
                                      matrix, eligible)

    server = P.server_labels(b, conv, 2)
    gate = P.reproduction_gate(b, conv, 2)

    # How far the rerun above lands from the tool's published grouping. It is not the
    # reproduction check — that one feeds the replica the same population the server
    # had and matches exactly (`gate`). This is the price of the two differences the
    # report makes on purpose: machine accounts dropped, and only people over the vote
    # threshold. Reported rather than glossed, because the two sets of group sizes both
    # appear on the page.
    shared_with_server = [p for p in polis if p in server.get('labels', {})]
    comparison['ari_vs_server'] = (
        adjusted_rand_score([server['labels'][p] for p in shared_with_server],
                            [polis[p] for p in shared_with_server])
        if len(shared_with_server) > 1 else float('nan'))
    print(f'rerun vs published grouping: ARI {comparison["ari_vs_server"]:.3f} '
          f'on {len(shared_with_server)} shared people '
          f'(reproduction gate on the server\'s own population: ARI {gate["ari"]:.3f})')
    head_to_heads = [M.head_to_head(b, conv, g) for g in groups]
    families = M.statement_families(b, conv)

    shared_kwargs = dict(
        bundle=b, conv_key=conv, checks=checks,
        funnel=P.participation_funnel(b, conv), server=server, gate=gate,
        sweep=M.leiden_sweep(b, gate), stability=M.cluster_stability(b, gate),
        divergence=R.statement_divergence(b, conv, server), groups=groups, pairs=pairs,
        head_to_heads=head_to_heads, effect=M.wording_effect(head_to_heads),
        roster=P.cluster_roster(b, conv),
        participation=M.wording_participation(b, conv, groups), families=families,
        generations=M.family_generations(families),
        descendants=M.statement_descendants(b, conv),
        representatives=M.family_representatives(b, conv, families),
        redundant=redundant, comparison_figure=figure, method_comparison=comparison,
        ladder=ladder, significance=significance)

    print()
    written = []
    for audience, name in (('organiser', 'report_organiser.html'),
                           ('participant', 'report_participant.html')):
        path = R.write_report(audience=audience, out=name, **shared_kwargs)
        written.append(path)
        print(f'  {audience:12s} {path}  {path.stat().st_size:,} bytes')

    if args.copy_to:
        target = Path(args.copy_to).expanduser()
        for path in written:
            destination = target / f'wiki-polis_{conv}_{path.stem.split("_")[-1]}.html'
            shutil.copy(path, destination)
            print(f'  copied  {destination}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
