"""Featured statement administration API contract tests."""

from unittest.mock import MagicMock, patch

from db import AdminRole, Argument, AuditEvent, FeaturedStatement, db
from tests.conftest import login


def _candidate(statement_id=12):
    return {
        'tid': statement_id,
        'text': 'A candidate statement',
        'is_seed': True,
        'n_agree': 3,
        'n_pass': 2,
        'n_disagree': 1,
        'n_votes': 6,
    }


def test_featured_workspace_reports_transparent_candidate_metrics(
    admin_client, conversation,
):
    selected = FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=11,
        statement_text='Selected statement',
        confirmed_by_admin=True,
    )
    db.session.add(selected)
    db.session.flush()
    db.session.add(Argument(
        featured_statement_id=selected.id,
        proposer_pseudonym='quiet-otter',
        body='Supporting context',
        side='pro',
    ))
    db.session.commit()
    server = MagicMock()
    server.get_featured_candidates.return_value = [_candidate()]
    with patch('app._polis_server_client', return_value=server):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/featured-statements',
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['dataAvailability'] == {'candidates': True}
    assert data['guidance']['recommendedCount'] == 15
    assert data['candidates'][0]['votes'] == {
        'agree': 3, 'pass': 2, 'disagree': 1, 'total': 6,
        'agreementPercent': 75.0,
    }
    assert data['selected'][0]['arguments'][0]['proposerPseudonym'] == 'quiet-otter'
    assert 'participant_id' not in response.text
    assert 'divisiv' not in response.text.lower()


def test_candidate_unavailability_is_distinct_from_empty(
    admin_client, conversation,
):
    server = MagicMock()
    server.get_featured_candidates.return_value = None
    with patch('app._polis_server_client', return_value=server):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/featured-statements',
        )

    data = response.get_json()['data']
    assert data['dataAvailability']['candidates'] is False
    assert data['candidates'] == []


def test_scoped_moderator_selects_verified_statement_idempotently(
    client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='moderator',
    ))
    db.session.commit()
    login(client, 'testuser')
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}/featured-statements/12'
    )
    with patch('app._statement_text_map', return_value={12: 'Verified text'}):
        first = client.put(endpoint, json={'source': 'system'})
        replay = client.put(endpoint, json={'source': 'system'})

    assert first.status_code == replay.status_code == 200
    assert first.get_json()['data']['changed'] is True
    assert replay.get_json()['data']['changed'] is False
    row = FeaturedStatement.query.filter_by(
        conversation_id=conversation.id, polis_statement_id=12,
    ).one()
    assert row.statement_text == 'Verified text'
    assert row.suggested_by_system is True
    assert AuditEvent.query.filter_by(
        operation='featured.select', conversation_id=conversation.id,
    ).count() == 1


def test_select_rejects_unknown_statement_and_rolls_back_failed_live_sync(
    admin_client, conversation,
):
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}/featured-statements/12'
    )
    with patch('app._statement_text_map', return_value={}):
        unknown = admin_client.put(endpoint, json={'source': 'manual'})

    conversation.phase_informed_voting = True
    conversation.phase6_polis_conversation_id = 'phase6round'
    db.session.commit()
    with (
        patch('app._statement_text_map', return_value={12: 'Verified text'}),
        patch('app._sync_phase6_featured', return_value=(False, 'sync offline')),
    ):
        failed = admin_client.put(endpoint, json={'source': 'manual'})

    assert unknown.status_code == 404
    assert failed.status_code == 502
    assert failed.get_json()['error']['message'] == 'sync offline'
    assert FeaturedStatement.query.filter_by(
        conversation_id=conversation.id, polis_statement_id=12,
    ).first() is None


def test_remove_selection_enforces_last_featured_invariant(
    admin_client, conversation,
):
    conversation.phase_argument_mapping = True
    selected = FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=11,
        statement_text='Selected statement',
        confirmed_by_admin=True,
    )
    db.session.add(selected)
    db.session.commit()
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}/featured-selections/{selected.id}'
    )

    protected = admin_client.delete(endpoint)
    second = FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=12,
        statement_text='Second statement',
        confirmed_by_admin=True,
    )
    db.session.add(second)
    db.session.commit()
    removed = admin_client.delete(endpoint)

    assert protected.status_code == 409
    assert removed.status_code == 200
    assert removed.get_json()['data']['removed'] is True
    assert db.session.get(FeaturedStatement, selected.id) is None


def test_argument_visibility_is_idempotent_and_audited(
    admin_client, conversation,
):
    selected = FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=11,
        statement_text='Selected statement',
        confirmed_by_admin=True,
    )
    db.session.add(selected)
    db.session.flush()
    argument = Argument(
        featured_statement_id=selected.id,
        body='Supporting context', side='pro', hidden=False,
    )
    db.session.add(argument)
    db.session.commit()
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}/featured-arguments/{argument.id}'
    )

    first = admin_client.put(endpoint, json={'hidden': True})
    replay = admin_client.put(endpoint, json={'hidden': True})

    assert first.status_code == replay.status_code == 200
    assert first.get_json()['data']['changed'] is True
    assert replay.get_json()['data']['changed'] is False
    assert db.session.get(Argument, argument.id).hidden is True
    assert AuditEvent.query.filter_by(
        operation='argument.moderate', conversation_id=conversation.id,
    ).count() == 1


def test_argument_deletion_is_conversation_scoped(admin_client, conversation):
    selected = FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=11,
        statement_text='Selected statement',
        confirmed_by_admin=True,
    )
    db.session.add(selected)
    db.session.flush()
    argument = Argument(
        featured_statement_id=selected.id,
        body='Supporting context', side='pro', hidden=False,
    )
    db.session.add(argument)
    db.session.commit()
    endpoint = (
        f'/api/v1/admin/conversations/{conversation.id}/featured-arguments/{argument.id}'
    )

    missing = admin_client.delete(endpoint.replace(
        f'conversations/{conversation.id}', 'conversations/999',
    ))
    removed = admin_client.delete(endpoint)

    assert missing.status_code == 404
    assert removed.status_code == 200
    assert removed.get_json()['data']['deleted'] is True
    assert db.session.get(Argument, argument.id) is None
