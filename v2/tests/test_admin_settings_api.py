"""Admin settings browser-contract tests."""

from db import AdminRole, AuditEvent, db
from tests.conftest import login


def test_settings_contract_exposes_editable_eligibility_configuration(
    admin_client, conversation,
):
    conversation.eligibility_event_id = 'private-checker-event'
    conversation.eligibility_label = 'Extended-confirmed on the target wiki'
    conversation.recommended_quantities = {
        'tier': 'simple', 'featured_statements': 999,
    }
    db.session.commit()

    response = admin_client.get(
        f'/api/v1/admin/conversations/{conversation.id}/settings',
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['recommendations']['tier'] == 'simple'
    assert data['recommendations']['tiers'][0]['quantities']['featured_statements'] == 8
    assert data['eligibility']['configured'] is True
    assert data['eligibility']['configurationMode'] == 'editable'
    assert data['eligibility']['eventId'] == 'private-checker-event'


def test_organizer_replaces_settings_idempotently(
    client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='organizer',
    ))
    db.session.commit()
    login(client, 'testuser')
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/settings'
    body = {
        'title': '  Updated consultation  ',
        'introHtml': '<p>Hello<script>alert(1)</script></p>',
        'outroHtml': '<strong>Thank you</strong>',
        'accessPolicy': 'invite_only',
        'eligibilityEventId': 'extended-confirmed',
        'eligibilityLabel': 'Extended-confirmed editors',
        'recommendationTier': 'complex',
    }

    first = client.put(endpoint, json=body)
    replay = client.put(endpoint, json=body)

    assert first.status_code == replay.status_code == 200
    assert first.get_json()['data']['changed'] is True
    assert replay.get_json()['data']['changed'] is False
    settings = replay.get_json()['data']['settings']
    assert settings['conversation']['title'] == 'Updated consultation'
    assert '<script' not in settings['conversation']['introHtml']
    assert settings['conversation']['accessPolicy'] == 'invite_only'
    assert settings['eligibility']['eventId'] == 'extended-confirmed'
    assert settings['eligibility']['label'] == 'Extended-confirmed editors'
    assert settings['recommendations']['tier'] == 'complex'
    assert AuditEvent.query.filter_by(
        operation='conversation.settings.update',
        conversation_id=conversation.id,
    ).count() == 1


def test_settings_update_returns_field_errors(admin_client, conversation):
    response = admin_client.put(
        f'/api/v1/admin/conversations/{conversation.id}/settings',
        json={
            'title': '', 'introHtml': '', 'outroHtml': '',
            'accessPolicy': 'secret', 'eligibilityEventId': 'x' * 81,
            'eligibilityLabel': 'y' * 256, 'recommendationTier': 'enormous',
        },
    )

    assert response.status_code == 400
    assert set(response.get_json()['error']['details']['fields']) == {
        'title', 'accessPolicy', 'eligibilityEventId', 'eligibilityLabel',
        'recommendationTier',
    }


def test_moderator_can_read_but_not_change_settings(
    client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.commit()
    login(client, 'testuser')
    endpoint = f'/api/v1/admin/conversations/{conversation.id}/settings'

    readable = client.get(endpoint)
    denied = client.put(endpoint, json={
        'title': conversation.title, 'introHtml': '', 'outroHtml': '',
        'accessPolicy': 'public', 'eligibilityEventId': '',
        'eligibilityLabel': '', 'recommendationTier': 'medium',
    })

    assert readable.status_code == 200
    assert readable.get_json()['data']['capabilities']['edit'] is False
    assert denied.status_code == 403
