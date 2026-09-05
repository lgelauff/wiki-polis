"""Tests for the argument mapping layer: submit, skip, prioritize, admin featured.

Ported from the deleted Jinja routes to the /api/v1 surface. The behavioural
assertions (DB state, permissions, audit rows) are unchanged; only the transport
moved. Deletions are recorded inline where a Jinja-only assertion had no
server-side counterpart.
"""
from unittest.mock import patch

import pytest

from db import (Argument, ArgumentSideState, ArgumentVote, AuditEvent, ContentFlag,
                Conversation, ConversationBan, FeaturedStatement, Participant,
                Participation, db)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def arg_conv(app):
    c = Conversation(
        slug='arg-conv', polis_id='arg1234567',
        title='Arg Conv', active=True, access_policy='public',
        phase_argument_mapping=True,
        argument_vote_data={'K': 2},
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def arg_part(app, participant, arg_conv):
    p = Participation(
        participant_id=participant.id,
        conversation_id=arg_conv.id,
        pseudonym='test-fox',
    )
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def fs(app, arg_conv):
    f = FeaturedStatement(
        conversation_id=arg_conv.id,
        polis_statement_id=42,
        confirmed_by_admin=True,
    )
    db.session.add(f)
    db.session.commit()
    return f


@pytest.fixture
def other_participant(app):
    p = Participant(mw_user_id=22222, mw_username='other', xid='o' * 64)
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def other_part(app, other_participant, arg_conv):
    p = Participation(
        participant_id=other_participant.id,
        conversation_id=arg_conv.id,
        pseudonym='other-fox',
    )
    db.session.add(p)
    db.session.commit()
    return p


def _make_args(fs_id, proposer_pseudonym, side, n):
    """Insert n seeded arguments for a side."""
    for i in range(n):
        a = Argument(
            featured_statement_id=fs_id,
            proposer_pseudonym=None,   # seeded — exempt from unique constraint
            body=f'Argument {i}',
            side=side,
        )
        db.session.add(a)
    db.session.commit()
    return Argument.query.filter_by(featured_statement_id=fs_id, side=side).all()


def _arguments_path(slug, fs_id):
    return f'/api/v1/conversations/{slug}/featured-statements/{fs_id}/arguments'


def _skip_path(slug, fs_id, side):
    return (f'/api/v1/conversations/{slug}/featured-statements/{fs_id}'
            f'/contributions/{side}/skip')


def _priority_path(slug, argument_id):
    return f'/api/v1/conversations/{slug}/arguments/{argument_id}/priority'


def _featured_argument_path(conv_id, argument_id):
    return (f'/api/v1/admin/conversations/{conv_id}'
            f'/featured-arguments/{argument_id}')


# ── Argument submission ────────────────────────────────────────────────────────

def test_submit_pro_argument(auth_client, arg_conv, arg_part, fs, participant):
    resp = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'pro', 'body': 'This is a pro argument.',
    })
    assert resp.status_code == 201
    arg = Argument.query.filter_by(
        proposer_pseudonym=arg_part.pseudonym, featured_statement_id=fs.id, side='pro').first()
    assert arg is not None
    assert arg.body == 'This is a pro argument.'
    assert resp.get_json()['data']['argument']['id'] == arg.id


def test_submit_updates_last_engagement(auth_client, arg_conv, arg_part, fs):
    assert arg_part.last_engagement is None
    resp = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'pro', 'body': 'This is a pro argument.',
    })
    assert resp.status_code == 201
    db.session.refresh(arg_part)
    assert arg_part.last_engagement is not None


def test_submit_con_argument(auth_client, arg_conv, arg_part, fs, participant):
    resp = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'con', 'body': 'This is a con argument.',
    })
    assert resp.status_code == 201
    assert Argument.query.filter_by(
        proposer_pseudonym=arg_part.pseudonym, featured_statement_id=fs.id, side='con').first()


def test_submit_invalid_side_rejected(auth_client, arg_conv, arg_part, fs):
    resp = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'neutral', 'body': 'Text.',
    })
    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'validation_failed'
    assert Argument.query.filter_by(featured_statement_id=fs.id).count() == 0


def test_submit_empty_body_rejected(auth_client, arg_conv, arg_part, fs):
    resp = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'pro', 'body': '',
    })
    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'validation_failed'
    assert Argument.query.filter_by(featured_statement_id=fs.id).count() == 0


def test_submit_body_too_long_rejected(auth_client, arg_conv, arg_part, fs):
    resp = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'pro', 'body': 'x' * 281,
    })
    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'validation_failed'
    assert Argument.query.filter_by(featured_statement_id=fs.id).count() == 0


