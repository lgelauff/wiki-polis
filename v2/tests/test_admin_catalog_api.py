"""Site-wide administration API contract tests."""

from unittest.mock import patch

from db import AuditEvent, Conversation, db
from services.admin_catalog import ConversationCreationSaveFailed


def _creation_body(**overrides):
    body = {
        'slug': 'new-catalog-conversation',
        'title': 'New catalog conversation',
        'introHtml': '<p>Introduction</p>',
        'outroHtml': '',
        'accessPolicy': 'public',
        'phaseRoute': 'default_7',
        'eligibilityEventId': '',
        'eligibilityLabel': '',
        'polisId': 'manual12345',
    }
    body.update(overrides)
    return body


def test_admin_catalog_is_privacy_safe_and_spa_linked(
    admin_client, conversation, admin_participant,
):
    response = admin_client.get('/api/v1/admin')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['creation']['mode'] == 'manual_polis_id'
    assert data['conversations'][0]['links']['manage'].endswith(
        f'/app/admin/conversations/{conversation.id}',
    )
    assert data['globalAdmins'] == [{
        'participantId': admin_participant.id,
        'username': 'adminuser',
    }]
    assert conversation.polis_id not in response.text


def test_manual_conversation_creation_returns_receipt_and_moderate_default(
    admin_client,
):
    response = admin_client.post(
        '/api/v1/admin/conversations', json=_creation_body(),
    )

    assert response.status_code == 201
    conversation = Conversation.query.filter_by(
        slug='new-catalog-conversation',
    ).one()
    assert conversation.polis_id == 'manual12345'
    assert conversation.statement_moderation_policy == 'moderate'
    assert response.get_json()['data']['links']['manage'].endswith(
        f'/app/admin/conversations/{conversation.id}',
    )
    assert AuditEvent.query.filter_by(operation='conversation.create').count() == 1


def test_managed_creation_keeps_polis_strict_and_hides_upstream_identifier(
    app, admin_client,
):
    app.config.update({
        'POLIS_SERVER_URL': 'http://polis.test',
        'POLIS_ADMIN_EMAIL': 'admin@example.org',
        'POLIS_ADMIN_PASSWORD': 'test-password',
    })
    with patch(
        'app.PolisServerClient.create_conversation', return_value='private-polis-id',
    ) as create:
        response = admin_client.post(
            '/api/v1/admin/conversations',
            json=_creation_body(slug='managed-conversation', polisId=None),
        )

    assert response.status_code == 201
    create.assert_called_once_with(
        'New catalog conversation', strict_moderation=True,
    )
    assert 'private-polis-id' not in response.text


def test_conversation_creation_reports_conflict_and_unknown_outcome(
    admin_client, conversation,
):
    conflict = admin_client.post(
        '/api/v1/admin/conversations',
        json=_creation_body(slug=conversation.slug),
    )
    with patch(
        'app.create_admin_conversation',
        side_effect=ConversationCreationSaveFailed(outcome_unknown=True),
    ):
        unknown = admin_client.post(
            '/api/v1/admin/conversations', json=_creation_body(),
        )

    assert conflict.status_code == 409
    assert conflict.get_json()['error']['code'] == 'slug_conflict'
    assert unknown.status_code == 409
    assert unknown.get_json()['error']['code'] == 'command_outcome_unknown'


def test_global_admin_grants_are_desired_state_commands(
    admin_client, participant,
):
    grant = admin_client.post(
        '/api/v1/admin/global-admin-grants',
        json={'username': participant.mw_username},
    )
    replay = admin_client.post(
        '/api/v1/admin/global-admin-grants',
        json={'username': participant.mw_username},
    )
    revoke = admin_client.put(
        f'/api/v1/admin/global-admins/{participant.id}',
        json={'granted': False},
    )

    assert grant.status_code == 201
    assert grant.get_json()['data']['changed'] is True
    assert replay.status_code == 200
    assert replay.get_json()['data']['changed'] is False
    assert revoke.get_json()['data']['granted'] is False
    assert AuditEvent.query.filter(
        AuditEvent.operation.in_(['global_admin.grant', 'global_admin.revoke']),
    ).count() == 2


def test_admin_catalog_requires_global_admin(auth_client):
    assert auth_client.get('/api/v1/admin').status_code == 403


def test_openapi_documents_site_admin_contract(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    assert spec['paths']['/admin']['get']['operationId'] == 'getAdminCatalog'
    assert spec['paths']['/admin/conversations']['post']['operationId'] == 'postAdminConversation'
