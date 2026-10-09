"""Admin home (#538): the caller's own consultations, and the site admin dashboard's move.

`GET /api/v1/admin/home` lists the consultations the caller holds a role in -- title, the
caller's role, a status word and the open flag count -- and nothing about anyone else.
`/admin` is the page for everyone with a role; the site admin dashboard moved to
`/site-admin`, whose data (`GET /api/v1/admin`) stays site-admins-only, so anyone else who
opens it gets the SPA's access page from the 403.
"""

from datetime import datetime, timedelta, timezone

import pytest

import app as app_module
from db import AdminRole, ContentFlag, Conversation, Participant, db
from tests.conftest import _xid, login

HOME = '/api/v1/admin/home'


@pytest.fixture
def spa_build(app, tmp_path, monkeypatch):
    build_dir = tmp_path / 'spa'
    build_dir.mkdir()
    (build_dir / 'index.html').write_text('<!doctype html><div id="root"></div>', encoding='utf-8')
    monkeypatch.setattr(app_module, '_SPA_BUILD_DIR', str(build_dir))


def _conversation(slug, *, days_ago=0, **fields):
    conv = Conversation(**{
        'slug': slug, 'polis_id': f'polis-{slug}', 'title': f'Title {slug}', 'active': True,
        'access_policy': 'public',
        'created_at': datetime.now(timezone.utc) - timedelta(days=days_ago),
        **fields,
    })
    db.session.add(conv)
    db.session.commit()
    return conv


def _role(participant, conversation, role):
    db.session.add(AdminRole(participant_id=participant.id, conversation_id=conversation.id, role=role))
    db.session.commit()


def _flag(conversation, participant, status='open'):
    db.session.add(ContentFlag(
        conversation_id=conversation.id, participant_id=participant.id,
        content_type='statement', statement_tid=1, category='other',
        detail='private detail text', status=status,
    ))
    db.session.commit()


def test_lists_only_the_callers_consultations_with_role_status_and_open_flags(client, participant):
    other = Participant(mw_user_id=77777, mw_username='someone-else', xid=_xid(77777))
    db.session.add(other)
    db.session.commit()
    organized = _conversation('organized', days_ago=2)
    moderated = _conversation('moderated', days_ago=1, paused=True)
    not_mine = _conversation('not-mine')
    _role(participant, organized, 'organizer')
    _role(participant, moderated, 'moderator')
    _role(other, not_mine, 'organizer')
    _flag(moderated, other)
    _flag(moderated, other)
    _flag(moderated, other, status='resolved')
    _flag(not_mine, other)
    login(client, 'testuser')

    response = client.get(HOME)

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()['data']
    # Newest first; only the two consultations the caller holds a role in.
    assert data['conversations'] == [
        {'id': moderated.id, 'title': 'Title moderated', 'role': 'Moderator', 'status': 'paused',
         'openFlags': 2, 'links': {'overview': f'/admin/conversations/{moderated.id}'}},
        {'id': organized.id, 'title': 'Title organized', 'role': 'Organizer', 'status': 'active',
         'openFlags': 0, 'links': {'overview': f'/admin/conversations/{organized.id}'}},
    ]
    assert data['links'] == {'self': HOME, 'siteAdminDashboard': None}


def test_carries_no_participant_data(client, participant):
    other = Participant(mw_user_id=77777, mw_username='flagger-name', xid=_xid(77777))
    db.session.add(other)
    db.session.commit()
    conv = _conversation('slug-kept-out', title='Mine')
    _role(participant, conv, 'organizer')
    _role(other, conv, 'moderator')
    _flag(conv, other)
    login(client, 'testuser')

    response = client.get(HOME)

    assert response.status_code == 200
    for private in ('flagger-name', 'testuser', other.xid, participant.xid,
                    'private detail text', conv.polis_id, conv.slug):
        assert private not in response.text


def test_an_organizer_who_also_moderates_is_listed_once_as_organizer(client, participant):
    conv = _conversation('both')
    _role(participant, conv, 'moderator')
    _role(participant, conv, 'organizer')
    login(client, 'testuser')

    rows = client.get(HOME).get_json()['data']['conversations']

    assert [(row['id'], row['role']) for row in rows] == [(conv.id, 'Organizer')]


@pytest.mark.parametrize(('fields', 'status'), [
    ({'paused': True}, 'paused'),
    ({'active': False}, 'archived'),
    ({'active': False, 'closed_at': datetime(2026, 9, 1, tzinfo=timezone.utc)}, 'closed'),
])
def test_status_is_the_dashboards_word(client, participant, fields, status):
    conv = _conversation('stat', **fields)
    _role(participant, conv, 'moderator')
    login(client, 'testuser')

    rows = client.get(HOME).get_json()['data']['conversations']

    assert rows[0]['status'] == status


def test_a_site_admin_gets_their_own_roles_and_the_dashboard_link(client, admin_participant, conversation):
    mine = _conversation('admin-organizes')
    _role(admin_participant, mine, 'organizer')
    login(client, 'adminuser')

    data = client.get(HOME).get_json()['data']

    # Site-wide access is not a role in a consultation: only the one they hold is listed.
    assert [row['id'] for row in data['conversations']] == [mine.id]
    assert data['links']['siteAdminDashboard'] == '/site-admin'


def test_a_site_admin_with_no_role_gets_an_empty_list(admin_client, conversation):
    response = admin_client.get(HOME)

    assert response.status_code == 200
    assert response.get_json()['data'] == {
        'conversations': [],
        'links': {'self': HOME, 'siteAdminDashboard': '/site-admin'},
    }


def test_signed_in_without_any_role_is_forbidden(auth_client, conversation):
    response = auth_client.get(HOME)

    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'forbidden'


def test_signed_out_is_unauthorized(client, conversation):
    response = client.get(HOME)

    assert response.status_code == 401
    assert response.get_json()['error']['code'] == 'unauthorized'


def test_admin_home_and_site_admin_pages_are_spa_routes(client, spa_build):
    for path in ('/admin', '/site-admin'):
        response = client.get(path)
        assert response.status_code == 200, path
        assert b'<div id="root"></div>' in response.data


def test_the_dashboard_data_stays_site_admin_only(client, participant, spa_build):
    """`/site-admin` is the SPA shell for anyone; what it shows comes from `GET /api/v1/admin`,
    which refuses everyone but a site admin, and the SPA renders that 403 as its access page."""
    conv = _conversation('organized')
    _role(participant, conv, 'organizer')
    login(client, 'testuser')

    assert client.get('/api/v1/admin').status_code == 403
    assert client.get(HOME).status_code == 200


def test_the_dashboard_data_is_served_to_a_site_admin(admin_client, spa_build):
    assert admin_client.get('/api/v1/admin').status_code == 200