def test_submit_duplicate_keeps_single_argument(auth_client, arg_conv, arg_part, fs,
                                                participant):
    """A second, different argument on the same side never creates a second row.

    The Jinja route swallowed the duplicate and redirected; the API reports the
    conflict explicitly. The invariant under test — one argument per participant
    per side — is the same.
    """
    first = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'pro', 'body': 'First submission.',
    })
    resp = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'pro', 'body': 'Second submission.',
    })
    assert first.status_code == 201
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'argument_already_submitted'
    assert Argument.query.filter_by(
        proposer_pseudonym=arg_part.pseudonym, featured_statement_id=fs.id, side='pro').count() == 1
    assert Argument.query.filter_by(
        featured_statement_id=fs.id, side='pro').one().body == 'First submission.'


def test_submit_inserts_into_side_state_order(auth_client, arg_conv, arg_part, fs, participant):
    """After submission the new argument ID appears in the participant's argument_order."""
    resp = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'pro', 'body': 'Ordering test.',
    })
    assert resp.status_code == 201
    arg = Argument.query.filter_by(
        proposer_pseudonym=arg_part.pseudonym, featured_statement_id=fs.id, side='pro').first()
    state = ArgumentSideState.query.filter_by(
        participant_id=participant.id, featured_statement_id=fs.id, side='pro').first()
    assert state is not None
    assert arg.id in state.argument_order


# DELETED: test_legacy_submit_url_redirects_to_featured_statement_route and
# test_legacy_skip_url_redirects_to_featured_statement_route. Both asserted a 307
# from an old Jinja URL (/c/<slug>/arguments/<fs>/submit, /c/<slug>/arguments/
# <fs>/<side>/skip) to a newer Jinja URL. Both source and target routes were
# deleted with the Jinja frontend, so there is no compatibility shim left to test
# and no /api/v1 counterpart.


def test_submit_blocked_on_inactive_conv(auth_client, app, participant, fs):
    c = Conversation(slug='closed-arg', polis_id='clo1234567',
                     title='Closed', active=False, access_policy='public',
                     phase_argument_mapping=True)
    db.session.add(c)
    db.session.flush()
    # Join the conversation so the block below can only come from `active=False`.
    db.session.add(Participation(participant_id=participant.id,
                                 conversation_id=c.id, pseudonym='closed-fox'))
    fs2 = FeaturedStatement(conversation_id=c.id, polis_statement_id=1,
                            confirmed_by_admin=True)
    db.session.add(fs2)
    db.session.commit()
    resp = auth_client.post(_arguments_path('closed-arg', fs2.id), json={
        'side': 'pro', 'body': 'Should be blocked.',
    })
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'conflict'
    assert Argument.query.filter_by(featured_statement_id=fs2.id).count() == 0


def test_banned_participant_cannot_submit_argument(auth_client, arg_conv, arg_part, fs, participant):
    db.session.add(ConversationBan(
        conversation_id=arg_conv.id,
        participant_id=participant.id,
        summary='spam',
    ))
    db.session.commit()
    resp = auth_client.post(_arguments_path('arg-conv', fs.id), json={
        'side': 'pro', 'body': 'Should be blocked.',
    })
    assert resp.status_code == 403
    assert resp.get_json()['error']['code'] == 'forbidden'
    assert Argument.query.filter_by(
        proposer_pseudonym=arg_part.pseudonym,
        featured_statement_id=fs.id,
    ).first() is None


def test_banned_participant_cannot_submit_statement_or_vote(auth_client, participant):
    conv = Conversation(
        slug='ban-write',
        polis_id='ban1234567',
        title='Ban Write',
        active=True,
        access_policy='public',
        phase_submission=True,
    )
    db.session.add(conv)
    db.session.flush()
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conv.id,
        pseudonym='ban-fox',
    ))
    db.session.add(ConversationBan(
        conversation_id=conv.id,
        participant_id=participant.id,
        summary='blocked',
    ))
    db.session.commit()

    stmt_resp = auth_client.post(
        '/api/v1/conversations/ban-write/statements',
        json={'text': 'Should be blocked.'},
        headers={'Idempotency-Key': 'ban-write-statement-1'},
    )
    vote_resp = auth_client.put(
        '/api/v1/conversations/ban-write/statements/1/vote',
        json={'choice': 'disagree'},
    )

    assert stmt_resp.status_code == 403
    assert stmt_resp.get_json()['error']['code'] == 'forbidden'
    assert vote_resp.status_code == 403
    assert vote_resp.get_json()['error']['code'] == 'forbidden'


# ── Skip ──────────────────────────────────────────────────────────────────────

def test_skip_pro_side(auth_client, arg_conv, arg_part, fs, participant):
    resp = auth_client.put(_skip_path('arg-conv', fs.id, 'pro'))
    assert resp.status_code == 200
    assert resp.get_json()['data']['status'] == 'skipped'
    state = ArgumentSideState.query.filter_by(
        participant_id=participant.id, featured_statement_id=fs.id, side='pro').first()
    assert state is not None
    assert state.skipped is True


