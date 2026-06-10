"""Tests for phase-specific statistics in the admin conversation window (#165).

Covers the per-phase tile selection in _phase_stats() and the loud warning shown
when Polis PG is configured but unreachable.
"""
import re
from unittest.mock import MagicMock, patch

import pytest

from db import (Argument, ArgumentVote, Conversation, FeaturedStatement,
                Participant, Participation, db)


@pytest.fixture
def conv(app):
    c = Conversation(
        slug='stats-conv', polis_id='sta1234567',
        title='Stats Test Conv', active=True, access_policy='public',
    )
    db.session.add(c)
    db.session.commit()
    return c


def _participant(uid, name):
    p = Participant(mw_user_id=uid, mw_username=name, xid=f'xid{uid}')
    db.session.add(p)
    db.session.commit()
    return p


def _tile_value(html, label):
    """Return the tile value rendered next to the given phase-stat label, or None.

    The negative lookahead keeps the captured value within the same tile — it must
    not skip across an intervening phase-stat-value div to reach the label.
    """
    m = re.search(
        r'phase-stat-value">([^<]*)<(?:(?!phase-stat-value).)*?phase-stat-label">'
        + re.escape(label) + '<',
        html, re.DOTALL)
    return m.group(1).strip() if m else None


# ── Featured-selection phase ────────────────────────────────────────────────────

def test_featured_selection_shows_selected_vs_recommended(admin_client, conv):
    conv.phase_personal_results = True            # featured_selection stage
    for i in range(3):
        db.session.add(FeaturedStatement(conversation_id=conv.id, polis_statement_id=i,
                                         confirmed_by_admin=True))
    db.session.add(FeaturedStatement(conversation_id=conv.id, polis_statement_id=9,
                                     confirmed_by_admin=False))   # not confirmed
    db.session.commit()

    page = admin_client.get(f'/admin/conversations/{conv.id}').get_data(as_text=True)
    assert _tile_value(page, 'featured selected') == '3'
    assert 'recommended' in page                  # advisory note rendered


# ── Argument-mapping phase ──────────────────────────────────────────────────────

def test_argument_mapping_counts_pro_con_contributors_raters(admin_client, conv):
    conv.phase_argument_mapping = True
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=1,
                           confirmed_by_admin=True)
    db.session.add(fs)
    db.session.commit()

    p1, p2 = _participant(101, 'contrib1'), _participant(102, 'contrib2')
    pro1 = Argument(featured_statement_id=fs.id, proposer_id=p1.id, body='pro a', side='pro')
    pro2 = Argument(featured_statement_id=fs.id, proposer_id=p2.id, body='pro b', side='pro')
    con1 = Argument(featured_statement_id=fs.id, proposer_id=p1.id, body='con a', side='con')
    seed = Argument(featured_statement_id=fs.id, proposer_id=None, body='seed', side='pro')
    hidden = Argument(featured_statement_id=fs.id, proposer_id=p2.id, body='bad', side='con',
                      hidden=True)
    db.session.add_all([pro1, pro2, con1, seed, hidden])
    db.session.commit()

    rater = _participant(103, 'rater1')
    db.session.add(ArgumentVote(argument_id=pro1.id, participant_id=rater.id))
    db.session.add(ArgumentVote(argument_id=con1.id, participant_id=rater.id))
    db.session.commit()

    page = admin_client.get(f'/admin/conversations/{conv.id}').get_data(as_text=True)
    # Seeds (NULL proposer) and hidden args are excluded from the counts.
    assert _tile_value(page, 'pro arguments') == '2'
    assert _tile_value(page, 'con arguments') == '1'
    assert _tile_value(page, 'contributors') == '2'      # p1, p2 — distinct
    assert _tile_value(page, 'rating arguments') == '1'  # one distinct rater


def test_argument_mapping_raters_exclude_hidden_only_voters(admin_client, conv):
    # A participant who rated *only* a hidden argument must not inflate the rater count —
    # n_raters applies the same Argument.hidden filter as the other tiles (#165 should-fix).
    conv.phase_argument_mapping = True
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=1,
                           confirmed_by_admin=True)
    db.session.add(fs)
    db.session.commit()

    author = _participant(201, 'author')
    visible = Argument(featured_statement_id=fs.id, proposer_id=author.id,
                       body='visible', side='pro')
    hidden = Argument(featured_statement_id=fs.id, proposer_id=author.id,
                      body='moderated', side='con', hidden=True)
    db.session.add_all([visible, hidden])
    db.session.commit()

    visible_rater = _participant(202, 'visible_rater')
    hidden_rater = _participant(203, 'hidden_rater')
    db.session.add(ArgumentVote(argument_id=visible.id, participant_id=visible_rater.id))
    db.session.add(ArgumentVote(argument_id=hidden.id, participant_id=hidden_rater.id))
    db.session.commit()

    page = admin_client.get(f'/admin/conversations/{conv.id}').get_data(as_text=True)
    # Only the visible-arg rater counts; the hidden-only rater is excluded.
    assert _tile_value(page, 'rating arguments') == '1'


