"""Meta statements (#415, #416): the flag is set on seeds only and survives moderation.

A meta statement asks about the participant, not the topic. Polis keeps it out of
clustering; we keep it out of Featured and the informed round, and a participant
cannot reword it.
"""
from unittest.mock import MagicMock, patch

import pytest

from db import AuditEvent, CommandReceipt, FeaturedStatement, db
from polis_admin import (
    _FEATURED_CANDIDATES_SQL, _STATEMENTS_SQL,
    PolisServerClient, PolisServerError,
)
from tests.test_explore_api import _join, _store_upstream_session


# ── Polis client: moderation keeps the flags it does not change ───────────────

def _db_client():
    return PolisServerClient('http://polis:8001', 'admin@test.com', 'pass',
                             db_url='postgresql://localhost/polis')


def _put_payload(client, flags_row, call):
    sess = MagicMock()
    sess.put.return_value = MagicMock(ok=True)
    with (
        patch.object(PolisServerClient, '_login', return_value=(sess, {})),
        patch.object(client, '_pg_query', return_value=flags_row) as query,
    ):
        call(client)
    return sess, query


def test_moderating_a_meta_statement_leaves_it_meta():
    client = _db_client()
    # (tid, active, mod, is_meta, is_seed)
    sess, _ = _put_payload(client, [(7, True, 1, True, True)],
                           lambda c: c.moderate('abc123', 7, -1))
    payload = sess.put.call_args.kwargs['json']
    assert payload['is_meta'] is True
    assert payload['mod'] == -1
    assert payload['active'] is True


def test_moderating_an_inactive_statement_does_not_reactivate_it():
    client = _db_client()
    sess, _ = _put_payload(client, [(7, False, 0, False, False)],
                           lambda c: c.moderate('abc123', 7, 1))
    assert sess.put.call_args.kwargs['json']['active'] is False


@pytest.mark.parametrize('rows', [None, []])
def test_moderation_refuses_when_the_current_flags_cannot_be_read(rows):
    client = _db_client()
    sess = MagicMock()
    with (
        patch.object(PolisServerClient, '_login', return_value=(sess, {})),
        patch.object(client, '_pg_query', return_value=rows),
        pytest.raises(PolisServerError),
    ):
        client.moderate('abc123', 7, 1)
    sess.put.assert_not_called()


def test_moderation_refuses_without_a_polis_database():
    client = PolisServerClient('http://polis:8001', 'a@b.com', 'pw', db_url='')
    sess = MagicMock()
    with (
        patch.object(PolisServerClient, '_login', return_value=(sess, {})),
        pytest.raises(PolisServerError),
    ):
        client.moderate('abc123', 7, 1)
    sess.put.assert_not_called()


def test_set_meta_keeps_moderation_and_active():
    client = _db_client()
    sess, query = _put_payload(client, [(7, False, -1, False, True)],
                               lambda c: c.set_meta('abc123', 7, True))
    payload = sess.put.call_args.kwargs['json']
    assert payload == {
        'conversation_id': 'abc123', 'tid': 7, 'mod': -1, 'active': False,
        'is_meta': True, 'velocity': 0.5,
    }
    assert query.call_args.args[1] == ('abc123', 7)


def test_statement_rows_carry_meta_and_responses_by_others():
    client = _db_client()
    row = (7, 'I would stand as a candidate', 1, True, 3, 1, 2, True, True)
    with patch.object(client, '_pg_query', return_value=[row]):
        _pending, approved, _hidden = client.get_statements('abc123')
    assert approved[0]['is_meta'] is True
    assert approved[0]['has_responses'] is True


def test_meta_statements_are_never_featured_candidates():
    sql = ' '.join(_FEATURED_CANDIDATES_SQL.split())
    assert 'c.is_meta = FALSE' in sql
    # The admin list still shows them, so moderators can see and unmark them.
    assert 'is_meta = FALSE' not in ' '.join(_STATEMENTS_SQL.split())
    # A seed carries its author's own pass, so "responses" means someone else's.
    assert 'o.pid <> c.pid' in ' '.join(_STATEMENTS_SQL.split())


