"""Invitations made by user name are bound to the Wikimedia account at login.

The invite-only check matches the stable user id (#405), so an invitation for
someone who had not logged in yet must be claimed by their login, by exact
MediaWiki-canonical name: never by a collation-equal different account.
"""
import pytest

from db import Conversation, ConversationInvite, Participant, db
from services.access import check_access
from services.invites import (
    add_conversation_invites, canonical_mw_username, claim_username_invites,
)


@pytest.fixture
def invite_only(conversation):
    conversation.access_policy = 'invite_only'
    conversation.gated = True
    conversation.gating_type = 'invite_only'
    db.session.commit()
    return conversation


def _invite(conv, *names):
    return add_conversation_invites(db.session, conversation_id=conv.id, usernames=list(names))


def _login(user_id, name):
    """What a login does: the account row, then the claim."""
    p = Participant.query.filter_by(mw_user_id=user_id).first()
    if p is None:
        p = Participant(mw_user_id=user_id, mw_username=name, xid=f'{user_id:064d}')
        db.session.add(p)
    p.mw_username = name
    claimed = claim_username_invites(db.session, mw_user_id=user_id, mw_username=name)
    db.session.commit()
    return p, claimed


@pytest.mark.parametrize('raw,canonical', [
    ('foo_bar', 'Foo bar'), ('  Foo   bar ', 'Foo bar'), ('alice', 'Alice'),
    ('ALICE', 'ALICE'), ('Ölaf_de_Vries', 'Ölaf de Vries'), ('', ''),
])
def test_canonical_mw_username(raw, canonical):
    assert canonical_mw_username(raw) == canonical


@pytest.mark.parametrize('typed', ['Newcomer user', 'newcomer_user', ' newcomer  user '])
def test_an_invite_typed_loosely_is_claimed_by_the_canonical_login(app, invite_only, typed):
    _invite(invite_only, typed)
    p, claimed = _login(777, 'Newcomer user')
    assert claimed == 1
    assert check_access(invite_only, p).allowed is True


def test_a_different_account_with_a_case_variant_name_cannot_claim(app, invite_only):
    """Under MariaDB's case-insensitive collation "ALICE" = "Alice"; they are
    different Wikimedia accounts, so the claim must compare exactly."""
    _invite(invite_only, 'Alice')
    squatter, claimed = _login(666, 'ALICE')
    assert claimed == 0
    assert check_access(invite_only, squatter).allowed is False
    alice, claimed = _login(111, 'Alice')
    assert claimed == 1
    assert check_access(invite_only, alice).allowed is True


def test_an_invite_already_bound_is_never_rebound(app, invite_only):
    _login(111, 'Samename')
    _invite(invite_only, 'Samename')  # binds at add time: the account exists
    _, claimed = _login(222, 'Samename')
    assert claimed == 0
    assert ConversationInvite.query.one().mw_user_id == 111


def test_adding_binds_only_on_an_exact_name_match(app, invite_only):
    _login(111, 'Alice')
    _invite(invite_only, 'ALICE')
    assert ConversationInvite.query.one().mw_user_id is None


def test_case_and_underscore_variants_are_one_invitation(app, invite_only):
    first = _invite(invite_only, 'Foo bar')
    again = _invite(invite_only, 'foo_bar', 'Foo  bar')
    assert first.added == 1
    assert again.added == 0 and again.concurrent_conflicts == 0
    assert ConversationInvite.query.count() == 1


def test_a_renamed_account_claims_invites_for_its_new_name(app, invite_only):
    _login(111, 'Oldname')
    _invite(invite_only, 'Newname')  # nobody is called Newname yet
    p, claimed = _login(111, 'Newname')  # the rename arrives with the next login
    assert claimed == 1
    assert check_access(invite_only, p).allowed is True


def test_the_claim_binds_every_conversation_but_only_that_name(app, invite_only):
    other = Conversation(slug='other', polis_id='other12345', title='Other', active=True,
                         access_policy='invite_only', gated=True, gating_type='invite_only')
    db.session.add(other)
    db.session.commit()
    _invite(invite_only, 'Newcomer', 'Someone else')
    _invite(other, 'newcomer')
    _, claimed = _login(777, 'Newcomer')
    assert claimed == 2
    assert ConversationInvite.query.filter_by(mw_username='Someone else').one().mw_user_id is None
