"""Conversation About HTML and API contract tests (#277)."""

import json
from unittest.mock import patch

from db import (Argument, ArgumentVote, ConversationInvite, FeaturedStatement,
                Participation, db)


def _join(participant, conversation, *, pseudonym='about-otter', new_stmt_ids=None):
    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym=pseudonym,
        new_stmt_ids=new_stmt_ids or [],
    )
    db.session.add(participation)
    db.session.commit()
    return participation


def test_about_api_combines_public_record_and_personal_contributions(
    auth_client, participant, conversation,
):
    conversation.intro_text = '<p>A <strong>shared</strong> description.</p>'
    conversation.outro_text = '<p>Thank you for taking part.</p>'
    conversation.phase_submission = True
    participation = _join(
        participant, conversation, new_stmt_ids=[101, 102],
    )
    statement = FeaturedStatement(
        conversation_id=conversation.id,
        polis_statement_id=8,
        statement_text='A featured statement',
    )
    db.session.add(statement)
    db.session.flush()
    argument = Argument(
        featured_statement_id=statement.id,
        proposer_pseudonym=participation.pseudonym,
        body='A useful reason',
        side='pro',
    )
    db.session.add(argument)
    db.session.flush()
    db.session.add(ArgumentVote(
        argument_id=argument.id,
        participant_id=participant.id,
    ))
    db.session.commit()

    with (
        patch('app.PolisServerClient.get_polis_stats', return_value={
            'n_participants': 14,
            'n_votes': 86,
            'n_statements': 12,
        }),
        patch(
            'app.PolisServerClient.get_statement_progress_bulk',
            return_value={conversation.polis_id: {'voted': 7}},
        ),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/about')

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()['data']
    assert data['space'] == 'real'
    assert data['descriptionHtml'] == '<p>A <strong>shared</strong> description.</p>'
    assert data['phases'] == [{'key': 'submission', 'label': 'Explore'}]
    assert data['pseudonym'] == 'about-otter'
    assert data['statistics'] == {
        'participants': 14,
        'statementVotes': 86,
        'statements': 12,
        'arguments': 1,
        'argumentContributors': 1,
    }
    assert data['personal'] == {
        'statementsSuggested': 2,
        'statementVotes': 7,
        'statementVotesAvailable': True,
        'argumentsAdded': 1,
        'argumentsRated': 1,
    }
    assert data['capabilities'] == {'participate': True, 'moderate': False}
    assert data['links'] == {
        'self': '/api/v1/conversations/test-conv/about',
        'conversation': '/c/test-conv',
    }
    serialized = json.dumps(data)
    assert conversation.polis_id not in serialized
    assert participant.xid not in serialized
    assert str(participant.mw_user_id) not in serialized


def test_about_remains_available_when_polis_statistics_are_down(
    client, conversation,
):
    with patch(
        'app.PolisServerClient.get_polis_stats',
        side_effect=RuntimeError('polis unavailable'),
    ):
        response = client.get('/api/v1/conversations/test-conv/about')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['statistics'] == {
        'participants': None,
        'statementVotes': None,
        'statements': None,
        'arguments': 0,
        'argumentContributors': 0,
    }
    assert data['personal'] is None


def test_invite_only_about_uses_structured_api_denial(
    auth_client, conversation,
):
    conversation.access_policy = 'invite_only'
    db.session.commit()

    response = auth_client.get('/api/v1/conversations/test-conv/about')

    assert response.status_code == 403
    assert response.is_json
    assert response.get_json()['error']['code'] == 'forbidden'


def test_invited_participant_can_view_about(
    auth_client, participant, conversation,
):
    conversation.access_policy = 'invite_only'
    db.session.add(ConversationInvite(
        conversation_id=conversation.id,
        mw_username=participant.mw_username,
    ))
    db.session.commit()

    response = auth_client.get('/api/v1/conversations/test-conv/about')

    assert response.status_code == 200
    assert response.get_json()['data']['title'] == 'Test Conversation'


def test_main_conversation_persistently_links_about_not_moderation_log(
    auth_client, participant, conversation,
):
    """The conversation surface offers About; the moderation log hangs off About.

    The page asserted this as nav markup. The same routing decision is made by the
    server: the workspace payload carries an About link and no moderation-log link,
    and the moderation log is reachable only from the About payload.
    """
    _join(participant, conversation)

    workspace = auth_client.get('/api/v1/conversations/test-conv/workspace')
    assert workspace.status_code == 200
    links = workspace.get_json()['data']['links']

    assert links['about'] == '/c/test-conv/about'
    assert not any('moderation-log' in href for href in links.values())

    about = auth_client.get('/api/v1/conversations/test-conv/about')
    assert about.get_json()['data']['moderation']['href'] == '/c/test-conv/moderation-log'


def test_openapi_describes_conversation_about(client):
    spec = client.get('/api/v1/openapi.json').get_json()

    operation = spec['paths']['/conversations/{slug}/about']['get']
    assert operation['operationId'] == 'getConversationAbout'
    assert (
        operation['responses']['200']['content']['application/json']['schema']['$ref']
        == '#/components/schemas/ConversationAboutResponse'
    )
