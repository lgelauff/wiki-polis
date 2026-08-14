"""Statement administration API contract tests."""

from unittest.mock import MagicMock, patch

from db import AdminRole, AuditEvent, FeaturedStatement, db
from polis_admin import POLIS_NOT_CONFIGURED_MESSAGE, PolisServerError
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
    assert data['moderationPolicy'] == {
        'mode': 'moderate', 'newStatements': 'pending', 'available': True,
    }
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


def test_legacy_policy_is_adopted_from_live_upstream_state(
    admin_client, conversation,
):
    conversation.statement_moderation_policy = None
    db.session.commit()
    server, participant = _upstream(strict=False)
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/statements',
        )

    assert response.get_json()['data']['moderationPolicy'] == {
        'mode': 'auto_approve',
        'newStatements': 'approved',
        'available': True,
    }


def test_policy_change_explicitly_approves_visible_pending_before_strict_baseline(
    admin_client, conversation,
):
    conversation.statement_moderation_policy = None
    db.session.commit()
    server, participant = _upstream(strict=False)
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.put(
            f'/api/v1/admin/conversations/{conversation.id}/statement-moderation-policy',
            json={'mode': 'auto_approve'},
        )

    assert response.status_code == 200
    assert response.get_json()['data']['reconciledStatements'] == 1
    server.moderate.assert_called_once_with(conversation.polis_id, 11, 1)
    server.set_strict_moderation.assert_called_once_with(conversation.polis_id, True)
    db.session.refresh(conversation)
    assert conversation.statement_moderation_policy == 'auto_approve'
    events = AuditEvent.query.order_by(AuditEvent.id).all()
    assert [event.operation for event in events] == [
        'statement.moderation.baseline',
        'statement.moderation_policy.set',
    ]


def test_policy_change_fails_closed_when_live_state_is_unavailable(
    admin_client, conversation,
):
    server, participant = _upstream()
    from polis_admin import PolisParticipantError
    participant.get_settings.side_effect = PolisParticipantError('offline')
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.put(
            f'/api/v1/admin/conversations/{conversation.id}/statement-moderation-policy',
            json={'mode': 'auto_approve'},
        )

    assert response.status_code == 503
    assert response.get_json()['error']['code'] == 'verification_unavailable'
    server.moderate.assert_not_called()
    server.set_strict_moderation.assert_not_called()


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


def test_seed_import_sanitizes_deduplicates_and_reports_counts(
    admin_client, conversation,
):
    server, participant = _upstream()
    server.bulk_add_seeds.return_value = (2, [])
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.post(
            f'/api/v1/admin/conversations/{conversation.id}/statement-imports',
            json={'statements': [
                '<b>New seed</b>', 'new seed', '=Formula', 'Approved seed',
            ]},
        )

    assert response.status_code == 200
    assert response.get_json()['data']['outcome'] == {
        'imported': 2,
        'skippedExisting': 1,
        'skippedDuplicateInput': 1,
        'failedUpstream': 0,
    }
    server.bulk_add_seeds.assert_called_once_with(
        conversation.polis_id, ['New seed', 'Formula'],
    )
    event = AuditEvent.query.filter_by(
        operation='statement.seed_import', conversation_id=conversation.id,
    ).one()
    assert event.detail['imported'] == 2


def test_seed_import_fails_closed_when_dedup_source_is_unavailable(
    admin_client, conversation,
):
    server, participant = _upstream()
    server.get_statements.return_value = None
    from polis_admin import PolisParticipantError
    participant.get_statements.side_effect = PolisParticipantError('offline')
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.post(
            f'/api/v1/admin/conversations/{conversation.id}/statement-imports',
            json={'statements': ['New seed']},
        )

    assert response.status_code == 503
    assert response.get_json()['error']['code'] == 'verification_unavailable'
    server.bulk_add_seeds.assert_not_called()


def test_seed_import_surfaces_safe_polis_configuration_error(
    admin_client, conversation,
):
    server, participant = _upstream()
    server.bulk_add_seeds.side_effect = PolisServerError(
        'internal configuration detail',
        admin_message=POLIS_NOT_CONFIGURED_MESSAGE,
    )
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.post(
            f'/api/v1/admin/conversations/{conversation.id}/statement-imports',
            json={'statements': ['New seed']},
        )

    assert response.status_code == 502
    assert response.get_json()['error']['message'] == POLIS_NOT_CONFIGURED_MESSAGE
    assert 'internal configuration detail' not in response.text


def test_seed_import_surfaces_safe_error_when_every_statement_post_fails(
    admin_client, conversation,
):
    server, participant = _upstream()
    server.bulk_add_seeds.return_value = (0, [(
        'New seed',
        PolisServerError(
            'connection refused', admin_message=POLIS_NOT_CONFIGURED_MESSAGE,
        ),
    )])
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.post(
            f'/api/v1/admin/conversations/{conversation.id}/statement-imports',
            json={'statements': ['New seed']},
        )

    assert response.status_code == 502
    assert response.get_json()['error']['message'] == POLIS_NOT_CONFIGURED_MESSAGE


def test_seed_import_rejects_invalid_batch_before_upstream_write(
    admin_client, conversation,
):
    server, participant = _upstream()
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = admin_client.post(
            f'/api/v1/admin/conversations/{conversation.id}/statement-imports',
            json={'statements': ['x' * 281]},
        )

    assert response.status_code == 400
    assert '280 characters' in response.get_json()['error']['message']
    server.bulk_add_seeds.assert_not_called()
