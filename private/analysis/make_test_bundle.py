#!/usr/bin/env python3
"""Build a synthetic bundle that exercises every path in the pipeline.

This is a PLUMBING test, not a validation of the clustering. Its `math_main` is
produced by running the replica and writing the result in the engine's own JSON
shape — so the reproduction gate necessarily passes and proves nothing about
agreement with the real Clojure engine. Only a bundle exported from a real Polis
database (local stack or server) can do that.

What it does prove: the bundle loads, the integrity checks fire, matrices build,
Leiden runs, near-duplicate groups form, head-to-heads compute, and the report
renders — without waiting on docker.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle import BundleWriter, load_salt, person_key  # noqa: E402

CONV = 'test-conv'
SALT_FILE = Path(__file__).with_name('.test_salt')

# Ten propositions; the last two each get a near-duplicate rewording so the
# wording-effect path has something to chew on.
STATEMENTS = [
    'Members should serve a term of two years',
    'Members should be elected by the community',
    'A case needs at least three arbitrators',
    'Requests must show prior attempts at resolution',
    'Decisions should be published in full',
    'Blocked users may request clarification',
    'The committee should meet monthly',
    'Candidates need one year of tenure',
    'Candidates need at least a thousand edits',
    'Appeals must explain what has changed since',
]
NEAR_DUPLICATES = [
    (8, 'Candidates need at least a thousand non-vandalism edits'),
    (8, 'Candidates need at least a thousand edits in the article namespace'),
    (7, 'Candidates need at least one year of tenure before the election'),
]

N_GROUP_A, N_GROUP_B = 22, 18


def main() -> int:
    rng = np.random.default_rng(20260606)
    if not SALT_FILE.exists():
        SALT_FILE.write_text('0' * 64)
    salt = load_salt(SALT_FILE)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else 'test_bundle')

    texts = list(STATEMENTS)
    parent_of: dict[int, int] = {}
    for parent_tid, text in NEAR_DUPLICATES:
        parent_of[len(texts)] = parent_tid
        texts.append(text)

    n_people = N_GROUP_A + N_GROUP_B
    # Group A agrees with the even-indexed propositions, group B with the odd.
    # A derivative inherits its parent's stance, so a lineage looks like a lineage.
    stance = np.zeros((n_people, len(texts)))
    for tid in range(len(texts)):
        base = parent_of.get(tid, tid)
        for pid in range(n_people):
            group_a = pid < N_GROUP_A
            agrees = (base % 2 == 0) if group_a else (base % 2 == 1)
            stance[pid, tid] = -1 if agrees else 1

    # One of the three rewordings genuinely shifts a few people, so the
    # head-to-head has a real effect to find.
    shifted_tid = len(STATEMENTS)
    for pid in rng.choice(N_GROUP_A, size=6, replace=False):
        stance[pid, shifted_tid] = 1

    votes, history = [], []
    for pid in range(n_people):
        # A handful of people vote on very little, so the funnel and the in-conv
        # threshold both have someone to exclude.
        n_seen = 3 if pid % 13 == 0 else len(texts)
        for tid in range(n_seen):
            vote = int(stance[pid, tid])
            if rng.random() < 0.08:
                vote = 0
            elif rng.random() < 0.06:
                vote = -vote
            key = person_key(salt, f'xid-{pid:03d}')
            timestamp = 1_770_000_000_000 + pid * 1000 + tid
            votes.append([CONV, 2, key, pid, tid, vote, timestamp])
            history.append([CONV, 2, key, pid, tid, vote, timestamp])

    # No author column: statement authorship is deliberately not exported.
    statements_rows = [
        [CONV, 2, tid, tid < len(STATEMENTS), 0, True,
         1_770_000_000_000 + tid, 'en', text]
        for tid, text in enumerate(texts)
    ]
    participants_rows = [
        [CONV, 2, person_key(salt, f'xid-{pid:03d}'), pid,
         sum(1 for v in votes if v[3] == pid), 1_770_000_100_000, True]
        for pid in range(n_people)
    ]

    # math_main, in the engine's own shape, from the replica.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pipeline import POLIS_STUDY  # noqa: F401  (sets sys.path for the replica)
    from analysis.polis_replica import run_replica

    matrix = np.full((n_people, len(texts)), np.nan)
    for _, _, _, pid, tid, vote, _ in votes:
        matrix[pid, tid] = vote
    result = run_replica(matrix)

    base_members: dict[int, list[int]] = {}
    for cluster in result['base_clusters']:
        base_members[int(cluster['id'])] = [int(m) for m in cluster['members']]
    group_clusters = [
        {'id': int(gi), 'center': [float(x) for x in g['center']],
         'members': [int(m) for m in g['members']]}
        for gi, g in enumerate(result['group_clusters'])
    ]
    math_payload = {
        'conv_key': CONV, 'phase': 2, 'zinvite': 'testzin001',
        'math_env': 'test', 'last_vote_timestamp': 1_770_000_100_000,
        'math_tick': 1, 'modified': 1_770_000_100_000,
        'data': {
            'n': n_people, 'n-cmts': len(texts),
            'tids': list(range(len(texts))),
            'in-conv': [int(p) for p in result['in_conv']],
            'mod-in': [], 'mod-out': [], 'meta-tids': [],
            'base-clusters': {
                'id': sorted(base_members),
                'members': [base_members[i] for i in sorted(base_members)],
                'count': [len(base_members[i]) for i in sorted(base_members)],
            },
            'group-clusters': group_clusters,
        },
    }

    polis = BundleWriter(out, kind='polis', env='local', salt=salt, with_text=True,
                         extra_manifest={'conversations': [
                             {'conv_key': CONV, 'phase': 2, 'zinvite': 'testzin001',
                              'n_participants': n_people, 'n_identity_linked': n_people,
                              'n_statements': len(texts), 'n_votes_latest': len(votes),
                              'n_votes_history': len(history), 'has_math_main': True}]})
    polis.add_csv('conversations.csv',
                  ['conv_key', 'phase', 'zinvite', 'is_active', 'is_public',
                   'strict_moderation', 'vis_type', 'created_ms'],
                  [[CONV, 2, 'testzin001', True, True, False, 1, 1_770_000_000_000]])
    polis.add_csv('participants.csv',
                  ['conv_key', 'phase', 'person_key', 'pid', 'vote_count',
                   'last_interaction_ms', 'identity_linked'], participants_rows)
    polis.add_csv('statements.csv',
                  ['conv_key', 'phase', 'tid', 'is_seed', 'mod',
                   'active', 'created_ms', 'lang', 'txt'], statements_rows)
    polis.add_csv('votes_latest.csv',
                  ['conv_key', 'phase', 'person_key', 'pid', 'tid', 'vote', 'modified_ms'],
                  votes)
    polis.add_csv('votes_history.csv',
                  ['conv_key', 'phase', 'person_key', 'pid', 'tid', 'vote', 'created_ms'],
                  history)
    polis.add_json(f'math_main/{CONV}_phase2.json', math_payload)
    polis.close()

    app = BundleWriter(out, kind='app', env='local', salt=salt, with_text=True,
                       allow_columns={'pseudonym'},
                       extra_manifest={'conversations': [
                           {'conv_key': CONV, 'phase2_zinvite': 'testzin001',
                            'phase6_zinvite': None, 'n_participations': n_people,
                            'n_featured': 0, 'n_featured_confirmed': 0,
                            'n_featured_bridged': 0,
                            'n_provenance': len(NEAR_DUPLICATES), 'n_arguments': 0}],
                           'with_arguments': False, 'with_pseudonyms': True})
    app.add_csv('conversations.csv',
                ['conv_key', 'slug', 'polis_id', 'phase6_polis_conversation_id', 'title',
                 'language', 'access_policy', 'phase_route', 'active', 'paused',
                 'phase_submission', 'phase_personal_results', 'phase_argument_mapping',
                 'phase_cleanup', 'phase_public_results', 'phase_informed_voting',
                 'argument_vote_method', 'created_at', 'closed_at', 'n_participations'],
                [[CONV, CONV, 'testzin001', None, 'Synthetic test', 'en', 'public',
                  'default_7', True, False, True, True, False, False, True, False,
                  'kApproval', '2026-01-01', None, n_people]])
    app.add_csv('featured_statements.csv',
                ['conv_key', 'polis_statement_id', 'phase6_polis_statement_id',
                 'suggested_by_system', 'confirmed_by_admin', 'created_at',
                 'statement_text'], [])
    # Only two of the three rewordings were *declared* as improvements — the third
    # must be found by the embeddings alone, which is what makes the detected-vs-
    # declared comparison meaningful.
    app.add_csv('statement_provenance.csv',
                ['conv_key', 'polis_statement_id', 'derived_from_tid', 'provenance_type',
                 'link_method', 'created_at'],
                [[CONV, tid, parent, 'derivative', 'declared', '2026-01-02']
                 for tid, parent in list(parent_of.items())[:2]])
    app.add_csv('statement_similarity.csv',
                ['conv_key', 'polis_statement_id', 'model', 'value', 'scored_at'],
                [[CONV, tid, 'semantic-v1', 0.93, '2026-01-02']
                 for tid in list(parent_of)[:2]])
    app.add_csv('people.csv', ['conv_key', 'person_key', 'pseudonym'],
                [[CONV, person_key(salt, f'xid-{pid:03d}'), f'testuser-{pid:03d}']
                 for pid in range(n_people)])
    app.close()

    print(f'\nsynthetic bundle written to {out}')
    print(f'  {n_people} people, {len(texts)} statements '
          f'({len(NEAR_DUPLICATES)} of them rewordings), {len(votes):,} votes')
    print(f'  replica K={result["K"]}  (written into math_main — plumbing only)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