def test_skip_invalid_side_rejected(auth_client, arg_conv, arg_part, fs, participant):
    resp = auth_client.put(_skip_path('arg-conv', fs.id, 'neutral'))
    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'validation_failed'
    assert ArgumentSideState.query.filter_by(
        participant_id=participant.id, featured_statement_id=fs.id).count() == 0


def test_skip_idempotent(auth_client, arg_conv, arg_part, fs, participant):
    first = auth_client.put(_skip_path('arg-conv', fs.id, 'pro'))
    replay = auth_client.put(_skip_path('arg-conv', fs.id, 'pro'))
    assert first.status_code == replay.status_code == 200
    assert ArgumentSideState.query.filter_by(
        participant_id=participant.id, featured_statement_id=fs.id, side='pro').count() == 1


def test_both_sides_offer_a_direct_skip_before_any_contribution(
        auth_client, arg_conv, arg_part, fs):
    """Ported from test_argument_tab_renders_direct_skip_controls.

    The template rendered exactly two `at-direct-skip` controls (one per side);
    the payload counterpart is `contribution.capabilities.skip` on both sides
    while the contribution is still pending, and it must drop away once the side
    is answered.
    """
    with patch('app._statement_text_map', return_value={}):
        card = auth_client.get(
            '/api/v1/conversations/arg-conv/arguments',
        ).get_json()['data']['featuredStatements'][0]
    assert [side['contribution']['status'] for side in card['sides'].values()] == [
        'pending', 'pending',
    ]
    assert all(side['contribution']['capabilities']['skip'] is True
               for side in card['sides'].values())

    assert auth_client.put(_skip_path('arg-conv', fs.id, 'pro')).status_code == 200
    with patch('app._statement_text_map', return_value={}):
        card = auth_client.get(
            '/api/v1/conversations/arg-conv/arguments',
        ).get_json()['data']['featuredStatements'][0]
    assert card['sides']['pro']['contribution']['capabilities']['skip'] is False
    assert card['sides']['con']['contribution']['capabilities']['skip'] is True


# COVERAGE GAP: the deleted assertion `'/help/arguments' in html` has no /api/v1
# counterpart — the argument-guidance link now lives only in the React shell
# (frontend/src/features/legacy/argument-mapping-panel.tsx) and is covered by the
# frontend tests, not by any API payload field.


def test_all_complete_state_requires_both_side_contributions(
        auth_client, arg_conv, arg_part, fs):
    """Ported from test_all_complete_state_requires_side_contribution_states.

    That test read conversation.html and asserted the JS gate consulted BOTH
    `proWrapper` and `conWrapper`. The server-side equivalent is that
    `contributionsComplete` / `progress.allDone` stay false until both sides are
    answered — asserted here against the real state machine rather than the
    template source.
    """
    def read():
        with patch('app._statement_text_map', return_value={}):
            return auth_client.get(
                '/api/v1/conversations/arg-conv/arguments',
            ).get_json()['data']

    data = read()
    assert data['featuredStatements'][0]['contributionsComplete'] is False
    assert data['progress']['allDone'] is False

    assert auth_client.put(_skip_path('arg-conv', fs.id, 'pro')).status_code == 200
    data = read()
    assert data['featuredStatements'][0]['contributionsComplete'] is False
    assert data['progress']['allDone'] is False

    assert auth_client.put(_skip_path('arg-conv', fs.id, 'con')).status_code == 200
    data = read()
    assert data['featuredStatements'][0]['contributionsComplete'] is True
    assert data['progress']['allDone'] is True


# DELETED: test_all_done_interlude_copy_is_not_reversibility_copy. It asserted two
# literal English strings in the rendered Jinja page ("Nice work. Review the
# importance choices below..." present, "Nothing is locked in" absent). The
# argument-mapping payload carries no copy at all — only structural flags such as
# progress.allDone, which test_all_complete_state_requires_both_side_contributions
# now covers. Interlude wording is a frontend concern.


# ── Importance voting (prioritization) ────────────────────────────────────────

def _pass_gate(client, slug, fs_id):
    """Helper: skip both sides to pass the contribution gate."""
    assert client.put(_skip_path(slug, fs_id, 'pro')).status_code == 200
    assert client.put(_skip_path(slug, fs_id, 'con')).status_code == 200


def test_vote_blocked_before_gate(auth_client, arg_conv, arg_part, fs, participant, app):
    args = _make_args(fs.id, None, 'pro', 3)
    resp = auth_client.put(_priority_path('arg-conv', args[0].id),
                           json={'selected': True})
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'contribution_gate_closed'
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=args[0].id).first() is None


