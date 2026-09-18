"""Provider-neutral access contract tests."""

from types import SimpleNamespace

import pytest

from db import ConversationInvite, Participation, db
from services.access import AccessAnswer, check_access


def test_access_answer_separates_unknown_certainty():
    assert AccessAnswer(
        'unknown', reason='access-could-not-confirm', certainty='temporary',
    ).certainty == 'temporary'
    with pytest.raises(ValueError):
        AccessAnswer('refused', reason='access-invite-required', certainty='temporary')


def test_existing_participation_does_not_short_circuit_invite_check(
    app, conversation, participant,
):
    conversation.access_policy = 'invite_only'
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='joined-otter',
    ))
    db.session.commit()

    decision = check_access(conversation, participant)

    assert decision.allowed is False
    assert decision.viewer == 'access_lost'
    assert decision.certainty == 'known'
    assert decision.reason == 'access-invite-required'


def test_unknown_provider_keeps_viewer_relationship_and_certainty(
    app, conversation, participant,
):
    conversation.gated = True
    conversation.gating_type = 'voucher'
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='joined-otter',
    ))
    db.session.commit()

    decision = check_access(conversation, participant)

    assert decision.allowed is False
    assert decision.viewer == 'access_lost'
    assert decision.answer.state == 'unknown'
    assert decision.certainty == 'inconclusive'
    assert decision.reason == 'access-could-not-confirm'


def test_invite_lookup_does_not_match_null_identity(app, conversation):
    conversation.access_policy = 'invite_only'
    db.session.add(ConversationInvite(
        conversation_id=conversation.id,
        mw_username='legacy-account',
        mw_user_id=None,
    ))
    voucher = SimpleNamespace(id=999, mw_user_id=None, mw_username=None)
    db.session.commit()

    decision = check_access(conversation, voucher)

    assert decision.allowed is False
    assert decision.viewer == 'refused'
    assert decision.reason == 'access-invite-required'


def test_invite_lookup_ignores_stale_username_with_different_user_id(
    app, conversation, participant,
):
    conversation.access_policy = 'invite_only'
    db.session.add(ConversationInvite(
        conversation_id=conversation.id,
        mw_username=participant.mw_username,
        mw_user_id=12345,
    ))
    db.session.commit()

    decision = check_access(conversation, participant)

    assert decision.allowed is False
    assert decision.viewer == 'refused'
    assert decision.reason == 'access-invite-required'


def test_logged_out_access_has_a_viewer_state_without_provider_call(
    app, conversation,
):
    conversation.gated = True
    conversation.gating_type = 'invite_only'
    db.session.commit()

    decision = check_access(conversation, None)

    assert decision.allowed is False
    assert decision.viewer == 'logged_out'
    assert decision.answer is None
    assert decision.certainty == 'known'
    assert decision.reason is None
