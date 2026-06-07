"""Tests for the argument mapping layer: submit, skip, vote, admin featured."""
import pytest

from db import (Argument, ArgumentSideState, ArgumentVote, Conversation,
                FeaturedStatement, Participant, Participation, db)
from tests.conftest import login


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


def _make_args(fs_id, proposer_id, side, n):
    """Insert n arguments for a given proposer/side combo (uses different proposers for n>1)."""
    args = []
    for i in range(n):
        # Use distinct proposer IDs so uniqueness constraint is satisfied.
        a = Argument(
            featured_statement_id=fs_id,
            proposer_id=None,   # seeded — exempt from unique constraint
            body=f'Argument {i}',
            side=side,
        )
        db.session.add(a)
    db.session.commit()
    return Argument.query.filter_by(featured_statement_id=fs_id, side=side).all()


# ── Argument submission ────────────────────────────────────────────────────────

def test_submit_pro_argument(auth_client, arg_conv, arg_part, fs, participant):
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit', data={
        'side': 'pro', 'body': 'This is a pro argument.',
    })
    assert resp.status_code == 302
    arg = Argument.query.filter_by(
        proposer_id=participant.id, featured_statement_id=fs.id, side='pro').first()
    assert arg is not None
    assert arg.body == 'This is a pro argument.'


def test_submit_con_argument(auth_client, arg_conv, arg_part, fs, participant):
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit', data={
        'side': 'con', 'body': 'This is a con argument.',
    })
    assert resp.status_code == 302
    assert Argument.query.filter_by(
        proposer_id=participant.id, featured_statement_id=fs.id, side='con').first()


def test_submit_invalid_side_rejected(auth_client, arg_conv, arg_part, fs):
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit', data={
        'side': 'neutral', 'body': 'Text.',
    })
    assert resp.status_code == 400


def test_submit_empty_body_rejected(auth_client, arg_conv, arg_part, fs):
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit', data={
        'side': 'pro', 'body': '',
    })
    assert resp.status_code == 400


def test_submit_body_too_long_rejected(auth_client, arg_conv, arg_part, fs):
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit', data={
        'side': 'pro', 'body': 'x' * 281,
    })
    assert resp.status_code == 400


def test_submit_duplicate_silently_redirects(auth_client, arg_conv, arg_part, fs, participant):
    auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit', data={
        'side': 'pro', 'body': 'First submission.',
    })
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit', data={
        'side': 'pro', 'body': 'Second submission.',
    })
    assert resp.status_code == 302
    assert Argument.query.filter_by(
        proposer_id=participant.id, featured_statement_id=fs.id, side='pro').count() == 1


def test_submit_inserts_into_side_state_order(auth_client, arg_conv, arg_part, fs, participant):
    """After submission the new argument ID appears in the participant's argument_order."""
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit', data={
        'side': 'pro', 'body': 'Ordering test.',
    })
    assert resp.status_code == 302
    arg = Argument.query.filter_by(
        proposer_id=participant.id, featured_statement_id=fs.id, side='pro').first()
    state = ArgumentSideState.query.filter_by(
        participant_id=participant.id, featured_statement_id=fs.id, side='pro').first()
    assert state is not None
    assert arg.id in state.argument_order


def test_submit_blocked_on_inactive_conv(auth_client, app, participant, fs):
    c = Conversation(slug='closed-arg', polis_id='clo1234567',
                     title='Closed', active=False, access_policy='public',
                     phase_argument_mapping=True)
    db.session.add(c)
    db.session.commit()
    fs2 = FeaturedStatement(conversation_id=c.id, polis_statement_id=1,
                            confirmed_by_admin=True)
    db.session.add(fs2)
    db.session.commit()
    resp = auth_client.post(f'/c/closed-arg/arguments/{fs2.id}/submit', data={
        'side': 'pro', 'body': 'Should be blocked.',
    })
    assert resp.status_code == 403


# ── Skip ──────────────────────────────────────────────────────────────────────

def test_skip_pro_side(auth_client, arg_conv, arg_part, fs, participant):
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/pro/skip')
    assert resp.status_code == 302
    state = ArgumentSideState.query.filter_by(
        participant_id=participant.id, featured_statement_id=fs.id, side='pro').first()
    assert state is not None
    assert state.skipped is True