def test_vote_blocked_below_k_threshold(auth_client, arg_conv, arg_part, fs,
                                        participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 1)
    resp = auth_client.put(_priority_path('arg-conv', args[0].id),
                           json={'selected': True})
    # Only 1 pro arg, K=2 — enforce the same minimum-volume gate in the API
    # that the UI advertises, so direct requests cannot bypass it.
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'prioritization_unavailable'
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=args[0].id).first() is None


def test_vote_cast_and_recorded(auth_client, arg_conv, arg_part, fs,
                                participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 3)
    resp = auth_client.put(_priority_path('arg-conv', args[0].id),
                           json={'selected': True})
    assert resp.status_code == 200
    assert resp.get_json()['data']['selectedCount'] == 1
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=args[0].id).first()


def test_vote_k_cap_enforced(auth_client, arg_conv, arg_part, fs,
                             participant, app):
    """Selecting K+1 arguments on the same side returns 409 and stores only K."""
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 5)
    auth_client.put(_priority_path('arg-conv', args[0].id), json={'selected': True})
    auth_client.put(_priority_path('arg-conv', args[1].id), json={'selected': True})
    resp = auth_client.put(_priority_path('arg-conv', args[2].id),
                           json={'selected': True})
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'priority_budget_exceeded'
    assert ArgumentVote.query.filter_by(participant_id=participant.id).count() == 2
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=args[2].id).first() is None


def test_cap_exceeded_returns_machine_readable_error(auth_client, arg_conv,
                                                     arg_part, fs, app):
    """Ported from test_p1_2_cap_exceeded_ajax_returns_json_reason.

    The Jinja route answered AJAX callers with {'ok': False, 'reason': 'cap'};
    /api/v1 answers every caller with the standard error envelope. The client
    needs a code it can branch on, so assert the envelope shape, not just status.
    """
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 5)
    auth_client.put(_priority_path('arg-conv', args[0].id), json={'selected': True})
    auth_client.put(_priority_path('arg-conv', args[1].id), json={'selected': True})
    resp = auth_client.put(_priority_path('arg-conv', args[2].id),
                           json={'selected': True})
    assert resp.status_code == 409
    assert resp.is_json
    error = resp.get_json()['error']
    assert error['code'] == 'priority_budget_exceeded'
    assert error['message']


def test_duplicate_submit_answers_with_json_not_a_redirect(auth_client, arg_conv,
                                                           arg_part, fs):
    """Ported from test_p1_1_duplicate_ajax_submit_returns_json.

    The Jinja route redirected on the duplicate branch even for AJAX callers, so
    the fetch handler got HTML and hung. /api/v1 must answer the replay with a
    200 JSON body identical to the original 201 payload.
    """
    first = auth_client.post(_arguments_path('arg-conv', fs.id),
                             json={'side': 'pro', 'body': 'First.'})
    replay = auth_client.post(_arguments_path('arg-conv', fs.id),
                              json={'side': 'pro', 'body': 'First.'})
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.is_json
    assert replay.get_json() == first.get_json()
    assert Argument.query.filter_by(
        proposer_pseudonym=arg_part.pseudonym,
        featured_statement_id=fs.id, side='pro').count() == 1


def test_vote_own_argument_allowed(auth_client, arg_conv, arg_part, fs,
                                   participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    _make_args(fs.id, None, 'pro', 2)
    own = Argument(featured_statement_id=fs.id, proposer_pseudonym=arg_part.pseudonym,
                   body='My argument.', side='pro')
    db.session.add(own)
    db.session.commit()
    resp = auth_client.put(_priority_path('arg-conv', own.id),
                           json={'selected': True})
    assert resp.status_code == 200
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=own.id).first()


def test_unvote_removes_vote(auth_client, arg_conv, arg_part, fs,
                             participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 3)
    assert auth_client.put(_priority_path('arg-conv', args[0].id),
                           json={'selected': True}).status_code == 200
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=args[0].id).first()
    resp = auth_client.put(_priority_path('arg-conv', args[0].id),
                           json={'selected': False})
    assert resp.status_code == 200
    assert resp.get_json()['data']['selectedCount'] == 0
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=args[0].id).first() is None


# ── Moderator delete ──────────────────────────────────────────────────────────

def test_moderator_can_delete_argument(admin_client, arg_conv, arg_part, fs,
                                       admin_participant, app):
    db.session.add(Participation(participant_id=admin_participant.id,
                                 conversation_id=arg_conv.id, pseudonym='admin-fox'))
    arg = Argument(featured_statement_id=fs.id, proposer_pseudonym=None,
                   body='To be deleted.', side='pro')
    db.session.add(arg)
    db.session.commit()
    resp = admin_client.delete(_featured_argument_path(arg_conv.id, arg.id))
    assert resp.status_code == 200
    assert resp.get_json()['data']['deleted'] is True
    assert db.session.get(Argument, arg.id) is None
    assert AuditEvent.query.filter_by(operation='argument.delete').count() == 1


