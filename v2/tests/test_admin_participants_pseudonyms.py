"""Who sees whose username on the admin participant roster (owner decision, 2026-10-08).

Moderators know people only by the pseudonym they take part under: the roster sends a
moderator-only viewer no username at all, and does not order the rows by one either.
Organizers and site admins keep the username, as they had on main.
"""

import json
from datetime import datetime, timezone

from db import AdminRole, Participant, Participation, db
from tests.conftest import _xid, login


def _person(user_id, username, conversation, pseudonym):
    person = Participant(mw_user_id=user_id, mw_username=username, xid=_xid(user_id))
    db.session.add(person)
    db.session.flush()
    db.session.add(Participation(
        conversation_id=conversation.id, participant_id=person.id, pseudonym=pseudonym,
        last_engagement=datetime(2026, 8, 13, 9, 30, tzinfo=timezone.utc),
    ))
    db.session.commit()
    return person


def _roster_as(client, conversation, role):
    viewer = _person(70001, 'Viewer account', conversation, 'zz-viewer')
    db.session.add(AdminRole(
        participant_id=viewer.id, conversation_id=conversation.id, role=role,
    ))
    db.session.commit()
    login(client, 'Viewer account')
    response = client.get(f'/api/v1/admin/conversations/{conversation.id}/participants')
    assert response.status_code == 200
    return response.get_json()['data']['participants']


def _two_people(conversation):
    # Username order and pseudonym order disagree, so the row order can be told apart.
    _person(70002, 'Aaron Example', conversation, 'quiet-otter')
    _person(70003, 'Zelda Example', conversation, 'amber-fox')


def test_a_moderator_only_viewer_gets_pseudonyms_and_no_username(client, conversation):
    _two_people(conversation)

    rows = _roster_as(client, conversation, 'moderator')

    assert [row['username'] for row in rows] == [None, None, None]
    assert [row['pseudonym'] for row in rows] == ['amber-fox', 'quiet-otter', 'zz-viewer']
    serialized = json.dumps(rows)
    for username in ('Aaron Example', 'Zelda Example', 'Viewer account'):
        assert username not in serialized


def test_an_organizer_keeps_the_usernames(client, conversation):
    _two_people(conversation)

    rows = _roster_as(client, conversation, 'organizer')

    assert [row['username'] for row in rows] == [
        'Aaron Example', 'Viewer account', 'Zelda Example',
    ]


def test_a_site_admin_keeps_the_usernames(admin_client, conversation):
    _two_people(conversation)

    response = admin_client.get(f'/api/v1/admin/conversations/{conversation.id}/participants')

    assert response.status_code == 200
    assert [row['username'] for row in response.get_json()['data']['participants']] == [
        'Aaron Example', 'Zelda Example',
    ]


def test_openapi_says_the_username_may_be_withheld(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    username = spec['components']['schemas']['AdminParticipant']['properties']['username']

    assert username['type'] == ['string', 'null']
