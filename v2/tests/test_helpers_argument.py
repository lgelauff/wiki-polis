"""Unit characterization of the argument-tab helpers that issue #90 lifted to module
level (`_get_or_create_side_state`, `_build_featured_data`, `_require_arg_participation`).

Promoted from #90's scratch suite after the senior + security review. Includes two
gap-fillers the reviewers asked for: the post-visit hide path (the production path that
enforces hidden-argument confidentiality once a participant's side-state already
exists) and the paused / phase-off authorization branches of the participation gate.
"""
import pytest
from werkzeug.exceptions import Forbidden

from app import (_build_featured_data, _get_or_create_side_state,
                 _require_arg_participation)
from db import (Argument, ArgumentSideState, ArgumentVote, Conversation,
                FeaturedStatement, Participation, db)


@pytest.fixture
def conv(app):
    c = Conversation(
        slug='s5-conv', polis_id='s5xxxxxxxx', title='S5', active=True,
        access_policy='public', phase_argument_mapping=True,
        argument_vote_data={'K': 2},
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def part(app, participant, conv):
    p = Participation(participant_id=participant.id, conversation_id=conv.id,
                      pseudonym='s5-fox')
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def fs(app, conv):
    f = FeaturedStatement(conversation_id=conv.id, polis_statement_id=42,
                          statement_text='Seed statement', confirmed_by_admin=True)
    db.session.add(f)
    db.session.commit()
    return f


def _args(fs_id, side, n):
    for i in range(n):
        db.session.add(Argument(featured_statement_id=fs_id, proposer_id=None,
                                body=f'{side} {i}', side=side))
    db.session.commit()
    return Argument.query.filter_by(featured_statement_id=fs_id, side=side).all()


def _participation(part, conv):
    return Participation.query.filter_by(
        participant_id=part.participant_id, conversation_id=conv.id).first()


# ── _get_or_create_side_state ───────────────────────────────────────────────────

def test_side_state_created_with_full_permutation(part, fs):
    args = _args(fs.id, 'pro', 4)
    ids = {a.id for a in args}
    state = _get_or_create_side_state(part.participant_id, fs.id, 'pro', args)
    assert state.id is not None                      # persisted
    assert set(state.argument_order) == ids          # all ids, no extras
    assert len(state.argument_order) == 4            # a permutation, not a subset


def test_side_state_appends_only_new_ids_and_is_idempotent(part, fs):
    args = _args(fs.id, 'pro', 2)
    s1 = _get_or_create_side_state(part.participant_id, fs.id, 'pro', args)
    order_before = list(s1.argument_order)

    # No new args → no change (idempotent).
    s2 = _get_or_create_side_state(part.participant_id, fs.id, 'pro', args)
    assert list(s2.argument_order) == order_before

    # One new arg → inserted; existing order otherwise preserved as a subsequence.
    _args(fs.id, 'pro', 1)                   # add 1 → 3 total (2 old + 1 new)
    more = Argument.query.filter_by(featured_statement_id=fs.id, side='pro').all()
    new_id = (set(a.id for a in more) - set(order_before)).pop()
    s3 = _get_or_create_side_state(part.participant_id, fs.id, 'pro', more)
    assert new_id in s3.argument_order
    assert len(s3.argument_order) == 3
    assert [i for i in s3.argument_order if i in order_before] == order_before


# ── _build_featured_data ────────────────────────────────────────────────────────

def test_build_featured_data_deterministic_per_participant(part, fs, conv):
    _args(fs.id, 'pro', 2)
    _args(fs.id, 'con', 2)
    r1 = _build_featured_data(conv, _participation(part, conv))
    r2 = _build_featured_data(conv, _participation(part, conv))
    # random.Random(pid) → stable ordering across calls for the same participant.
    assert [d['fs'].id for d in r1] == [d['fs'].id for d in r2]


def test_build_featured_data_gates_and_text_fallback(part, fs, conv):
    _args(fs.id, 'pro', 1)
    _args(fs.id, 'con', 1)
    data = _build_featured_data(conv, _participation(part, conv))
    assert len(data) == 1
    entry = data[0]
    # Participant has neither proposed nor skipped → both gates closed.
    assert entry['pro_gate'] is False and entry['con_gate'] is False
    # No Polis reachable in tests → text falls back to stored statement_text.
    assert entry['text'] == 'Seed statement'
    assert entry['k'] == 2


def test_build_featured_data_hidden_excluded_for_participant(part, fs, conv):
    pro = _args(fs.id, 'pro', 2)
    pro[0].hidden = True
    db.session.commit()
    # Non-moderator must not see hidden arguments.
    entry = _build_featured_data(conv, _participation(part, conv), can_mod=False)[0]
    assert pro[0].id not in {a.id for a in entry['pro_args']}
    # Moderator view includes them.
    entry_mod = _build_featured_data(conv, _participation(part, conv), can_mod=True)[0]
    assert pro[0].id in {a.id for a in entry_mod['pro_args']}


def test_build_featured_data_hides_argument_after_state_exists(part, fs, conv):
    """Production confidentiality path: participant visits first (side-state written
    with both ids), THEN a moderator hides an argument. On revisit it must drop out of
    the non-moderator view even though its id is still in the persisted argument_order
    — enforcement is the `if aid in arg_map` filter at render, not state mutation."""
    pro = _args(fs.id, 'pro', 2)
    # First visit creates the side-state containing both argument ids.
    _build_featured_data(conv, _participation(part, conv))
    state = ArgumentSideState.query.filter_by(
        participant_id=part.participant_id, featured_statement_id=fs.id,
        side='pro').first()
    assert pro[0].id in state.argument_order

    # Moderator hides the argument AFTER the participant's state exists.
    pro[0].hidden = True
    db.session.commit()

    entry = _build_featured_data(conv, _participation(part, conv), can_mod=False)[0]
    assert pro[0].id not in {a.id for a in entry['pro_args']}
    # The persisted order is untouched; filtering happens only at render time.
    refreshed = ArgumentSideState.query.filter_by(
        participant_id=part.participant_id, featured_statement_id=fs.id,
        side='pro').first()
    assert pro[0].id in refreshed.argument_order


def test_build_featured_data_reflects_votes(part, fs, conv):
    pro = _args(fs.id, 'pro', 2)
    db.session.add(ArgumentVote(argument_id=pro[0].id,
                                participant_id=part.participant_id))
    db.session.commit()
    entry = _build_featured_data(conv, _participation(part, conv))[0]
    assert pro[0].id in entry['voted_ids']


# ── _require_arg_participation (authorization gate) ─────────────────────────────

def test_require_arg_participation_gate_branches(app, participant, conv, part):
    """Happy path returns (conv, participation); paused or phase-off must abort 403."""
    from flask import session

    # Active + in the argument phase + participating → returns the pair.
    with app.test_request_context():
        session['username'] = participant.mw_username
        got_conv, got_part = _require_arg_participation(conv.slug)
        assert got_conv.id == conv.id
        assert got_part.participant_id == participant.id

    # Paused conversation → 403.
    conv.paused = True
    db.session.commit()
    with app.test_request_context():
        session['username'] = participant.mw_username
        with pytest.raises(Forbidden):
            _require_arg_participation(conv.slug)

    # Not in the argument-mapping phase → 403.
    conv.paused = False
    conv.phase_argument_mapping = False
    db.session.commit()
    with app.test_request_context():
        session['username'] = participant.mw_username
        with pytest.raises(Forbidden):
            _require_arg_participation(conv.slug)