def test_participant_cannot_delete_argument(auth_client, arg_conv, arg_part, fs, app):
    arg = Argument(featured_statement_id=fs.id, proposer_pseudonym=None,
                   body='Should survive.', side='pro')
    db.session.add(arg)
    db.session.commit()
    resp = auth_client.delete(_featured_argument_path(arg_conv.id, arg.id))
    assert resp.status_code == 403
    assert resp.get_json()['error']['code'] == 'forbidden'
    assert db.session.get(Argument, arg.id) is not None
    assert AuditEvent.query.filter_by(operation='argument.delete').count() == 0


def test_admin_can_hide_and_unhide_argument_from_featured_workspace(admin_client,
                                                                    arg_conv, fs):
    arg = Argument(featured_statement_id=fs.id, proposer_pseudonym=None,
                   body='Needs review.', side='pro')
    db.session.add(arg)
    db.session.commit()

    hide_resp = admin_client.put(
        _featured_argument_path(arg_conv.id, arg.id), json={'hidden': True},
    )
    assert hide_resp.status_code == 200
    assert hide_resp.get_json()['data']['hidden'] is True
    db.session.refresh(arg)
    assert arg.hidden is True

    unhide_resp = admin_client.put(
        _featured_argument_path(arg_conv.id, arg.id), json={'hidden': False},
    )
    assert unhide_resp.status_code == 200
    assert unhide_resp.get_json()['data']['hidden'] is False
    db.session.refresh(arg)
    assert arg.hidden is False


# ── Argument hide / unhide ────────────────────────────────────────────────────

def _make_visible_arg(fs_id, side='pro'):
    arg = Argument(featured_statement_id=fs_id, proposer_pseudonym=None,
                   body='Visible argument.', side=side)
    db.session.add(arg)
    db.session.commit()
    return arg


def test_moderator_can_hide_argument(admin_client, arg_conv, arg_part, fs,
                                     admin_participant, app):
    db.session.add(Participation(participant_id=admin_participant.id,
                                 conversation_id=arg_conv.id, pseudonym='admin-fox'))
    arg = _make_visible_arg(fs.id)
    resp = admin_client.put(_featured_argument_path(arg_conv.id, arg.id),
                            json={'hidden': True})
    assert resp.status_code == 200
    assert resp.get_json()['data']['changed'] is True
    db.session.refresh(arg)
    assert arg.hidden is True
    assert AuditEvent.query.filter_by(operation='argument.moderate').count() == 1

    # Re-issuing the same state is a no-op: no second audit row.
    replay = admin_client.put(_featured_argument_path(arg_conv.id, arg.id),
                              json={'hidden': True})
    assert replay.status_code == 200
    assert replay.get_json()['data']['changed'] is False
    assert AuditEvent.query.filter_by(operation='argument.moderate').count() == 1


def test_moderator_can_unhide_argument(admin_client, arg_conv, arg_part, fs,
                                       admin_participant, app):
    db.session.add(Participation(participant_id=admin_participant.id,
                                 conversation_id=arg_conv.id, pseudonym='admin-fox'))
    arg = Argument(featured_statement_id=fs.id, proposer_pseudonym=None,
                   body='Was hidden.', side='pro', hidden=True)
    db.session.add(arg)
    db.session.commit()
    resp = admin_client.put(_featured_argument_path(arg_conv.id, arg.id),
                            json={'hidden': False})
    assert resp.status_code == 200
    db.session.refresh(arg)
    assert arg.hidden is False


def test_participant_cannot_hide_argument(auth_client, arg_conv, arg_part, fs, app):
    arg = _make_visible_arg(fs.id)
    resp = auth_client.put(_featured_argument_path(arg_conv.id, arg.id),
                           json={'hidden': True})
    assert resp.status_code == 403
    assert resp.get_json()['error']['code'] == 'forbidden'
    db.session.refresh(arg)
    assert arg.hidden is False


# ── Content flags ─────────────────────────────────────────────────────────────

def _flags_path(slug='arg-conv'):
    return f'/api/v1/conversations/{slug}/flags'


def test_participant_can_flag_argument(auth_client, arg_conv, arg_part, fs, participant):
    arg = _make_visible_arg(fs.id)
    resp = auth_client.post(_flags_path(), json={
        'contentType': 'argument', 'targetId': arg.id,
        'category': 'personal_attack', 'detail': '<b>bad</b>',
    })
    assert resp.status_code == 201
    assert resp.is_json
    assert resp.get_json()['data']['created'] is True
    flag = ContentFlag.query.filter_by(
        conversation_id=arg_conv.id,
        participant_id=participant.id,
        content_type='argument',
        argument_id=arg.id,
    ).first()
    assert flag is not None
    assert flag.category == 'personal_attack'
    assert flag.detail == 'bad'


