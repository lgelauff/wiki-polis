"""Conversation role roster and replacement API contract tests."""

from db import AdminRole, AuditEvent, Participant, db
from tests.conftest import login


def test_global_admin_role_roster_includes_candidates(
    admin_client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.commit()

    response = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}/roles',
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['capabilities'] == {'manageRoles': True}
    assert data['assignments'][0]['username'] == 'testuser'
    assert data['assignments'][0]['roles'] == ['moderator']
    assert {row['username'] for row in data['candidates']} == {
        'adminuser', 'testuser',
    }


def test_scoped_moderator_sees_assignments_but_not_candidate_directory(
    client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.add(Participant(
        mw_user_id=333, mw_username='unrelated-account', xid='u' * 64,
    ))
    db.session.commit()
    login(client, 'testuser')

    response = client.get(
        f'/api/v1/admin/conversations/{conversation.id}/roles',
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['capabilities'] == {'manageRoles': False}
    assert data['candidates'] == []
    assert 'unrelated-account' not in response.text


def test_role_set_replacement_is_idempotent_and_audits_deltas(
    admin_client, conversation, participant,
):
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}'
        f'/roles/{participant.id}'
    )

    grant = admin_client.put(endpoint, json={
        'roles': ['moderator', 'organizer'],
    })
    replay = admin_client.put(endpoint, json={
        'roles': ['moderator', 'organizer'],
    })
    replace = admin_client.put(endpoint, json={'roles': ['organizer']})

    assert grant.status_code == replay.status_code == replace.status_code == 200
    assert grant.get_json()['data']['added'] == ['moderator', 'organizer']
    assert replay.get_json()['data']['changed'] is False
    assert replace.get_json()['data']['removed'] == ['moderator']
    assert [row.role for row in AdminRole.query.all()] == ['organizer']
    assert [(event.operation, event.detail['role']) for event in AuditEvent.query.order_by(AuditEvent.id)] == [
        ('role.grant', 'moderator'),
        ('role.grant', 'organizer'),
        ('role.revoke', 'moderator'),
    ]


def test_scoped_moderator_cannot_replace_roles(
    client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.commit()
    login(client, 'testuser')

    response = client.put(
        f'/api/v1/admin/conversations/{conversation.id}/roles/{participant.id}',
        json={'roles': ['organizer']},
    )

    assert response.status_code == 403
    assert [row.role for row in AdminRole.query.all()] == ['moderator']


def test_role_replacement_validates_unique_known_roles(
    admin_client, conversation, participant,
):
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}'
        f'/roles/{participant.id}'
    )

    unknown = admin_client.put(endpoint, json={'roles': ['owner']})
    duplicate = admin_client.put(endpoint, json={'roles': ['moderator', 'moderator']})
    missing = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/roles/9999',
        json={'roles': []},
    )

    assert unknown.status_code == duplicate.status_code == 400
    assert missing.status_code == 404


def test_openapi_documents_admin_role_contract(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    roster = '/admin/conversations/{conversationId}/roles'
    assignment = '/admin/conversations/{conversationId}/roles/{participantId}'

    assert spec['paths'][roster]['get']['operationId'] == 'getAdminConversationRoles'
    assert spec['paths'][assignment]['put']['operationId'] == 'putAdminConversationRoles'