def test_skip_invalid_side_rejected(auth_client, arg_conv, arg_part, fs):
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/neutral/skip')
    assert resp.status_code == 400


def test_skip_idempotent(auth_client, arg_conv, arg_part, fs, participant):
    auth_client.post(f'/c/arg-conv/arguments/{fs.id}/pro/skip')
    auth_client.post(f'/c/arg-conv/arguments/{fs.id}/pro/skip')
    assert ArgumentSideState.query.filter_by(
        participant_id=participant.id, featured_statement_id=fs.id, side='pro').count() == 1


# ── Importance voting ─────────────────────────────────────────────────────────

def _pass_gate(client, slug, fs_id):
    """Helper: skip both sides to pass the contribution gate."""
    client.post(f'/c/{slug}/arguments/{fs_id}/pro/skip')
    client.post(f'/c/{slug}/arguments/{fs_id}/con/skip')


def test_vote_blocked_before_gate(auth_client, arg_conv, arg_part, fs, app):
    args = _make_args(fs.id, None, 'pro', 3)
    resp = auth_client.post(f'/c/arg-conv/arguments/{args[0].id}/vote')
    assert resp.status_code == 403


def test_vote_blocked_below_k_threshold(auth_client, arg_conv, arg_part, fs,
                                        participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 1)
    resp = auth_client.post(f'/c/arg-conv/arguments/{args[0].id}/vote')
    # Only 1 pro arg, K=2 — threshold not met, but gate passes; vote button
    # should not be shown in UI. Route doesn't enforce threshold, only K-cap.
    assert resp.status_code == 302


def test_vote_cast_and_recorded(auth_client, arg_conv, arg_part, fs,
                                participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 3)
    resp = auth_client.post(f'/c/arg-conv/arguments/{args[0].id}/vote')
    assert resp.status_code == 302
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=args[0].id).first()


def test_vote_k_cap_enforced(auth_client, arg_conv, arg_part, fs,
                             participant, app):
    """Casting K+1 votes on the same side returns 409."""
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 5)
    auth_client.post(f'/c/arg-conv/arguments/{args[0].id}/vote')
    auth_client.post(f'/c/arg-conv/arguments/{args[1].id}/vote')
    resp = auth_client.post(f'/c/arg-conv/arguments/{args[2].id}/vote')
    assert resp.status_code == 409


def test_vote_own_argument_blocked(auth_client, arg_conv, arg_part, fs,
                                   participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    own = Argument(featured_statement_id=fs.id, proposer_id=participant.id,
                   body='My argument.', side='pro')
    db.session.add(own)
    db.session.commit()
    resp = auth_client.post(f'/c/arg-conv/arguments/{own.id}/vote')
    assert resp.status_code == 403


def test_unvote_removes_vote(auth_client, arg_conv, arg_part, fs,
                             participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 3)
    auth_client.post(f'/c/arg-conv/arguments/{args[0].id}/vote')
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=args[0].id).first()
    auth_client.post(f'/c/arg-conv/arguments/{args[0].id}/unvote')
    assert ArgumentVote.query.filter_by(
        participant_id=participant.id, argument_id=args[0].id).first() is None


# ── P1 bug reproductions ──────────────────────────────────────────────────────

AJAX = {'X-Requested-With': 'fetch'}


def test_p1_1_duplicate_ajax_submit_returns_json(auth_client, arg_conv, arg_part, fs):
    """P1-1: Second AJAX submit on the same side must return JSON, not a redirect.

    First call succeeds. Second call hits the duplicate-check branch (line 861)
    which currently returns redirect() unconditionally — the AJAX header is never
    checked. Fetch follows the redirect, r.ok is true but r.json() throws, the
    .catch re-enables submitBtn and leaves the wrapper stuck in composing.
    """
    auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit',
                     data={'side': 'pro', 'body': 'First.'}, headers=AJAX)
    resp = auth_client.post(f'/c/arg-conv/arguments/{fs.id}/submit',
                            data={'side': 'pro', 'body': 'Duplicate.'}, headers=AJAX)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None, "Expected JSON response, got redirect/HTML"
    assert data.get('ok') is True


