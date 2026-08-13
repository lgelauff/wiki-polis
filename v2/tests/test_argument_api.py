"""Argument-mapping read API contract tests."""

import json
from unittest.mock import patch

from db import (Argument, ArgumentSideState, ArgumentVote, AuditEvent,
                ContentFlag, Conversation, FeaturedStatement, Participation, db)


def _argument_fixture(participant):
    conversation = Conversation(
        slug='argument-api', polis_id='argapi1234', title='Argument API',
        active=True, access_policy='public', phase_argument_mapping=True,
        phase_submission=True, argument_vote_data={'K': 2},
    )
    db.session.add(conversation)
    db.session.flush()
    participation = Participation(
        participant_id=participant.id, conversation_id=conversation.id,
        pseudonym='careful-heron',
    )
    featured = FeaturedStatement(
        conversation_id=conversation.id, polis_statement_id=73,
        statement_text='Communities should share infrastructure.',
        confirmed_by_admin=True,
    )
    db.session.add_all([participation, featured])
    db.session.flush()
    arguments = [
        Argument(featured_statement_id=featured.id, side='pro', body=f'Pro {index}')
        for index in range(3)
    ]
    db.session.add_all(arguments)
    db.session.add(Argument(
        featured_statement_id=featured.id, side='con', body='Con 0',
    ))
    db.session.flush()
    db.session.add_all([
        ArgumentSideState(
            participant_id=participant.id, featured_statement_id=featured.id,
            side='pro', skipped=True, argument_order=[item.id for item in arguments],
        ),
        ArgumentSideState(
            participant_id=participant.id, featured_statement_id=featured.id,
            side='con', skipped=True, argument_order=[],
        ),
        ArgumentVote(argument_id=arguments[0].id, participant_id=participant.id),
    ])
    db.session.commit()
    return conversation, participation, featured, arguments


def test_argument_mapping_api_returns_explicit_gates_without_identity_or_tallies(
    auth_client, participant,
):
    conversation, participation, featured, arguments = _argument_fixture(participant)
    with patch('app._statement_text_map', return_value={}):
        response = auth_client.get('/api/v1/conversations/argument-api/arguments')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['progress'] == {
        'completed': 0,
        'total': 1,
        'allDone': False,
        'currentFeaturedStatementId': featured.id,
    }
    card = data['featuredStatements'][0]
    assert card['statement'] == {
        'id': 73, 'text': 'Communities should share infrastructure.',
    }
    assert card['sides']['pro']['contribution']['status'] == 'skipped'
    assert card['sides']['con']['contribution']['status'] == 'skipped'
    assert card['sides']['pro']['prioritization'] == {
        'available': True,
        'requiredArgumentCount': 3,
        'argumentCount': 3,
        'selectionBudget': 2,
        'selectedCount': 1,
        'complete': False,
    }
    assert card['sides']['con']['prioritization']['available'] is False
    assert card['sides']['pro']['arguments'][0]['selected'] is True
    assert 'importanceVoteCount' not in card['sides']['pro']['arguments'][0]
    assert data['links']['explore'] == '/app/conversations/argument-api/explore'
    serialized = json.dumps(data)
    assert participant.xid not in serialized
    assert participant.mw_username not in serialized
    assert participation.pseudonym in serialized
    assert conversation.polis_id not in serialized


def test_argument_mapping_api_hides_moderated_arguments(
    auth_client, participant,
):
    _conversation, _participation, _featured, arguments = _argument_fixture(participant)
    arguments[1].hidden = True
    db.session.commit()

    with patch('app._statement_text_map', return_value={}):
        data = auth_client.get(
            '/api/v1/conversations/argument-api/arguments',
        ).get_json()['data']

    visible = data['featuredStatements'][0]['sides']['pro']['arguments']
    assert [argument['body'] for argument in visible] == ['Pro 0', 'Pro 2']
    assert data['featuredStatements'][0]['sides']['pro'][
        'prioritization'
    ]['available'] is False


def test_argument_mapping_api_rejects_closed_phase_before_building_state(
    auth_client, participant,
):
    conversation, *_ = _argument_fixture(participant)
    conversation.phase_argument_mapping = False
    db.session.commit()

    with patch('app._build_featured_data') as build:
        response = auth_client.get('/api/v1/conversations/argument-api/arguments')

    assert response.status_code == 409
    build.assert_not_called()


def test_concurrent_participant_phases_advertise_both_activity_links(
    auth_client, participant,
):
    conversation, *_ = _argument_fixture(participant)
    with patch(
        'app.PolisServerClient.get_statements_remaining_bulk',
        return_value={conversation.polis_id: 2},
    ):
        data = auth_client.get('/api/v1/conversations').get_json()['data']

    card = data['groups']['needsAttention'][0]
    assert card['links']['explore'] == '/app/conversations/argument-api/explore'
    assert card['links']['arguments'] == '/app/conversations/argument-api/arguments'


