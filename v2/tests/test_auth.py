"""Tests for login, OAuth callback, and logout flows."""
from unittest.mock import MagicMock, patch

from flask import session

from db import Participant, db


def test_login_without_oauth_returns_503(client):
    resp = client.get('/login')
    assert resp.status_code == 503


def test_login_with_oauth_redirects_to_wikimedia(client, app):
    app.config['OAUTH_CLIENT_ID'] = 'test-client-id'
    resp = client.get('/login')
    assert resp.status_code == 302
    assert 'meta.wikimedia.org' in resp.headers['Location']
    assert 'code_challenge' in resp.headers['Location']


def test_oauth_callback_state_mismatch_redirects_to_login(client):
    """Bad state in callback → redirect to /login, no session set."""
    resp = client.get('/oauth-callback?code=abc&state=bad-state')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
    with client.session_transaction() as sess:
        assert 'username' not in sess


def test_oauth_callback_happy_path_creates_participant(client, app):
    """Valid callback creates a Participant row and populates session."""
    app.config['OAUTH_CLIENT_ID'] = 'cid'
    app.config['OAUTH_CLIENT_SECRET'] = 'csecret'
    app.config['OAUTH_REDIRECT_URI'] = 'http://localhost/oauth-callback'

    with client.session_transaction() as sess:
        sess['oauth_state'] = 'valid-state'
        sess['oauth_code_verifier'] = 'verifier'

    token_resp = MagicMock()
    token_resp.json.return_value = {'access_token': 'tok'}
    token_resp.raise_for_status = MagicMock()

    profile_resp = MagicMock()
    profile_resp.json.return_value = {'username': 'WikiUser', 'sub': 42}
    profile_resp.raise_for_status = MagicMock()

    with patch('app.requests.post', return_value=token_resp), \
         patch('app.requests.get', return_value=profile_resp), \
         patch('app._is_emailable', return_value=True):
        resp = client.get('/oauth-callback?code=abc&state=valid-state')

    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get('username') == 'WikiUser'
        assert sess.get('emailable') is True

    p = Participant.query.filter_by(mw_username='WikiUser').first()
    assert p is not None
    assert p.mw_user_id == 42


def test_oauth_callback_updates_username_if_changed(client, app, participant):
    """If mw_username changed since last login, it is updated in the DB."""
    app.config['OAUTH_CLIENT_ID'] = 'cid'
    app.config['OAUTH_CLIENT_SECRET'] = 'csecret'
    app.config['OAUTH_REDIRECT_URI'] = 'http://localhost/cb'

    # participant.mw_user_id=99999, mw_username='testuser'
    with client.session_transaction() as sess:
        sess['oauth_state'] = 'st'
        sess['oauth_code_verifier'] = 'v'

    token_resp = MagicMock()
    token_resp.json.return_value = {'access_token': 'tok'}
    token_resp.raise_for_status = MagicMock()

    profile_resp = MagicMock()
    profile_resp.json.return_value = {'username': 'RenamedUser', 'sub': 99999}
    profile_resp.raise_for_status = MagicMock()

    with patch('app.requests.post', return_value=token_resp), \
         patch('app.requests.get', return_value=profile_resp), \
         patch('app._is_emailable', return_value=False):
        client.get('/oauth-callback?code=x&state=st')

    from db import db
    db.session.refresh(participant)
    assert participant.mw_username == 'RenamedUser'


def test_oauth_callback_preserves_existing_xid_when_secret_changes(client, app, participant):
    """A secret rotation must not detach an existing participant from Polis history."""
    original_xid = participant.xid
    original_version = participant.xid_key_version
    app.config.update(
        OAUTH_CLIENT_ID='cid',
        OAUTH_CLIENT_SECRET='csecret',
        OAUTH_REDIRECT_URI='http://localhost/cb',
        XID_HASH_SECRET='rotated-secret',
    )
    with client.session_transaction() as sess:
        sess['oauth_state'] = 'st'
        sess['oauth_code_verifier'] = 'v'

    token_resp = MagicMock()
    token_resp.json.return_value = {'access_token': 'tok'}
    token_resp.raise_for_status = MagicMock()
    profile_resp = MagicMock()
    profile_resp.json.return_value = {
        'username': participant.mw_username,
        'sub': participant.mw_user_id,
    }
    profile_resp.raise_for_status = MagicMock()

    with patch('app.requests.post', return_value=token_resp), \
         patch('app.requests.get', return_value=profile_resp), \
         patch('app._is_emailable', return_value=False):
        client.get('/oauth-callback?code=x&state=st')

    db.session.refresh(participant)
    assert participant.xid == original_xid
    assert participant.xid_key_version == original_version
    with client.session_transaction() as sess:
        assert sess['xid'] == original_xid


def test_current_participant_resolves_stale_username_by_xid(app, participant):
    """A renamed user keeps the same stable xid, so old session username is ignored."""
    from app import _current_participant

    old_username = participant.mw_username
    participant.mw_username = 'RenamedUser'
    db.session.commit()

    with app.test_request_context('/'):
        session['username'] = old_username
        session['xid'] = participant.xid
        assert _current_participant().id == participant.id


def test_current_participant_rejects_invalid_xid_even_if_username_matches(app, participant):
    """Once a session has xid, username is not accepted as a fallback identity key."""
    from app import _current_participant

    with app.test_request_context('/'):
        session['username'] = participant.mw_username
        session['xid'] = 'not-the-participant-xid'
        assert _current_participant() is None


def test_logout_clears_session(auth_client):
    resp = auth_client.post('/logout')
    assert resp.status_code == 302
    with auth_client.session_transaction() as sess:
        assert 'username' not in sess


def test_login_required_redirects_unauthenticated(client):
    """Protected routes redirect to /login when not authenticated."""
    for path in ['/accept/foo', '/c/foo', '/admin']:
        resp = client.get(path)
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location'], path
