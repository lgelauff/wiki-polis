"""Tests for phase-specific statistics in the admin conversation window (#165).

Covers the per-phase tile selection in _phase_tiles() and the loud warning raised
when Polis PG is configured but unreachable.

Ported off the Jinja admin page onto GET /api/v1/admin/conversations/<id>, which
exposes the same computation as ``statistics.groups[].tiles[]`` plus the
``statistics.upstreamUnavailable`` flag. What is deliberately *not* asserted here
any more is the rendering: the tile markup, the ``aria-labelledby`` wiring and the
warning/header copy ("Live statistics unavailable", "Multiple phases active",
"... shown below") are the SPA's, not the server's. The server decides which
groups exist, which tiles they carry, what those tiles read, and whether the
upstream is flagged as down — and that is what these tests hold.
"""
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


def _lifecycle(admin_client, conv):
    resp = admin_client.get(f'/api/v1/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    return resp.get_json()['data']


def _stats(admin_client, conv):
    return _lifecycle(admin_client, conv)['statistics']


def _tile(stats, label):
    """The tile carrying `label`, from whichever group holds it, or None."""
    for group in stats['groups']:
        for tile in group['tiles']:
            if tile['label'] == label:
                return tile
    return None


def _tile_value(stats, label):
    tile = _tile(stats, label)
    return tile['value'] if tile else None


def _tiled_group_labels(stats):
    """Labels of the groups that actually carry tiles.

    A group with no tiles rendered no block in the old page, so it is excluded
    here too — that is what 'Explore yields no tiles, so it gets no group block'
    used to mean.
    """
    return [g['label'] for g in stats['groups'] if g['tiles']]


# ── Featured-selection phase ────────────────────────────────────────────────────

def test_featured_selection_shows_selected_vs_recommended(admin_client, conv):
    conv.phase_personal_results = True            # featured_selection stage
    for i in range(3):
        db.session.add(FeaturedStatement(conversation_id=conv.id, polis_statement_id=i,
                                         confirmed_by_admin=True))
    db.session.add(FeaturedStatement(conversation_id=conv.id, polis_statement_id=9,
                                     confirmed_by_admin=False))   # not confirmed
    db.session.commit()

    stats = _stats(admin_client, conv)
    assert _tile_value(stats, 'featured selected') == 3
    assert 'recommended' in _tile(stats, 'featured selected')['note']   # advisory note


# ── Argument-mapping phase ──────────────────────────────────────────────────────

def test_argument_mapping_counts_pro_con_contributors_raters(admin_client, conv):
    conv.phase_argument_mapping = True
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=1,
                           confirmed_by_admin=True)
    db.session.add(fs)
    db.session.commit()

    pro1 = Argument(featured_statement_id=fs.id, proposer_pseudonym='contrib-one',
                    body='pro a', side='pro')
    pro2 = Argument(featured_statement_id=fs.id, proposer_pseudonym='contrib-two',
                    body='pro b', side='pro')
    con1 = Argument(featured_statement_id=fs.id, proposer_pseudonym='contrib-one',
                    body='con a', side='con')
    seed = Argument(featured_statement_id=fs.id, proposer_pseudonym=None,
                    body='seed', side='pro')
    hidden = Argument(featured_statement_id=fs.id, proposer_pseudonym='contrib-two',
                      body='bad', side='con',
                      hidden=True)
    db.session.add_all([pro1, pro2, con1, seed, hidden])
    db.session.commit()

    rater = _participant(103, 'rater1')
    db.session.add(ArgumentVote(argument_id=pro1.id, participant_id=rater.id))
    db.session.add(ArgumentVote(argument_id=con1.id, participant_id=rater.id))
    db.session.commit()

    stats = _stats(admin_client, conv)
    # Seeds (NULL proposer) and hidden args are excluded from the counts.
    assert _tile_value(stats, 'pro arguments') == 2
    assert _tile_value(stats, 'con arguments') == 1
    assert _tile_value(stats, 'contributors') == 2      # p1, p2 — distinct
    assert _tile_value(stats, 'rating arguments') == 1  # one distinct rater


