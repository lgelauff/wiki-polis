"""Statement administration API contract tests."""

from unittest.mock import MagicMock, patch

from db import AdminRole, AuditEvent, FeaturedStatement, db
from polis_admin import PolisServerError
from tests.conftest import login


def _statement_rows():
    return (
        [{
            'tid': 11, 'txt': 'Needs review', 'mod': 0, 'is_seed': False,
            'agree_count': 2, 'pass_count': 1, 'disagree_count': 3,
            'pid': 991, 'xid': 'must-not-leak',
        }],
        [{
            'tid': 12, 'txt': 'Approved seed', 'mod': 1, 'is_seed': True,
            'agree_count': 4, 'pass_count': 2, 'disagree_count': 1,
        }],
        [],
    )


def _upstream(rows=None, strict=True):
    server = MagicMock()
    server.get_statements.return_value = rows or _statement_rows()
    participant = MagicMock()
    participant.get_settings.return_value = {'strict_moderation': strict}
    participant.get_statements.return_value = rows or _statement_rows()
    return server, participant


def test_statement_workspace_is_typed_and_privacy_safe(admin_client, conversation):
    server, participant = _upstream()
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/statements',
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['moderationPolicy'] == {'strict': True, 'available': True}
    assert data['dataAvailability'] == {'statements': True}
    assert data['seeding']['maxStatementsPerImport'] == 20
    assert data['statements']['pending'][0] == {
        'id': 11,
        'text': 'Needs review',
        'moderation': 'pending',
        'seed': False,
        'featured': False,
        'votes': {'agree': 2, 'pass': 1, 'disagree': 3},
        'provenance': None,
    }
    assert 'must-not-leak' not in response.text
    assert 'pid' not in response.text


def test_statement_workspace_distinguishes_unavailable_from_empty(
    admin_client, conversation,
):
    server, participant = _upstream()
    server.get_statements.return_value = None
    from polis_admin import PolisParticipantError
    participant.get_statements.side_effect = PolisParticipantError('offline')
    participant.get_settings.side_effect = PolisParticipantError('offline')
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/statements',
        )

    data = response.get_json()['data']
    assert data['dataAvailability']['statements'] is False
    assert data['capabilities']['moderate'] is False
    assert data['statements'] == {'pending': [], 'approved': [], 'hidden': []}


def test_moderator_replaces_statement_state_and_receives_refreshed_workspace(
    client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.commit()
    login(client, 'testuser')
    server, participant_client = _upstream()
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant_client),
    ):
        response = client.put(
            f'/api/v1/admin/conversations/{conversation.id}/statements/11/moderation',
            json={'status': 'approved'},
        )

    assert response.status_code == 200
    assert response.get_json()['data']['status'] == 'approved'
    server.moderate.assert_called_once_with(conversation.polis_id, 11, 1)
    event = AuditEvent.query.filter_by(
        operation='statement.moderate', conversation_id=conversation.id,
    ).one()
    assert event.target_id == '11'
    assert event.detail == {'decision': 1}


def test_moderation_rejects_unknown_statement_and_upstream_failure(
    admin_client, conversation,
):
    server, participant = _upstream()
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        unknown = admin_client.put(
            f'/api/v1/admin/conversations/{conversation.id}/statements/999/moderation',
            json={'status': 'hidden'},
        )
    server.moderate.side_effect = PolisServerError('offline')
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        unavailable = admin_client.put(
            f'/api/v1/admin/conversations/{conversation.id}/statements/11/moderation',
            json={'status': 'hidden'},
        )

    assert unknown.status_code == 404
    assert unavailable.status_code == 502
    assert unavailable.get_json()['error']['code'] == 'upstream_unavailable'


def test_last_featured_statement_is_protected_during_argument_mapping(
    admin_client, conversation,
):
    conversation.phase_argument_mapping = True
    db.session.add(FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=11,
        statement_text='Needs review',
        confirmed_by_admin=True,
    ))
    db.session.commit()
    server, participant = _upstream()
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.put(
            f'/api/v1/admin/conversations/{conversation.id}/statements/11/moderation',
            json={'status': 'hidden'},
        )

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'last_featured_statement_protected'
    server.moderate.assert_not_called()
