"""Admin termination inspection and deletion contract tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db import AdminRole, AuditEvent, Conversation, db
from services.admin_termination import DeletionOutcomeUnknown, delete_empty_conversation
from tests.conftest import login


def test_termination_contract_recommends_archive_when_votes_exist(
    admin_client, conversation,
):
    server = MagicMock()
    server.get_valid_vote_count.return_value = 3
    with patch('app._polis_server_client', return_value=server):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conversation.id}/termination',
        )

    assert response.status_code == 200
    assert response.get_json()['data']['deletion'] == {
        'state': 'blocked_by_votes',
        'validVoteCount': 3,
        'reason': 'Conversations with votes are retained; archive it instead.',
    }
    assert conversation.polis_id not in response.text


def test_delete_api_rechecks_then_hides_and_deletes_empty_conversation(
    admin_client, conversation,
):
    conversation_id = conversation.id
    server = MagicMock()
    server.get_valid_vote_count.return_value = 0
    with patch('app._polis_server_client', return_value=server):
        response = admin_client.delete(
            f'/api/v1/admin/conversations/{conversation_id}',
        )

    assert response.status_code == 200
    assert response.get_json()['data'] == {
        'conversationId': conversation_id,
        'deleted': True,
        'links': {'admin': '/admin'},
    }
    assert db.session.get(Conversation, conversation_id) is None
    server.close_and_hide_conversation.assert_called_once()
    event = AuditEvent.query.filter_by(operation='conversation.delete').one()
    assert event.conversation_id is None
    assert event.target_id == str(conversation_id)
    assert event.detail['valid_vote_count'] == 0


def test_delete_api_blocks_votes_and_verification_failure(
    admin_client, conversation,
):
    endpoint = f'/api/v1/admin/conversations/{conversation.id}'
    server = MagicMock()
    server.get_valid_vote_count.return_value = 2
    with patch('app._polis_server_client', return_value=server):
        blocked = admin_client.delete(endpoint)
    server.get_valid_vote_count.return_value = None
    with patch('app._polis_server_client', return_value=server):
        unavailable = admin_client.delete(endpoint)

    assert blocked.status_code == 409
    assert blocked.get_json()['error']['details'] == {'validVoteCount': 2}
    assert unavailable.status_code == 503
    assert db.session.get(Conversation, conversation.id) is not None
    server.close_and_hide_conversation.assert_not_called()


def test_delete_api_preserves_local_record_when_upstream_hide_fails(
    admin_client, conversation,
):
    endpoint = f'/api/v1/admin/conversations/{conversation.id}'
    server = MagicMock()
    server.get_valid_vote_count.return_value = 0
    from polis_admin import PolisServerError
    server.close_and_hide_conversation.side_effect = PolisServerError('offline')

    with patch('app._polis_server_client', return_value=server):
        response = admin_client.delete(endpoint)

    assert response.status_code == 502
    assert response.get_json()['error']['code'] == 'upstream_unavailable'
    assert db.session.get(Conversation, conversation.id) is not None


def test_scoped_organizer_cannot_inspect_or_delete_conversation(
    client, conversation, participant,
):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='organizer',
    ))
    db.session.commit()
    login(client, 'testuser')
    termination = (
        f'/api/v1/admin/conversations/{conversation.id}/termination'
    )

    assert client.get(termination).status_code == 403
    assert client.delete(
        f'/api/v1/admin/conversations/{conversation.id}',
    ).status_code == 403


def test_deletion_reports_unknown_outcome_after_upstream_hide_and_commit_failure():
    conversation = SimpleNamespace(id=17, slug='empty', polis_id='polis-17')
    session = MagicMock()
    session.commit.side_effect = SQLAlchemyError('database offline')
    hide_upstream = MagicMock()
    delete_local = MagicMock()
    audit_deleted = MagicMock()

    with pytest.raises(DeletionOutcomeUnknown):
        delete_empty_conversation(
            conversation=conversation,
            valid_vote_count=0,
            hide_upstream=hide_upstream,
            delete_local=delete_local,
            session=session,
            audit_deleted=audit_deleted,
            upstream_errors=(RuntimeError,),
        )

    hide_upstream.assert_called_once_with('polis-17')
    delete_local.assert_called_once_with(conversation)
    session.rollback.assert_called_once_with()
    audit_deleted.assert_not_called()


def test_deletion_reports_unknown_outcome_when_local_delete_cannot_be_staged():
    conversation = SimpleNamespace(id=18, slug='empty', polis_id='polis-18')
    session = MagicMock()
    delete_local = MagicMock(side_effect=SQLAlchemyError('constraint failure'))

    with pytest.raises(DeletionOutcomeUnknown):
        delete_empty_conversation(
            conversation=conversation,
            valid_vote_count=0,
            hide_upstream=MagicMock(),
            delete_local=delete_local,
            session=session,
            audit_deleted=MagicMock(),
            upstream_errors=(RuntimeError,),
        )

    session.commit.assert_not_called()
    session.rollback.assert_called_once_with()
