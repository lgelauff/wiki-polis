"""Typed participant join command contract tests."""

from unittest.mock import patch

from db import ConversationInvite, Participant, Participation, db


def test_participation_entry_describes_the_legacy_join_form(
    auth_client, participant, conversation,
):
    conversation.intro_text = '<p>Join this discussion.</p>'
    conversation.eligibility_label = 'Extended-confirmed editors'
    db.session.commit()

    response = auth_client.get(
        '/api/v1/conversations/test-conv/participation-entry',
    )

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()['data']
    assert data['state'] == 'join'
    assert data['conversation'] == {
        'id': conversation.id,
        'slug': 'test-conv',
        'title': 'Test Conversation',
        'descriptionHtml': '<p>Join this discussion.</p>',
        'eligibilityLabel': 'Extended-confirmed editors',
    }
    assert len(data['pseudonyms']) == 5
    assert data['emailable'] is True
    assert data['reveal'] == {'cooldownDays': 30, 'windowEndDays': 60}
    assert data['links'] == {'home': '/', 'conversation': '/c/test-conv'}


def test_participation_entry_returns_route_redirect_for_existing_participant(
    auth_client, participant, conversation,
):
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='joined-otter',
    ))
    db.session.commit()

    response = auth_client.get(
        '/api/v1/conversations/test-conv/participation-entry',
    )

    assert response.get_json()['data'] == {
        'state': 'redirect',
        'reason': 'already_participating',
        'href': '/c/test-conv',
    }


def test_participation_entry_exposes_invite_denial_as_route_state(
    auth_client, participant, conversation,
):
    conversation.access_policy = 'invite_only'
    db.session.commit()

    denied = auth_client.get(
        '/api/v1/conversations/test-conv/participation-entry',
    )
    assert denied.status_code == 200
    data = denied.get_json()['data']
    assert data['state'] == 'invite_denied'
    assert data['conversation']['title'] == 'Test Conversation'
    assert data['canModerate'] is False
    assert data['links'] == {'home': '/', 'manageInvites': None}

    db.session.add(ConversationInvite(
        conversation_id=conversation.id,
        mw_username=participant.mw_username,
    ))
    db.session.commit()
    allowed = auth_client.get(
        '/api/v1/conversations/test-conv/participation-entry',
    )
    assert allowed.get_json()['data']['state'] == 'join'


def test_join_command_creates_participation_and_filters_email_preference(
    auth_client, participant, conversation,
):
    with auth_client.session_transaction() as sess:
        sess['emailable'] = False

    response = auth_client.post(
        '/api/v1/conversations/test-conv/participation',
        json={
            'pseudonym': 'calm-otter',
            'notifyEmail': True,
            'notifyTalkPage': True,
        },
    )

    assert response.status_code == 201
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.get_json()['data'] == {
        'pseudonym': 'calm-otter',
        'notifications': {'email': False, 'talkPage': True},
        'eligibilityStatus': 'not_required',
        'links': {
            'conversation': '/c/test-conv',
            'about': '/c/test-conv/about',
        },
    }
    participation = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conversation.id,
    ).one()
    assert participation.pseudonym == 'calm-otter'


def test_join_command_replay_returns_existing_participation_without_rechecking(
    auth_client, participant, conversation,
):
    existing = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='first-otter',
        eligibility_status='eligible',
    )
    db.session.add(existing)
    db.session.commit()

    with patch('app._check_join_eligibility') as eligibility:
        response = auth_client.post(
            '/api/v1/conversations/test-conv/participation',
            json={'pseudonym': 'other-otter'},
        )

    assert response.status_code == 200
    assert response.get_json()['data']['pseudonym'] == 'first-otter'
    eligibility.assert_not_called()
    assert Participation.query.count() == 1


def test_join_command_returns_field_validation_errors(auth_client, conversation):
    response = auth_client.post(
        '/api/v1/conversations/test-conv/participation',
        json={'pseudonym': 'Bad name', 'unexpected': True},
    )

    assert response.status_code == 400
    error = response.get_json()['error']
    assert error['code'] == 'validation_failed'
    assert error['details']['fields']['_request'] == ['Unknown field: unexpected.']


def test_join_command_returns_pseudonym_conflict(
    auth_client, conversation,
):
    owner = Participant(
        mw_user_id=1234,
        mw_username='pseudonym-owner',
        xid='p' * 64,
    )
    db.session.add(owner)
    db.session.flush()
    db.session.add(Participation(
        participant_id=owner.id,
        conversation_id=conversation.id,
        pseudonym='taken-otter',
    ))
    db.session.commit()

    response = auth_client.post(
        '/api/v1/conversations/test-conv/participation',
        json={'pseudonym': 'taken-otter'},
    )

    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'pseudonym_unavailable'


def test_join_command_requires_authentication(client, conversation):
    response = client.post(
        '/api/v1/conversations/test-conv/participation',
        json={'pseudonym': 'calm-otter'},
    )

    assert response.status_code == 401
    assert response.get_json()['error']['code'] == 'unauthorized'


def test_join_command_returns_typed_eligibility_denial(
    auth_client, conversation,
):
    conversation.eligibility_event_id = 'extended-confirmed'
    db.session.commit()

    with patch(
        'app._check_join_eligibility',
        return_value=(False, 'ineligible', {'reason': 'Not enough edits'}),
    ):
        response = auth_client.post(
            '/api/v1/conversations/test-conv/participation',
            json={'pseudonym': 'calm-otter'},
        )

    assert response.status_code == 403
    assert response.get_json() == {
        'error': {
            'code': 'eligibility_denied',
            'message': 'This account does not meet the participation criteria.',
            'details': {
                'status': 'ineligible',
                'displayMessage': 'Not enough edits',
            },
        },
    }
    assert Participation.query.count() == 0


def test_pseudonym_suggestions_require_authentication(client, conversation):
    denied = client.get(
        '/api/v1/conversations/test-conv/pseudonym-suggestions',
    )

    assert denied.status_code == 401


def test_pseudonym_suggestions_match_contract(auth_client, conversation):
    response = auth_client.get(
        '/api/v1/conversations/test-conv/pseudonym-suggestions',
    )

    assert response.status_code == 200
    suggestions = response.get_json()['data']['pseudonyms']
    assert len(suggestions) == 5
    assert all('-' in item for item in suggestions)


def test_openapi_documents_join_idempotency(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    operation = spec['paths']['/conversations/{slug}/participation']['post']

    assert operation['operationId'] == 'createParticipation'
    assert 'Idempotent' in operation['description']
    assert set(operation['responses']) >= {'200', '201', '400', '401', '403', '409'}