# ── Admin API: marking a seed ────────────────────────────────────────────────

def _rows(*, seed=True, meta=False, responses=False):
    return (
        [],
        [{'tid': 12, 'txt': 'I would stand as a candidate', 'mod': 1,
          'is_seed': seed, 'is_meta': meta, 'has_responses': responses,
          'agree_count': 0, 'pass_count': 0, 'disagree_count': 0}],
        [],
    )


def _put_meta(client, conversation, rows, body):
    server = MagicMock()
    server.get_statements.return_value = rows
    participant = MagicMock()
    participant.get_settings.return_value = {'strict_moderation': True}
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=participant),
    ):
        response = client.put(
            f'/api/v1/admin/conversations/{conversation.id}/statements/12/meta',
            json=body,
        )
    return response, server


def test_moderator_marks_a_seed_as_meta(admin_client, conversation):
    response, server = _put_meta(admin_client, conversation, _rows(), {'meta': True})
    assert response.status_code == 200
    assert response.get_json()['data']['meta'] is True
    assert response.get_json()['data']['changed'] is True
    server.set_meta.assert_called_once_with(conversation.polis_id, 12, True)
    event = AuditEvent.query.filter_by(operation='statement.meta').one()
    assert event.target_id == '12'


def test_a_participant_statement_cannot_be_meta(admin_client, conversation):
    response, server = _put_meta(admin_client, conversation, _rows(seed=False),
                                 {'meta': True})
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'meta_not_seed'
    server.set_meta.assert_not_called()


def test_a_statement_with_responses_changes_only_after_the_warning(
    admin_client, conversation,
):
    refused, server = _put_meta(admin_client, conversation, _rows(responses=True),
                                {'meta': True})
    assert refused.status_code == 409
    assert refused.get_json()['error']['code'] == 'meta_has_responses'
    server.set_meta.assert_not_called()

    allowed, server = _put_meta(admin_client, conversation, _rows(responses=True),
                                {'meta': True, 'acknowledgeResponses': True})
    assert allowed.status_code == 200
    server.set_meta.assert_called_once_with(conversation.polis_id, 12, True)


def test_unmarking_needs_the_warning_too(admin_client, conversation):
    refused, server = _put_meta(
        admin_client, conversation, _rows(meta=True, responses=True), {'meta': False},
    )
    assert refused.status_code == 409
    server.set_meta.assert_not_called()


def test_a_featured_statement_cannot_be_marked_meta(admin_client, conversation):
    db.session.add(FeaturedStatement(
        conversation_id=conversation.id, polis_statement_id=12,
        statement_text='I would stand as a candidate', confirmed_by_admin=True,
    ))
    db.session.commit()
    response, server = _put_meta(admin_client, conversation, _rows(), {'meta': True})
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'meta_featured'
    server.set_meta.assert_not_called()


def test_no_change_writes_nothing(admin_client, conversation):
    response, server = _put_meta(admin_client, conversation, _rows(meta=True),
                                 {'meta': True})
    assert response.status_code == 200
    assert response.get_json()['data']['changed'] is False
    server.set_meta.assert_not_called()
    assert AuditEvent.query.filter_by(operation='statement.meta').count() == 0


def test_upstream_failure_changes_nothing(admin_client, conversation):
    server = MagicMock()
    server.get_statements.return_value = _rows()
    server.set_meta.side_effect = PolisServerError('down')
    with (
        patch('app._polis_server_client', return_value=server),
        patch('app.PolisParticipantClient', return_value=MagicMock()),
    ):
        response = admin_client.put(
            f'/api/v1/admin/conversations/{conversation.id}/statements/12/meta',
            json={'meta': True},
        )
    assert response.status_code == 502
    assert AuditEvent.query.filter_by(operation='statement.meta').count() == 0


@pytest.mark.parametrize('body', [{}, {'meta': 'yes'}, {'meta': True, 'extra': 1},
                                  {'meta': True, 'acknowledgeResponses': 'yes'}])
def test_meta_request_is_validated(admin_client, conversation, body):
    response, server = _put_meta(admin_client, conversation, _rows(), body)
    assert response.status_code == 400
    server.set_meta.assert_not_called()