def test_p1_2_cap_exceeded_ajax_returns_json_reason(auth_client, arg_conv,
                                                     arg_part, fs, app):
    """P1-2: When the K-cap is exceeded via AJAX the server returns the error JSON,
    but the JS has no code to surface `reason` to the user — the optimistic
    update silently reverts.

    This test confirms the server side works (returns {'ok': False, 'reason': 'cap'}).
    The missing feedback is in the JS wireCard handler (no UI response to reason).
    """
    _pass_gate(auth_client, 'arg-conv', fs.id)
    args = _make_args(fs.id, None, 'pro', 5)
    auth_client.post(f'/c/arg-conv/arguments/{args[0].id}/vote', headers=AJAX)
    auth_client.post(f'/c/arg-conv/arguments/{args[1].id}/vote', headers=AJAX)
    resp = auth_client.post(f'/c/arg-conv/arguments/{args[2].id}/vote', headers=AJAX)
    assert resp.status_code == 409
    data = resp.get_json()
    assert data == {'ok': False, 'reason': 'cap'}
    # NOTE: the JS wireCard handler checks only r.ok and reverts the optimistic
    # update, but never reads data.reason or shows any message to the user.


# ── Moderator delete ──────────────────────────────────────────────────────────

def test_moderator_can_delete_argument(admin_client, arg_conv, arg_part, fs,
                                       admin_participant, app):
    db.session.add(Participation(participant_id=admin_participant.id,
                                 conversation_id=arg_conv.id, pseudonym='admin-fox'))
    arg = Argument(featured_statement_id=fs.id, proposer_id=None,
                   body='To be deleted.', side='pro')
    db.session.add(arg)
    db.session.commit()
    resp = admin_client.post(
        f'/admin/conversations/{arg_conv.id}/arguments/{arg.id}/delete')
    assert resp.status_code == 302
    assert db.session.get(Argument, arg.id) is None


def test_participant_cannot_delete_argument(auth_client, arg_conv, arg_part, fs, app):
    arg = Argument(featured_statement_id=fs.id, proposer_id=None,
                   body='Should survive.', side='pro')
    db.session.add(arg)
    db.session.commit()
    resp = auth_client.post(
        f'/admin/conversations/{arg_conv.id}/arguments/{arg.id}/delete')
    assert resp.status_code == 403
    assert db.session.get(Argument, arg.id) is not None


# ── Argument hide / unhide ────────────────────────────────────────────────────

def _make_visible_arg(fs_id, side='pro'):
    arg = Argument(featured_statement_id=fs_id, proposer_id=None,
                   body='Visible argument.', side=side)
    db.session.add(arg)
    db.session.commit()
    return arg


def test_moderator_can_hide_argument(admin_client, arg_conv, arg_part, fs,
                                     admin_participant, app):
    db.session.add(Participation(participant_id=admin_participant.id,
                                 conversation_id=arg_conv.id, pseudonym='admin-fox'))
    arg = _make_visible_arg(fs.id)
    resp = admin_client.post(f'/c/arg-conv/arguments/{arg.id}/hide')
    assert resp.status_code == 302
    db.session.refresh(arg)
    assert arg.hidden is True


def test_moderator_can_unhide_argument(admin_client, arg_conv, arg_part, fs,
                                       admin_participant, app):
    db.session.add(Participation(participant_id=admin_participant.id,
                                 conversation_id=arg_conv.id, pseudonym='admin-fox'))
    arg = Argument(featured_statement_id=fs.id, proposer_id=None,
                   body='Was hidden.', side='pro', hidden=True)
    db.session.add(arg)
    db.session.commit()
    resp = admin_client.post(f'/c/arg-conv/arguments/{arg.id}/unhide')
    assert resp.status_code == 302
    db.session.refresh(arg)
    assert arg.hidden is False


def test_participant_cannot_hide_argument(auth_client, arg_conv, arg_part, fs, app):
    arg = _make_visible_arg(fs.id)
    resp = auth_client.post(f'/c/arg-conv/arguments/{arg.id}/hide')
    assert resp.status_code == 403
    db.session.refresh(arg)
    assert arg.hidden is False