def test_argument_mapping_raters_exclude_hidden_only_voters(admin_client, conv):
    # A participant who rated *only* a hidden argument must not inflate the rater count —
    # n_raters applies the same Argument.hidden filter as the other tiles (#165 should-fix).
    conv.phase_argument_mapping = True
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=1,
                           confirmed_by_admin=True)
    db.session.add(fs)
    db.session.commit()

    visible = Argument(featured_statement_id=fs.id, proposer_pseudonym='author-fox',
                       body='visible', side='pro')
    hidden = Argument(featured_statement_id=fs.id, proposer_pseudonym='author-fox',
                      body='moderated', side='con', hidden=True)
    db.session.add_all([visible, hidden])
    db.session.commit()

    visible_rater = _participant(202, 'visible_rater')
    hidden_rater = _participant(203, 'hidden_rater')
    db.session.add(ArgumentVote(argument_id=visible.id, participant_id=visible_rater.id))
    db.session.add(ArgumentVote(argument_id=hidden.id, participant_id=hidden_rater.id))
    db.session.commit()

    stats = _stats(admin_client, conv)
    # Only the visible-arg rater counts; the hidden-only rater is excluded.
    assert _tile_value(stats, 'rating arguments') == 1


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
        stats = _stats(admin_client, conv)

    assert _tile_value(stats, 'statements seeded') == '1/1'
    assert _tile_value(stats, 'voted this round') == 7
    assert _tile_value(stats, 'informed votes') == 21
    assert _tile_value(stats, 'round 1 participants') == 12


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
        stats = _stats(admin_client, conv)

    assert stats['upstreamUnavailable'] is True
    # Round-2 tiles are absent (no phase6_stats); the flag explains why.
    assert _tile_value(stats, 'voted this round') is None


# ── Multiple phases active at once (advanced mode) ──────────────────────────────

def test_multi_phase_renders_a_group_per_active_phase(admin_client, conv):
    # Two phase flags on → every active phase is reported, each as its own labelled
    # stat group with its own tiles (not just the furthest-along one).
    conv.phase_argument_mapping = True
    conv.phase_informed_voting = True
    conv.phase6_polis_conversation_id = 'p6conv1234'
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=1,
                           confirmed_by_admin=True, phase6_polis_statement_id=0)
    db.session.add(fs)
    db.session.commit()
    db.session.add(Argument(featured_statement_id=fs.id, proposer_pseudonym='author-fox',
                            body='pro a', side='pro'))
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
        data = _lifecycle(admin_client, conv)
    stats = data['statistics']

    assert len(data['phase']['activeKeys']) > 1          # more than one phase active
    assert data['phase']['linear'] is False
    # A labelled group for each active phase.
    assert _tiled_group_labels(stats) == ['Arguments', 'Informed vote']
    # Tiles from both groups are present.
    assert _tile_value(stats, 'pro arguments') == 1
    assert _tile_value(stats, 'statements seeded') == '1/1'
    assert _tile_value(stats, 'voted this round') == 7


def test_single_phase_reports_one_group_and_no_multi_phase_state(admin_client, conv):
    # One active phase → a single group, and the server does not report the
    # multi-phase (non-linear) state the page used to headline.
    conv.phase_argument_mapping = True
    db.session.commit()
    data = _lifecycle(admin_client, conv)

    assert data['phase']['activeKeys'] == ['argument_mapping']
    assert data['phase']['linear'] is True
    assert _tiled_group_labels(data['statistics']) == ['Arguments']