# DELETED: test_participant_flag_argument_via_fetch_returns_json and
# test_participant_flag_statement_via_fetch_returns_json. Both asserted the Jinja
# route's content negotiation — that an `X-Requested-With: fetch` header produced
# {'ok': True} JSON instead of a 302 redirect. /api/v1 is JSON-only with a single
# response shape, so there is no negotiation left to test; the JSON envelope is
# asserted in test_participant_can_flag_argument and test_participant_can_flag_statement.


def test_participant_flag_argument_requires_detail_for_other(
    auth_client, arg_conv, arg_part, fs, participant,
):
    arg = _make_visible_arg(fs.id)

    resp = auth_client.post(_flags_path(), json={
        'contentType': 'argument', 'targetId': arg.id,
        'category': 'other', 'detail': '<b></b>',
    })

    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'validation_failed'
    assert ContentFlag.query.filter_by(
        conversation_id=arg_conv.id,
        participant_id=participant.id,
        content_type='argument',
        argument_id=arg.id,
    ).count() == 0


def test_participant_argument_flag_dedupes_open_flags(auth_client, arg_conv,
                                                      arg_part, fs, participant):
    arg = _make_visible_arg(fs.id)
    payload = {
        'contentType': 'argument', 'targetId': arg.id, 'category': 'off_topic',
    }
    first = auth_client.post(_flags_path(), json=payload)
    replay = auth_client.post(_flags_path(), json=payload)
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.get_json()['data']['created'] is False
    assert ContentFlag.query.filter_by(
        conversation_id=arg_conv.id,
        participant_id=participant.id,
        content_type='argument',
        argument_id=arg.id,
        category='off_topic',
    ).count() == 1


def test_participant_can_flag_statement(auth_client, arg_conv, arg_part, participant):
    with patch('app._statement_text_map', return_value={42: 'Statement text'}):
        resp = auth_client.post(_flags_path(), json={
            'contentType': 'statement', 'targetId': 42,
            'category': 'privacy', 'detail': 'Personal details',
        })
    assert resp.status_code == 201
    assert resp.is_json
    flag = ContentFlag.query.filter_by(
        conversation_id=arg_conv.id,
        participant_id=participant.id,
        content_type='statement',
        statement_tid=42,
    ).first()
    assert flag is not None
    assert flag.category == 'privacy'


def test_participant_can_flag_seed_statement(auth_client, arg_conv, arg_part, participant):
    """A seed (organizer-authored) statement must be just as flaggable as any other —
    previously an unconditional abort(400) here meant flagging any seed-derived
    featured statement (the common case) failed with Bad Request."""
    seed_stmt = {'tid': 42, 'txt': 'Seed statement text', 'text': 'Seed statement text',
                 'is_seed': True}
    with patch('app.PolisParticipantClient.get_statements',
               return_value=([], [seed_stmt], [])):
        resp = auth_client.post(_flags_path(), json={
            'contentType': 'statement', 'targetId': 42,
            'category': 'privacy', 'detail': 'Personal details',
        })
    assert resp.status_code == 201
    flag = ContentFlag.query.filter_by(
        conversation_id=arg_conv.id,
        participant_id=participant.id,
        content_type='statement',
        statement_tid=42,
    ).first()
    assert flag is not None


def test_participant_flag_statement_requires_detail_for_other(
    auth_client, arg_conv, arg_part, participant,
):
    with patch('app._statement_text_map', return_value={42: 'Statement text'}):
        resp = auth_client.post(_flags_path(), json={
            'contentType': 'statement', 'targetId': 42,
            'category': 'other', 'detail': '   ',
        })

    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'validation_failed'
    assert ContentFlag.query.filter_by(
        conversation_id=arg_conv.id,
        participant_id=participant.id,
        content_type='statement',
        statement_tid=42,
    ).count() == 0


def test_participant_can_flag_other_with_explanation(
    auth_client, arg_conv, arg_part, participant,
):
    with patch('app._statement_text_map', return_value={42: 'Statement text'}):
        resp = auth_client.post(_flags_path(), json={
            'contentType': 'statement', 'targetId': 42,
            'category': 'other', 'detail': 'This needs contextual review.',
        })

    assert resp.status_code == 201
    flag = ContentFlag.query.filter_by(
        conversation_id=arg_conv.id,
        participant_id=participant.id,
        content_type='statement',
        statement_tid=42,
    ).one()
    assert flag.detail == 'This needs contextual review.'