def test_hide_argument_wrong_conversation_returns_404(admin_client, arg_conv,
                                                      admin_participant, app):
    """Moderator cannot hide an arg belonging to a different conversation via slug mismatch."""
    other_conv = Conversation(slug='other-conv2', polis_id='oth9999999',
                              title='Other', active=True, access_policy='public',
                              phase_argument_mapping=True)
    db.session.add(other_conv)
    db.session.flush()
    other_fs = FeaturedStatement(conversation_id=other_conv.id,
                                 polis_statement_id=88, confirmed_by_admin=True)
    db.session.add(other_fs)
    db.session.flush()
    arg = Argument(featured_statement_id=other_fs.id, proposer_id=None,
                   body='Belongs to other conv.', side='pro')
    db.session.add(arg)
    db.session.commit()
    resp = admin_client.post(f'/c/arg-conv/arguments/{arg.id}/hide')
    assert resp.status_code == 404
    db.session.refresh(arg)
    assert arg.hidden is False


def test_vote_on_hidden_argument_blocked(auth_client, arg_conv, arg_part, fs,
                                         participant, app):
    _pass_gate(auth_client, 'arg-conv', fs.id)
    _make_args(fs.id, None, 'pro', 3)
    hidden_arg = Argument(featured_statement_id=fs.id, proposer_id=None,
                          body='Hidden.', side='pro', hidden=True)
    db.session.add(hidden_arg)
    db.session.commit()
    resp = auth_client.post(f'/c/arg-conv/arguments/{hidden_arg.id}/vote')
    assert resp.status_code == 403


def test_unvote_wrong_conversation_returns_404(auth_client, arg_conv, arg_part,
                                               fs, participant, app):
    """argument_unvote must verify the argument belongs to the conversation in the URL."""
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
    arg = Argument(featured_statement_id=other_fs.id, proposer_id=None,
                   body='Other conv arg.', side='pro')
    db.session.add(arg)
    db.session.commit()
    # Try to unvote an argument from other_conv via arg-conv URL
    resp = auth_client.post(f'/c/arg-conv/arguments/{arg.id}/unvote')
    assert resp.status_code == 404


# ── Admin featured statements ──────────────────────────────────────────────────

def test_admin_featured_page_accessible(admin_client, arg_conv, admin_participant):
    Participation(participant_id=admin_participant.id,
                  conversation_id=arg_conv.id, pseudonym='admin-fox2')
    resp = admin_client.get(f'/admin/conversations/{arg_conv.id}/featured')
    assert resp.status_code == 200


def test_admin_featured_add_by_tid(admin_client, arg_conv, admin_participant):
    resp = admin_client.post(
        f'/admin/conversations/{arg_conv.id}/featured/add',
        data={'tid': 99},
    )
    assert resp.status_code == 302
    assert FeaturedStatement.query.filter_by(
        conversation_id=arg_conv.id, polis_statement_id=99).first()


def test_admin_featured_add_deduplicates(admin_client, arg_conv, admin_participant):
    admin_client.post(f'/admin/conversations/{arg_conv.id}/featured/add',
                      data={'tid': 55})
    admin_client.post(f'/admin/conversations/{arg_conv.id}/featured/add',
                      data={'tid': 55})
    assert FeaturedStatement.query.filter_by(
        conversation_id=arg_conv.id, polis_statement_id=55).count() == 1


def test_admin_featured_remove(admin_client, arg_conv, admin_participant, fs):
    # arg_conv has phase_argument_mapping=True and fs is the only featured statement —
    # the guard should block removal and leave the record intact.
    resp = admin_client.post(
        f'/admin/conversations/{arg_conv.id}/featured/{fs.id}/remove',
    )
    assert resp.status_code == 302
    assert db.session.get(FeaturedStatement, fs.id) is not None


def test_admin_featured_remove_allowed_when_multiple(app, admin_client, arg_conv, admin_participant, fs):
    # Add a second featured statement so removing the first is allowed.
    fs2 = FeaturedStatement(
        conversation_id=arg_conv.id,
        polis_statement_id=99,
        confirmed_by_admin=True,
    )
    db.session.add(fs2)
    db.session.commit()
    resp = admin_client.post(
        f'/admin/conversations/{arg_conv.id}/featured/{fs.id}/remove',
    )
    assert resp.status_code == 302
    assert db.session.get(FeaturedStatement, fs.id) is None


def test_non_admin_cannot_access_featured_admin(auth_client, arg_conv):
    resp = auth_client.get(f'/admin/conversations/{arg_conv.id}/featured')
    assert resp.status_code == 403