# ── Informed-voting phase ───────────────────────────────────────────────────────

def test_informed_voting_shows_round2_stats(admin_client, conv):
    conv.phase_informed_voting = True
    conv.phase6_polis_conversation_id = 'p6conv1234'
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=1,
                           confirmed_by_admin=True, phase6_polis_statement_id=0)
    db.session.add(fs)
    db.session.commit()

    def stats_for(zinvite):
        if zinvite == 'p6conv1234':
            return {'n_participants': 7, 'n_votes': 21, 'avg_votes': 3.0,
                    'median_votes': 3.0, 'n_statements': 1, 'n_seed': 1}
        return {'n_participants': 12, 'n_votes': 80, 'avg_votes': 6.0,
                'median_votes': 6.0, 'n_statements': 10, 'n_seed': 2}

    server = MagicMock()
    server.get_polis_stats.side_effect = stats_for
    with patch('app._polis_server_client', return_value=server):
        page = admin_client.get(f'/admin/conversations/{conv.id}').get_data(as_text=True)

    assert _tile_value(page, 'statements seeded') == '1/1'
    assert _tile_value(page, 'voted this round') == '7'
    assert _tile_value(page, 'informed votes') == '21'
    assert _tile_value(page, 'round 1 participants') == '12'


def test_informed_voting_warns_when_phase6_fetch_fails(app, admin_client, conv):
    # Round-1 stats succeed but the phase-6 (round-2) fetch returns None. The warning
    # must still fire — otherwise the round-2 tiles vanish silently (#165 must-fix).
    app.config['POLIS_DATABASE_URL'] = 'postgresql://unused/db'
    conv.phase_informed_voting = True
    conv.phase6_polis_conversation_id = 'p6conv1234'
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=1,
                           confirmed_by_admin=True, phase6_polis_statement_id=0)
    db.session.add(fs)
    db.session.commit()

    def stats_for(zinvite):
        if zinvite == 'p6conv1234':
            return None                              # round-2 PG unreachable
        return {'n_participants': 12, 'n_votes': 80, 'avg_votes': 6.0,
                'median_votes': 6.0, 'n_statements': 10, 'n_seed': 2}

    server = MagicMock()
    server.get_polis_stats.side_effect = stats_for
    with patch('app._polis_server_client', return_value=server):
        page = admin_client.get(f'/admin/conversations/{conv.id}').get_data(as_text=True)

    assert 'phase-stats-warning' in page
    assert 'Live statistics unavailable' in page
    # Round-2 tiles are absent (no phase6_stats); the warning explains why.
    assert _tile_value(page, 'voted this round') is None


def test_no_round2_warning_when_informed_voting_not_displayed_stage(app, admin_client, conv):
    # Non-linear state: both informed-voting and public-results flags are on, so the
    # *displayed* stage is public_results (furthest-along). No round-2 tiles render, so a
    # failed phase-6 fetch must NOT trip the warning — it tracks the shown stage, not the
    # raw flag (#165). Guards the false-positive the flag-based condition would have raised.
    app.config['POLIS_DATABASE_URL'] = 'postgresql://unused/db'
    conv.phase_informed_voting = True
    conv.phase_public_results = True
    conv.phase6_polis_conversation_id = 'p6conv1234'
    db.session.commit()

    def stats_for(zinvite):
        if zinvite == 'p6conv1234':
            return None                              # round-2 PG unreachable (but not shown)
        return {'n_participants': 12, 'n_votes': 80, 'avg_votes': 6.0,
                'median_votes': 6.0, 'n_statements': 10, 'n_seed': 2}

    server = MagicMock()
    server.get_polis_stats.side_effect = stats_for
    with patch('app._polis_server_client', return_value=server):
        page = admin_client.get(f'/admin/conversations/{conv.id}').get_data(as_text=True)

    # Round-1 stats are healthy and shown; the irrelevant phase-6 failure stays silent.
    assert 'phase-stats-warning' not in page


# ── Loud warning when Polis PG is configured but down ───────────────────────────

def test_warning_when_pg_configured_but_unavailable(app, admin_client, conv):
    app.config['POLIS_DATABASE_URL'] = 'postgresql://unused/db'
    server = MagicMock()
    server.get_polis_stats.return_value = None        # PG unreachable
    with patch('app._polis_server_client', return_value=server):
        page = admin_client.get(f'/admin/conversations/{conv.id}').get_data(as_text=True)
    assert 'phase-stats-warning' in page
    assert 'Live statistics unavailable' in page


def test_no_warning_when_pg_not_configured(admin_client, conv):
    # POLIS_DATABASE_URL is unset in the test app — None stats are expected, not an error.
    server = MagicMock()
    server.get_polis_stats.return_value = None
    with patch('app._polis_server_client', return_value=server):
        page = admin_client.get(f'/admin/conversations/{conv.id}').get_data(as_text=True)
    assert 'phase-stats-warning' not in page