def test_hide_argument_wrong_conversation_returns_404(admin_client, arg_conv,
                                                      admin_participant, app):
    """Moderator cannot hide an arg belonging to a different conversation.

    The 404 must come from the cross-conversation guard in
    ``_require_admin_featured_argument``, not from a missing route: the same
    moderator hiding the same argument under its OWN conversation id succeeds.
    """
    other_conv = Conversation(slug='other-conv2', polis_id='oth9999999',
                              title='Other', active=True, access_policy='public',
                              phase_argument_mapping=True)
    db.session.add(other_conv)
    db.session.flush()
    other_fs = FeaturedStatement(conversation_id=other_conv.id,
                                 polis_statement_id=88, confirmed_by_admin=True)
    db.session.add(other_fs)
    db.session.flush()
    arg = Argument(featured_statement_id=other_fs.id, proposer_pseudonym=None,
                   body='Belongs to other conv.', side='pro')
    db.session.add(arg)
    db.session.commit()

    resp = admin_client.put(_featured_argument_path(arg_conv.id, arg.id),
                            json={'hidden': True})
    assert resp.status_code == 404
    assert resp.get_json()['error']['code'] == 'argument_not_found'
    db.session.refresh(arg)
    assert arg.hidden is False
    assert AuditEvent.query.filter_by(operation='argument.moderate').count() == 0

    # Same request under the argument's own conversation id is accepted, which
    # proves the 404 above came from the guard and not from routing.
    allowed = admin_client.put(_featured_argument_path(other_conv.id, arg.id),
                               json={'hidden': True})
    assert allowed.status_code == 200
    db.session.refresh(arg)
    assert arg.hidden is True


def test_delete_argument_wrong_conversation_returns_404(admin_client, arg_conv,
                                                        admin_participant, app):
    """The same cross-conversation guard protects the destructive verb."""
    other_conv = Conversation(slug='other-conv3', polis_id='oth8888888',
                              title='Other', active=True, access_policy='public',
                              phase_argument_mapping=True)
    db.session.add(other_conv)
    db.session.flush()
    other_fs = FeaturedStatement(conversation_id=other_conv.id,
                                 polis_statement_id=77, confirmed_by_admin=True)
    db.session.add(other_fs)
    db.session.flush()
    arg = Argument(featured_statement_id=other_fs.id, proposer_pseudonym=None,
                   body='Belongs to other conv.', side='pro')
    db.session.add(arg)
    db.session.commit()

    resp = admin_client.delete(_featured_argument_path(arg_conv.id, arg.id))
    assert resp.status_code == 404
    assert resp.get_json()['error']['code'] == 'argument_not_found'
    assert db.session.get(Argument, arg.id) is not None

    allowed = admin_client.delete(_featured_argument_path(other_conv.id, arg.id))
    assert allowed.status_code == 200
    assert db.session.get(Argument, arg.id) is None


def test_vote_on_hidden_argument_blocked(auth_client, arg_conv, arg_part, fs,
                                         participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    _make_args(fs.id, None, 'pro', 3)
    hidden_arg = Argument(featured_statement_id=fs.id, proposer_pseudonym=None,
                          body='Hidden.', side='pro', hidden=True)
    db.session.add(hidden_arg)
    db.session.commit()
    resp = auth_client.put(_priority_path('arg-conv', hidden_arg.id),
                           json={'selected': True})
    assert resp.status_code == 404
    assert resp.get_json()['error']['code'] == 'argument_unavailable'
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=hidden_arg.id).first() is None


def test_unvote_wrong_conversation_returns_404(auth_client, arg_conv, arg_part,
                                               fs, participant, app):
    """Prioritization must verify the argument belongs to the conversation in the URL.

    The 404 must come from the conversation-scoped lookup in
    ``set_argument_priority``, not from a missing route: the vote on the other
    conversation's argument survives the mismatched request, and the same
    unselect under the correct slug removes it.
    """
    other_conv = Conversation(slug='other-conv', polis_id='oth1234567',
                              title='Other', active=True, access_policy='public',
                              phase_argument_mapping=True)
    db.session.add(other_conv)
    db.session.commit()
    db.session.add(Participation(participant_id=participant.id,
                                 conversation_id=other_conv.id, pseudonym='test-wolf'))
    other_fs = FeaturedStatement(conversation_id=other_conv.id,
                                 polis_statement_id=99, confirmed_by_admin=True)
    db.session.add(other_fs)
    db.session.commit()
    arg = Argument(featured_statement_id=other_fs.id, proposer_pseudonym=None,
                   body='Other conv arg.', side='pro')
    db.session.add(arg)
    db.session.commit()
    db.session.add(ArgumentVote(participant_id=participant.id, argument_id=arg.id))
    db.session.commit()

    # Try to unselect an argument from other_conv via the arg-conv URL.
    resp = auth_client.put(_priority_path('arg-conv', arg.id),
                           json={'selected': False})
    assert resp.status_code == 404
    assert resp.get_json()['error']['code'] == 'not_found'
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=arg.id).first() is not None

    # The same unselect under the argument's own slug is accepted, which proves
    # the 404 above came from the ownership guard and not from routing.
    allowed = auth_client.put(_priority_path('other-conv', arg.id),
                              json={'selected': False})
    assert allowed.status_code == 200
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=arg.id).first() is None