def test_multi_phase_informed_voting_warns_on_phase6_outage(app, admin_client, conv):
    # Advanced/non-linear: informed-voting + public-results both on. The informed-voting
    # group renders, so a failed phase-6 fetch DOES drop its round-2 tiles — the warning
    # must fire (the round-2 tiles are genuinely shown when the flag is on).
    app.config['POLIS_DATABASE_URL'] = 'postgresql://unused/db'
    conv.phase_informed_voting = True
    conv.phase_public_results = True
    conv.phase6_polis_conversation_id = 'p6conv1234'
    db.session.commit()

    def stats_for(zinvite):
        if zinvite == 'p6conv1234':
            return None                              # round-2 PG unreachable
        return {'n_participants': 12, 'n_votes': 80, 'avg_votes': 6.0,
                'median_votes': 6.0, 'n_statements': 10, 'n_seed': 2}

    server = MagicMock()
    server.get_polis_stats.side_effect = stats_for
    with patch('app._polis_server_client', return_value=server):
        data = _lifecycle(admin_client, conv)

    assert data['statistics']['upstreamUnavailable'] is True
    assert len(data['phase']['activeKeys']) > 1


def test_multi_phase_lone_tiled_group_is_still_labelled(admin_client, conv):
    # Non-linear with two phases named, but only one currently has data: Explore is
    # Polis-only (no tiles while PG is down) and Arguments has Flask-derived tiles. The
    # single tiled group must still carry its phase label — otherwise the header names
    # two phases over one anonymous block and the reader can't tell whose numbers these are.
    conv.phase_submission = True            # Explore — polis_basic() → [] (no polis stats)
    conv.phase_argument_mapping = True      # Arguments — Flask tiles always render
    db.session.commit()

    data = _lifecycle(admin_client, conv)
    stats = data['statistics']
    # The header names both active phases.
    assert sorted(data['phase']['activeKeys']) == ['argument_mapping', 'submission']
    assert [g['label'] for g in stats['groups']] == ['Explore', 'Arguments']
    # Explore yields no tiles, so it contributes no tiled block of its own; the one
    # block that does render is labelled.
    assert _tiled_group_labels(stats) == ['Arguments']


def test_multi_phase_all_polis_only_yields_no_tiled_group(admin_client, conv):
    # Two Polis-only phases active with no Polis stats (PG unconfigured → no warning):
    # neither yields tiles. The phases are still named, but nothing is left to show, so
    # the page had to drop its "...shown below" promise rather than leave it dangling.
    conv.phase_submission = True            # Explore — polis-only
    conv.phase_public_results = True        # Report  — polis-only
    db.session.commit()

    data = _lifecycle(admin_client, conv)
    stats = data['statistics']
    assert len(data['phase']['activeKeys']) > 1
    assert [g['label'] for g in stats['groups']] == ['Explore', 'Report']
    assert _tiled_group_labels(stats) == []               # nothing to show below
    assert stats['upstreamUnavailable'] is False          # PG unconfigured — None is expected


def test_multi_phase_stepper_marks_every_active_step_current(admin_client, conv):
    # The journey stepper must agree with the hero: in non-linear mode every active phase
    # is "current" and none is shown as "done", rather than marking earlier still-open
    # phases complete off the single furthest-along stage.
    conv.phase_submission = True            # index 1
    conv.phase_argument_mapping = True      # index 3 (non-contiguous)
    db.session.commit()

    steps = _lifecycle(admin_client, conv)['phase']['steps']
    states = [s['state'] for s in steps]
    assert states.count('current') == 2                   # both active steps marked current
    assert 'done' not in states                           # nothing collapsed to "done"


# ── Loud warning when Polis PG is configured but down ───────────────────────────

def test_warning_when_pg_configured_but_unavailable(app, admin_client, conv):
    app.config['POLIS_DATABASE_URL'] = 'postgresql://unused/db'
    server = MagicMock()
    server.get_polis_stats.return_value = None        # PG unreachable
    with patch('app._polis_server_client', return_value=server):
        stats = _stats(admin_client, conv)
    assert stats['upstreamUnavailable'] is True


def test_no_warning_when_pg_not_configured(admin_client, conv):
    # POLIS_DATABASE_URL is unset in the test app — None stats are expected, not an error.
    server = MagicMock()
    server.get_polis_stats.return_value = None
    with patch('app._polis_server_client', return_value=server):
        stats = _stats(admin_client, conv)
    assert stats['upstreamUnavailable'] is False
