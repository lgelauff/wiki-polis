"""Polis numbers statements from 0, so tid 0 is a real statement, not "no statement"."""

from unittest.mock import patch

import app as app_module
from db import FeaturedStatement, db


class _StubPolisServer:
    """Vote counts keyed by tid, as PolisServerClient.get_phase6_vote_counts returns them."""

    P6 = {10: {'n_agree': 3, 'n_disagree': 1, 'n_pass': 0, 'n_voters': 4},
          12: {'n_agree': 2, 'n_disagree': 2, 'n_pass': 0, 'n_voters': 4}}
    P2 = {0: {'n_agree': 1, 'n_disagree': 2, 'n_pass': 1, 'n_voters': 4},
          2: {'n_agree': 2, 'n_disagree': 1, 'n_pass': 1, 'n_voters': 4}}

    def __init__(self):
        self.p2_tids_requested = None

    def get_phase6_vote_counts(self, zinvite, allowed_tids, excluded_pids=None):
        if zinvite == 'phase2-zinvite':
            self.p2_tids_requested = list(allowed_tids)
            return {t: self.P2[t] for t in allowed_tids if t in self.P2}
        return {t: self.P6[t] for t in allowed_tids if t in self.P6}

    def get_phase6_participant_count(self, zinvite, excluded_pids=None):
        return 4


def test_featured_statement_with_tid_zero_keeps_its_explore_tallies(app, conversation):
    conversation.polis_id = 'phase2-zinvite'
    conversation.phase6_polis_conversation_id = 'phase6-zinvite'
    db.session.add_all([
        FeaturedStatement(conversation_id=conversation.id, polis_statement_id=0,
                          phase6_polis_statement_id=10, confirmed_by_admin=True,
                          statement_text='Shared technical infrastructure deserves more investment.'),
        FeaturedStatement(conversation_id=conversation.id, polis_statement_id=2,
                          phase6_polis_statement_id=12, confirmed_by_admin=True,
                          statement_text='Second seeded statement.'),
    ])
    db.session.commit()
    stub = _StubPolisServer()

    with app.test_request_context(), \
            patch.object(app_module, '_polis_server_client', return_value=stub), \
            patch.object(app_module, 'PolisParticipantClient') as pa:
        pa.return_value.get_results.return_value = None
        results = app_module._build_phase6_results(conversation, None)

    assert sorted(stub.p2_tids_requested) == [0, 2]
    row = next(s for s in results['statements']
               if s['text'].startswith('Shared technical'))
    assert row['p2'] is not None
    assert row['p2']['n_agree'] == 1 and row['p2']['n_voters'] == 4
    assert row['p2']['pct_agree'] == 25.0
    assert row['shift'] == 50.0          # 75% agree in Phase 6 vs 25% in Explore
    assert row in results['p2_consensus']
    assert row in results['p2_divisive']