def test_openapi_documents_argument_mapping_read(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths']['/conversations/{slug}/arguments']['get']

    assert operation['operationId'] == 'getArgumentMapping'
    argument = spec['components']['schemas']['ArgumentItem']['properties']
    assert 'importanceVoteCount' not in argument


def test_argument_submission_is_idempotent_for_same_body_and_conflicts_for_edit(
    auth_client, participant,
):
    _conversation, _participation, featured, _arguments = _argument_fixture(participant)
    path = (
        f'/api/v1/conversations/argument-api/featured-statements/'
        f'{featured.id}/arguments'
    )

    first = auth_client.post(path, json={
        'side': 'pro', 'body': '  Shared maintenance reduces duplicated work.  ',
    })
    replay = auth_client.post(path, json={
        'side': 'pro', 'body': 'Shared maintenance reduces duplicated work.',
    })
    conflict = auth_client.post(path, json={
        'side': 'pro', 'body': 'A different replacement argument.',
    })

    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.get_json() == replay.get_json()
    assert first.get_json()['data']['argument']['body'] == (
        'Shared maintenance reduces duplicated work.'
    )
    assert conflict.status_code == 409
    assert conflict.get_json()['error']['code'] == 'argument_already_submitted'
    assert Argument.query.filter_by(
        featured_statement_id=featured.id,
        proposer_pseudonym='careful-heron',
        side='pro',
    ).count() == 1


def test_argument_skip_put_is_idempotent(auth_client, participant):
    _conversation, _participation, featured, _arguments = _argument_fixture(participant)
    path = (
        f'/api/v1/conversations/argument-api/featured-statements/'
        f'{featured.id}/contributions/con/skip'
    )

    first = auth_client.put(path)
    replay = auth_client.put(path)

    assert first.status_code == replay.status_code == 200
    assert first.get_json()['data']['status'] == 'skipped'
    assert ArgumentSideState.query.filter_by(
        participant_id=participant.id,
        featured_statement_id=featured.id,
        side='con',
    ).count() == 1


def test_argument_priority_put_enforces_budget_and_allows_unselect(
    auth_client, participant,
):
    _conversation, _participation, _featured, arguments = _argument_fixture(participant)

    selected = auth_client.put(
        f'/api/v1/conversations/argument-api/arguments/{arguments[1].id}/priority',
        json={'selected': True},
    )
    over_budget = auth_client.put(
        f'/api/v1/conversations/argument-api/arguments/{arguments[2].id}/priority',
        json={'selected': True},
    )
    unselected = auth_client.put(
        f'/api/v1/conversations/argument-api/arguments/{arguments[0].id}/priority',
        json={'selected': False},
    )

    assert selected.status_code == 200
    assert selected.get_json()['data']['selectedCount'] == 2
    assert over_budget.status_code == 409
    assert over_budget.get_json()['error']['code'] == 'priority_budget_exceeded'
    assert unselected.status_code == 200
    assert unselected.get_json()['data']['selectedCount'] == 1


def test_argument_priority_put_enforces_minimum_visible_volume(
    auth_client, participant,
):
    _conversation, _participation, _featured, arguments = _argument_fixture(participant)
    arguments[2].hidden = True
    db.session.commit()

    response = auth_client.put(
        f'/api/v1/conversations/argument-api/arguments/{arguments[1].id}/priority',
        json={'selected': True},
    )

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'prioritization_unavailable'


def test_openapi_documents_argument_commands(client):
    spec = client.get('/api/v1/openapi.json').get_json()

    assert spec['paths'][
        '/conversations/{slug}/featured-statements/{featuredStatementId}/arguments'
    ]['post']['operationId'] == 'createArgument'
    assert spec['paths'][
        '/conversations/{slug}/featured-statements/{featuredStatementId}/contributions/{side}/skip'
    ]['put']['operationId'] == 'putArgumentContributionSkip'
    assert spec['paths'][
        '/conversations/{slug}/arguments/{argumentId}/priority'
    ]['put']['operationId'] == 'putArgumentPriority'


def test_content_flag_api_creates_and_deduplicates_argument_flag(
    auth_client, participant,
):
    _conversation, _participation, _featured, arguments = _argument_fixture(participant)
    payload = {
        'contentType': 'argument', 'targetId': arguments[1].id,
        'category': 'off_topic', 'detail': '<b>Needs review</b>',
    }

    first = auth_client.post(
        '/api/v1/conversations/argument-api/flags', json=payload,
    )
    replay = auth_client.post(
        '/api/v1/conversations/argument-api/flags', json=payload,
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.get_json()['data']['created'] is True
    assert replay.get_json()['data']['created'] is False
    assert ContentFlag.query.one().detail == 'Needs review'
    assert AuditEvent.query.filter_by(operation='content_flag.create').count() == 1


def test_content_flag_api_requires_explanation_for_other(
    auth_client, participant,
):
    _conversation, _participation, _featured, arguments = _argument_fixture(participant)

    response = auth_client.post(
        '/api/v1/conversations/argument-api/flags',
        json={
            'contentType': 'argument', 'targetId': arguments[1].id,
            'category': 'other', 'detail': ' ',
        },
    )

    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'validation_failed'
    assert ContentFlag.query.count() == 0


def test_content_flag_api_validates_statement_target(
    auth_client, participant,
):
    _argument_fixture(participant)
    with patch('app._statement_text_map', return_value={73: 'Known statement'}):
        response = auth_client.post(
            '/api/v1/conversations/argument-api/flags',
            json={
                'contentType': 'statement', 'targetId': 73,
                'category': 'privacy',
            },
        )

    assert response.status_code == 201
    assert ContentFlag.query.one().statement_tid == 73
