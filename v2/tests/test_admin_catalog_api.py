"""Site-wide administration API contract tests."""

from unittest.mock import patch

from db import AuditEvent, Conversation, Participant, db
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
        f'/admin/conversations/{conversation.id}',
    )
    assert data['configuredAdmins'] == []
    assert data['globalAdmins'] == [{
        'participantId': admin_participant.id,
        'username': 'adminuser',
        'self': True,
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
        f'/admin/conversations/{conversation.id}',
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


def test_site_admin_cannot_remove_own_site_admin_access(
    admin_client, admin_participant,
):
    """Owner, 2026-10-09: refused with nothing changed and no audit row."""
    response = admin_client.put(
        f'/api/v1/admin/global-admins/{admin_participant.id}',
        json={'granted': False},
    )

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'own_site_admin_protected'
    db.session.expire_all()
    assert db.session.get(Participant, admin_participant.id).is_global_admin is True
    assert AuditEvent.query.filter(
        AuditEvent.operation.in_(['global_admin.grant', 'global_admin.revoke']),
    ).count() == 0
    # Still a site admin afterwards.
    assert admin_client.get('/api/v1/admin').status_code == 200


def test_site_admin_can_remove_another_site_admin(
    admin_client, participant,
):
    participant.is_global_admin = True
    db.session.commit()

    response = admin_client.put(
        f'/api/v1/admin/global-admins/{participant.id}',
        json={'granted': False},
    )

    assert response.status_code == 200
    assert response.get_json()['data']['changed'] is True
    db.session.expire_all()
    assert db.session.get(Participant, participant.id).is_global_admin is False
    assert AuditEvent.query.filter_by(operation='global_admin.revoke').count() == 1


def test_setting_own_site_admin_access_to_granted_is_not_refused(
    admin_client, admin_participant,
):
    """Granting is unaffected: asking to keep one's own access is a no-op, not a refusal."""
    response = admin_client.put(
        f'/api/v1/admin/global-admins/{admin_participant.id}',
        json={'granted': True},
    )

    assert response.status_code == 200
    assert response.get_json()['data']['changed'] is False


def test_admin_catalog_requires_global_admin(auth_client):
    assert auth_client.get('/api/v1/admin').status_code == 403


def test_openapi_documents_site_admin_contract(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    assert spec['paths']['/admin']['get']['operationId'] == 'getAdminCatalog'
    assert spec['paths']['/admin/conversations']['post']['operationId'] == 'postAdminConversation'


def test_site_admins_set_in_the_server_configuration_are_listed_apart(
    admin_client, admin_participant, participant, monkeypatch,
):
    """Two kinds of site admin: set in the server configuration (`admin-users`, matched by
    username), which the app cannot remove, and granted in the app. A username in both is
    listed once, as configured (and the app refuses to remove it, see below)."""
    import app as app_module
    participant.is_global_admin = True
    from db import db as _db
    _db.session.commit()
    monkeypatch.setattr(app_module, 'ADMIN_USERS', ['Config-admin', 'adminuser'])

    data = admin_client.get('/api/v1/admin').get_json()['data']

    assert data['configuredAdmins'] == ['Config-admin', 'adminuser']
    assert data['globalAdmins'] == [
        {'participantId': participant.id, 'username': 'testuser', 'self': False},
    ]


def test_a_configured_site_admin_with_no_participant_row_sees_the_dashboard(client, monkeypatch):
    """Configured by username alone, before ever signing in to the app as a participant."""
    import app as app_module
    from tests.conftest import login
    monkeypatch.setattr(app_module, 'ADMIN_USERS', ['Config-admin'])
    login(client, 'Config-admin')

    response = client.get('/api/v1/admin')

    assert response.status_code == 200
    assert response.get_json()['data']['configuredAdmins'] == ['Config-admin']


def test_build_admin_catalog_lists_a_username_once_and_keeps_order():
    from types import SimpleNamespace
    from services.admin_catalog import build_admin_catalog
    granted = [SimpleNamespace(id=3, mw_username='Both'), SimpleNamespace(id=4, mw_username='Granted')]

    data = build_admin_catalog(
        conversations=[], global_admins=granted, phase_routes={}, managed_creation=False,
        self_link='/api/v1/admin', conversation_link=str,
        configured_admins=['Zed', 'Both', '', 'Zed'],
    )

    assert data['configuredAdmins'] == ['Zed', 'Both']
    assert data['globalAdmins'] == [{'participantId': 4, 'username': 'Granted', 'self': False}]


def test_openapi_documents_configured_site_admins(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    catalog = spec['components']['schemas']['AdminCatalog']
    assert 'configuredAdmins' in catalog['required']
    assert catalog['properties']['configuredAdmins']['items'] == {'type': 'string'}


def _site_admin_audit_count():
    return AuditEvent.query.filter(
        AuditEvent.operation.in_(['global_admin.grant', 'global_admin.revoke']),
    ).count()


def test_a_configured_site_admin_cannot_be_removed_in_the_app(
    admin_client, participant, monkeypatch,
):
    """Owner, 2026-10-11: a site admin named in the server configuration is hard-coded. An app
    grant for the same username (pre-existing data) is refused removal: nothing changed, no
    audit row."""
    import app as app_module
    participant.is_global_admin = True
    db.session.commit()
    monkeypatch.setattr(app_module, 'ADMIN_USERS', ['testuser'])

    response = admin_client.put(
        f'/api/v1/admin/global-admins/{participant.id}', json={'granted': False},
    )

    assert response.status_code == 409
    error = response.get_json()['error']
    assert error['code'] == 'configured_site_admin_protected'
    assert error['message'] == (
        'This site admin is set in the server configuration and cannot be removed here.'
    )
    db.session.expire_all()
    assert db.session.get(Participant, participant.id).is_global_admin is True
    assert _site_admin_audit_count() == 0


def test_removing_ones_own_configured_access_says_it_is_configured(
    admin_client, admin_participant, monkeypatch,
):
    """The configuration refusal comes before the self-revoke one, so it says why."""
    import app as app_module
    monkeypatch.setattr(app_module, 'ADMIN_USERS', ['adminuser'])

    response = admin_client.put(
        f'/api/v1/admin/global-admins/{admin_participant.id}', json={'granted': False},
    )

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'configured_site_admin_protected'
    db.session.expire_all()
    assert db.session.get(Participant, admin_participant.id).is_global_admin is True
    assert _site_admin_audit_count() == 0


def test_a_configured_username_cannot_also_be_granted_in_the_app(
    admin_client, participant, monkeypatch,
):
    """Owner, 2026-10-11: no hidden app grant can be created through the dashboard."""
    import app as app_module
    monkeypatch.setattr(app_module, 'ADMIN_USERS', ['testuser'])

    by_name = admin_client.post(
        '/api/v1/admin/global-admin-grants', json={'username': 'testuser'},
    )
    by_id = admin_client.put(
        f'/api/v1/admin/global-admins/{participant.id}', json={'granted': True},
    )

    for response in (by_name, by_id):
        assert response.status_code == 409
        error = response.get_json()['error']
        assert error['code'] == 'already_configured_site_admin'
        assert error['message'] == (
            'This person is already a site admin through the server configuration.'
        )
    db.session.expire_all()
    assert db.session.get(Participant, participant.id).is_global_admin is False
    assert _site_admin_audit_count() == 0


def test_an_app_grant_reappears_once_the_name_leaves_the_configuration(
    admin_client, participant, monkeypatch,
):
    """Shown once, as configured, while the secret names it; once it no longer does, the app
    grant is an ordinary app-granted row again and can be removed."""
    import app as app_module
    participant.is_global_admin = True
    db.session.commit()
    monkeypatch.setattr(app_module, 'ADMIN_USERS', ['testuser'])
    covered = admin_client.get('/api/v1/admin').get_json()['data']
    assert covered['configuredAdmins'] == ['testuser']
    assert participant.id not in [row['participantId'] for row in covered['globalAdmins']]

    monkeypatch.setattr(app_module, 'ADMIN_USERS', [])
    data = admin_client.get('/api/v1/admin').get_json()['data']

    assert data['configuredAdmins'] == []
    assert {'participantId': participant.id, 'username': 'testuser', 'self': False} in (
        data['globalAdmins']
    )
    removed = admin_client.put(
        f'/api/v1/admin/global-admins/{participant.id}', json={'granted': False},
    )
    assert removed.status_code == 200
    assert removed.get_json()['data']['changed'] is True


def test_self_marks_the_callers_own_row_by_participant_id(
    admin_client, admin_participant, participant,
):
    """Matched by participant id, as the self-revoke guard is, not by the session's username,
    which may differ from the row's Wikimedia username."""
    participant.is_global_admin = True
    db.session.commit()
    with admin_client.session_transaction() as sess:
        sess['username'] = 'Renamed admin'

    rows = admin_client.get('/api/v1/admin').get_json()['data']['globalAdmins']

    assert {row['username']: row['self'] for row in rows} == {
        'adminuser': True, 'testuser': False,
    }


def test_build_admin_catalog_marks_self_only_for_the_actor():
    from types import SimpleNamespace
    from services.admin_catalog import build_admin_catalog
    granted = [SimpleNamespace(id=3, mw_username='Me'), SimpleNamespace(id=4, mw_username='Other')]

    data = build_admin_catalog(
        conversations=[], global_admins=granted, phase_routes={}, managed_creation=False,
        self_link='/api/v1/admin', conversation_link=str, actor_id=3,
    )

    assert [row['self'] for row in data['globalAdmins']] == [True, False]


def test_openapi_documents_the_site_admin_refusals(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    put_409 = spec['paths']['/admin/global-admins/{participantId}']['put']['responses']['409']
    grant_409 = spec['paths']['/admin/global-admin-grants']['post']['responses']['409']
    for code in ('own_site_admin_protected', 'configured_site_admin_protected',
                 'already_configured_site_admin'):
        assert code in put_409['description']
    assert 'already_configured_site_admin' in grant_409['description']
    row = spec['components']['schemas']['AdminCatalog']['properties']['globalAdmins']['items']
    assert 'self' in row['required']