# ── Admin API: a seed added as meta ──────────────────────────────────────────

def _post_seed(client, conversation, server, body):
    with patch('app._polis_server_client', return_value=server):
        return client.post(
            f'/api/v1/admin/conversations/{conversation.id}/statements', json=body,
        )


def test_seed_added_as_meta_is_marked_in_a_second_write(admin_client, conversation):
    server = MagicMock()
    server.add_seed_return_id.return_value = 42
    response = _post_seed(admin_client, conversation, server, {
        'text': 'I would stand as a candidate', 'derivedFromId': None, 'isMeta': True,
    })
    assert response.status_code == 201
    assert response.get_json()['data']['metaRecorded'] is True
    assert response.get_json()['data']['statementId'] == 42
    server.add_seed.assert_not_called()
    server.set_meta.assert_called_once_with(conversation.polis_id, 42, True)
    assert AuditEvent.query.filter_by(operation='statement.meta').count() == 1


def test_seed_whose_meta_mark_fails_is_reported_unmarked(admin_client, conversation):
    server = MagicMock()
    server.add_seed_return_id.return_value = 42
    server.set_meta.side_effect = PolisServerError('down')
    response = _post_seed(admin_client, conversation, server, {
        'text': 'I would stand as a candidate', 'derivedFromId': None, 'isMeta': True,
    })
    assert response.status_code == 201
    assert response.get_json()['data']['metaRecorded'] is False
    assert AuditEvent.query.filter_by(operation='statement.meta').count() == 0


def test_seed_request_rejects_a_non_boolean_meta(admin_client, conversation):
    server = MagicMock()
    response = _post_seed(admin_client, conversation, server, {
        'text': 'Seed', 'derivedFromId': None, 'isMeta': 'yes',
    })
    assert response.status_code == 400
    server.add_seed.assert_not_called()
    server.add_seed_return_id.assert_not_called()


# ── Featured and the participant side ────────────────────────────────────────

def test_a_meta_statement_cannot_be_featured(admin_client, conversation):
    with patch('app._statement_text_and_meta',
               return_value=({12: 'I would stand as a candidate'}, {12})):
        response = admin_client.put(
            f'/api/v1/admin/conversations/{conversation.id}/featured-statements/12',
            json={'source': 'manual'},
        )
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'meta_not_featurable'
    assert FeaturedStatement.query.filter_by(conversation_id=conversation.id).count() == 0


def test_a_participant_cannot_reword_a_meta_statement(
    auth_client, participant, conversation,
):
    _join(participant, conversation)
    _store_upstream_session(auth_client, conversation)
    with (
        patch('app._statement_text_and_meta',
              return_value=({7: 'I would stand as a candidate'}, {7})),
        patch('app.polis_http.post') as upstream_post,
    ):
        response = auth_client.post(
            '/api/v1/conversations/test-conv/statements',
            json={'text': 'I might stand as a candidate', 'derivedFromStatementId': 7},
            headers={'Idempotency-Key': 'statement-key-meta-1'},
        )
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'meta_not_rewordable'
    upstream_post.assert_not_called()
    assert CommandReceipt.query.filter_by(state='pending').count() == 0


def test_explore_offers_no_rewording_on_a_meta_statement(
    auth_client, participant, conversation,
):
    """The participant card hides "Suggest different wording" from this capability."""
    from tests.test_explore_api import _response
    _join(participant, conversation)
    session_response = _response(
        {'csrf_token': 'upstream-csrf'}, cookies={'session': 'upstream-cookie'},
    )
    statements = _response({
        '1': {'id': 1, 'text': 'I would stand as a candidate', 'is_meta': True, 'is_seed': True},
        '2': {'id': 2, 'text': 'An opinion', 'is_seed': True},
    })
    with (
        patch('app.polis_http.post', return_value=session_response),
        patch('app.polis_http.get', side_effect=[
            statements, _response({'votes': [], 'statements': []}),
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    data = response.get_json()['data']
    assert data['currentStatement']['isMeta'] is True  # meta statements come first
    assert data['capabilities']['suggestWording'] is False
