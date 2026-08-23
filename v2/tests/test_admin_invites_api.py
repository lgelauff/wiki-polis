"""Admin invitation roster and bulk command API contract tests."""

from unittest.mock import patch

from db import AuditEvent, Conversation, ConversationInvite, db
from services.invites import InviteBatchSaveError


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