# ── Admin featured statements ──────────────────────────────────────────────────

def _admin_featured_path(conv_id):
    return f'/api/v1/admin/conversations/{conv_id}/featured-statements'


def test_admin_featured_workspace_accessible(admin_client, arg_conv, fs,
                                             admin_participant):
    """Replaces test_admin_featured_page_accessible.

    That test GET'd /admin/conversations/<id>/featured, a canonical SPA path that
    returns the React shell with a 200 before route dispatch — so it asserted
    nothing. This asserts the moderator actually gets the workspace payload.
    """
    with patch('app._statement_text_map', return_value={42: 'Featured text'}):
        resp = admin_client.get(_admin_featured_path(arg_conv.id))

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['conversation'] == {
        'id': arg_conv.id, 'slug': 'arg-conv', 'title': 'Arg Conv',
    }
    assert [row['featuredId'] for row in data['selected']] == [fs.id]
    assert data['selected'][0]['statementId'] == 42
    assert data['capabilities'] == {'manage': True}
    assert data['phase']['argumentMappingActive'] is True


def test_admin_featured_workspace_shows_statement_provenance(admin_client, arg_conv,
                                                             fs, app):
    from app import record_statement_provenance
    record_statement_provenance(arg_conv.id, fs.polis_statement_id, 7,
                                parent_text='old statement', new_text='new statement')

    with patch('app._statement_text_map', return_value={42: 'Featured text'}):
        resp = admin_client.get(_admin_featured_path(arg_conv.id))

    assert resp.status_code == 200
    selection = resp.get_json()['data']['selected'][0]
    assert selection['statementId'] == fs.polis_statement_id
    assert selection['provenance']['derivedFromId'] == 7


def test_admin_featured_add_by_tid(admin_client, arg_conv, admin_participant):
    with patch('app._statement_text_map', return_value={99: 'Candidate text'}):
        resp = admin_client.put(
            f'{_admin_featured_path(arg_conv.id)}/99', json={'source': 'manual'},
        )
    assert resp.status_code == 200
    assert resp.get_json()['data']['changed'] is True
    assert FeaturedStatement.query.filter_by(
        conversation_id=arg_conv.id, polis_statement_id=99).first()
    assert AuditEvent.query.filter_by(operation='featured.select').count() == 1


def test_admin_featured_add_deduplicates(admin_client, arg_conv, admin_participant):
    with patch('app._statement_text_map', return_value={55: 'Candidate text'}):
        first = admin_client.put(
            f'{_admin_featured_path(arg_conv.id)}/55', json={'source': 'manual'},
        )
        replay = admin_client.put(
            f'{_admin_featured_path(arg_conv.id)}/55', json={'source': 'manual'},
        )
    assert first.get_json()['data']['changed'] is True
    assert replay.status_code == 200
    assert replay.get_json()['data']['changed'] is False
    assert FeaturedStatement.query.filter_by(
        conversation_id=arg_conv.id, polis_statement_id=55).count() == 1


def test_admin_featured_remove_blocked_for_last_selection(admin_client, arg_conv,
                                                          admin_participant, fs):
    # arg_conv has phase_argument_mapping=True and fs is the only featured statement —
    # the guard should block removal and leave the record intact.
    resp = admin_client.delete(
        f'/api/v1/admin/conversations/{arg_conv.id}/featured-selections/{fs.id}',
    )
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'last_featured_statement_protected'
    assert db.session.get(FeaturedStatement, fs.id) is not None


def test_admin_featured_remove_allowed_when_multiple(app, admin_client, arg_conv,
                                                     admin_participant, fs):
    # Add a second featured statement so removing the first is allowed.
    fs2 = FeaturedStatement(
        conversation_id=arg_conv.id,
        polis_statement_id=99,
        confirmed_by_admin=True,
    )
    db.session.add(fs2)
    db.session.commit()
    resp = admin_client.delete(
        f'/api/v1/admin/conversations/{arg_conv.id}/featured-selections/{fs.id}',
    )
    assert resp.status_code == 200
    assert resp.get_json()['data']['removed'] is True
    assert db.session.get(FeaturedStatement, fs.id) is None
    assert AuditEvent.query.filter_by(operation='featured.remove').count() == 1


def test_non_admin_cannot_access_featured_admin(auth_client, arg_conv):
    resp = auth_client.get(_admin_featured_path(arg_conv.id))
    assert resp.status_code == 403
    assert resp.get_json()['error']['code'] == 'forbidden'
