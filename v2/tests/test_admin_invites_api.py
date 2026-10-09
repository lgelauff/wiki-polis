"""Admin invitation roster and bulk command API contract tests."""

from unittest.mock import patch

from db import AdminRole, AuditEvent, Conversation, ConversationInvite, Participant, db
from services.invites import InviteBatchSaveError, claim_username_invites
from tests.conftest import login


def test_admin_invitation_roster_reports_policy_and_sorted_usernames(
    admin_client, conversation,
):
    conversation.access_policy = 'invite_only'
    db.session.add_all([
        ConversationInvite(conversation_id=conversation.id, mw_username='Zulu'),
        ConversationInvite(conversation_id=conversation.id, mw_username='Alpha'),
    ])
    db.session.commit()

    response = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}/invitations',
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['conversation']['accessPolicy'] == 'invite_only'
    assert [row['username'] for row in data['invitations']] == ['Alpha', 'Zulu']
    assert all(row['createdAt'].endswith('Z') for row in data['invitations'])


def test_admin_invitation_roster_requires_moderation_access(
    auth_client, conversation,
):
    response = auth_client.get(
        f'/api/v1/admin/conversations/{conversation.id}/invitations',
    )

    assert response.status_code == 403


def test_bulk_invitation_put_converges_duplicates_and_returns_roster(
    admin_client, conversation,
):
    db.session.add(ConversationInvite(
        conversation_id=conversation.id, mw_username='Alice',
    ))
    db.session.commit()

    response = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/invitations',
        json={'usernames': ['Alice', 'Bob', 'Bob']},
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['outcome'] == {
        'added': 1,
        'alreadyPresent': 1,
        'concurrentConflicts': 0,
        'duplicateInputs': 1,
    }
    assert [row['username'] for row in data['invitations']] == ['Alice', 'Bob']
    assert [event.operation for event in AuditEvent.query.all()] == ['invite.add']
    assert AuditEvent.query.one().detail == {'count': 1}


def test_bulk_invitation_put_has_structured_validation_and_save_errors(
    admin_client, conversation,
):
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/invitations'

    invalid = admin_client.put(endpoint, json={'usernames': []})
    with patch(
        'app.add_conversation_invites',
        side_effect=InviteBatchSaveError('database unavailable'),
    ):
        failed = admin_client.put(endpoint, json={'usernames': ['Alice']})

    assert invalid.status_code == 400
    assert invalid.get_json()['error']['code'] == 'validation_failed'
    assert failed.status_code == 503
    assert failed.get_json()['error']['code'] == 'save_failed'


def test_delete_invitation_is_scoped_and_returns_refreshed_roster(
    admin_client, conversation,
):
    other = Conversation(
        slug='other-invites', polis_id='other98765', title='Other', active=True,
        access_policy='invite_only',
    )
    db.session.add(other)
    db.session.flush()
    keep = ConversationInvite(conversation_id=conversation.id, mw_username='Keep')
    foreign = ConversationInvite(conversation_id=other.id, mw_username='Foreign')
    db.session.add_all([keep, foreign])
    db.session.commit()

    missing = admin_client.delete(
        f'/api/v1/admin/conversations/{conversation.id}/invitations/{foreign.id}',
    )
    removed = admin_client.delete(
        f'/api/v1/admin/conversations/{conversation.id}/invitations/{keep.id}',
    )

    assert missing.status_code == 404
    assert removed.status_code == 200
    assert removed.get_json()['data']['invitations'] == []
    assert db.session.get(ConversationInvite, foreign.id) is not None
    assert [event.operation for event in AuditEvent.query.all()] == ['invite.remove']


def _with_role(client, conversation, participant, role):
    db.session.add(AdminRole(
        participant_id=participant.id, conversation_id=conversation.id, role=role,
    ))
    db.session.commit()
    login(client, 'testuser')


def test_moderator_reads_invitations_with_usernames_but_cannot_change_them(
    client, conversation, participant,
):
    """Owner, 2026-10-09: invitations are access, so organizers stay in charge of them. A
    moderator sees the list (usernames included) read-only; adding and removing are
    refused and change nothing."""
    keep = ConversationInvite(conversation_id=conversation.id, mw_username='Keep')
    db.session.add(keep)
    db.session.commit()
    _with_role(client, conversation, participant, 'moderator')
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/invitations'

    roster = client.get(endpoint)
    added = client.put(endpoint, json={'usernames': ['Bob']})
    removed = client.delete(f'{endpoint}/{keep.id}')

    assert roster.status_code == 200
    assert [row['username'] for row in roster.get_json()['data']['invitations']] == ['Keep']
    assert roster.get_json()['data']['capabilities'] == {'manageInvitations': False}
    assert added.status_code == 403
    assert removed.status_code == 403
    assert [row.mw_username for row in ConversationInvite.query.all()] == ['Keep']
    assert AuditEvent.query.count() == 0


def test_organizer_manages_invitations(client, conversation, participant):
    _with_role(client, conversation, participant, 'organizer')
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/invitations'

    roster = client.get(endpoint)
    added = client.put(endpoint, json={'usernames': ['Bob']})
    invite_id = added.get_json()['data']['invitations'][0]['id']
    removed = client.delete(f'{endpoint}/{invite_id}')

    assert roster.get_json()['data']['capabilities'] == {'manageInvitations': True}
    assert added.status_code == 200
    assert removed.status_code == 200
    assert ConversationInvite.query.count() == 0


def test_site_admin_still_manages_invitations(admin_client, conversation):
    roster = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}/invitations',
    )
    assert roster.get_json()['data']['capabilities'] == {'manageInvitations': True}


def test_admin_invitation_roster_reports_whether_the_account_has_signed_in(
    admin_client, conversation,
):
    """signedIn mirrors the binding the invite-only check already uses."""
    conversation.access_policy = 'invite_only'
    db.session.add_all([
        ConversationInvite(
            conversation_id=conversation.id, mw_username='Bound', mw_user_id=4242,
        ),
        ConversationInvite(conversation_id=conversation.id, mw_username='Unbound'),
    ])
    db.session.commit()

    response = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}/invitations',
    )

    assert response.status_code == 200
    rows = response.get_json()['data']['invitations']
    assert {row['username']: row['signedIn'] for row in rows} == {
        'Bound': True, 'Unbound': False,
    }


def test_invitation_made_before_first_login_reads_linked_once_claimed(
    admin_client, conversation,
):
    """The #457 path: invited by name, then the account logs in and claims it."""
    conversation.access_policy = 'invite_only'
    db.session.add(ConversationInvite(conversation_id=conversation.id, mw_username='Newcomer'))
    db.session.commit()
    roster_url = f'/api/v1/admin/conversations/{conversation.id}/invitations'

    before = admin_client.get(roster_url).get_json()['data']['invitations']
    assert [(row['username'], row['signedIn']) for row in before] == [('Newcomer', False)]

    assert claim_username_invites(db.session, mw_user_id=9911, mw_username='Newcomer') == 1
    db.session.commit()

    after = admin_client.get(roster_url).get_json()['data']['invitations']
    assert [(row['username'], row['signedIn']) for row in after] == [('Newcomer', True)]


def test_bulk_invitation_receipt_reports_signed_in_for_a_known_account(
    admin_client, conversation,
):
    db.session.add(Participant(
        mw_user_id=7654, mw_username='Known editor', xid='known-editor-xid',
    ))
    db.session.commit()

    response = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/invitations',
        json={'usernames': ['Known editor', 'Never seen']},
    )

    assert response.status_code == 200
    rows = response.get_json()['data']['invitations']
    assert {row['username']: row['signedIn'] for row in rows} == {
        'Known editor': True, 'Never seen': False,
    }


def test_openapi_documents_admin_invitation_contract(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    collection = '/admin/conversations/{conversationId}/invitations'
    item = '/admin/conversations/{conversationId}/invitations/{inviteId}'

    assert spec['paths'][collection]['get']['operationId'] == (
        'getAdminConversationInvitations'
    )
    assert spec['paths'][collection]['put']['operationId'] == (
        'putAdminConversationInvitations'
    )
    assert spec['paths'][item]['delete']['operationId'] == (
        'deleteAdminConversationInvitation'
    )
    invitation = spec['components']['schemas']['AdminInvitation']
    assert invitation['properties']['signedIn'] == {'type': 'boolean'}
    assert 'signedIn' in invitation['required']
