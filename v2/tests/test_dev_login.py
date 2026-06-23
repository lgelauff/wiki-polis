"""Tests for the DEV_FAKE_LOGIN local-debug login (`/dev/login/<username>`).

Regression for the bug where a reused dev Participant (matched by mw_user_id) kept a
stale mw_username/xid, so the authenticated local-debug session no longer matched the
participant row used by participant-gated routes (/accept, /reveal).
"""
import hashlib
import hmac
import os
from unittest.mock import patch

import pytest
from cachelib.file import FileSystemCache

from app import create_app
from db import Participant, db


@pytest.fixture
def fake_login_app(tmp_path):
    """Local-debug app with DEV_FAKE_LOGIN=1 so `/dev/login/<username>` is registered."""
    session_dir = tmp_path / 'sessions'
    session_dir.mkdir()
    env = {
        'FLASK_DEBUG': '1',
        'DEV_LOGIN_USER': '',
        'DEV_FAKE_LOGIN': '1',
        'TOOL_TOOLFORGE_API_URL': '',
    }
    with patch.dict(os.environ, env, clear=False):
        a = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/test.db',
            'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': {'check_same_thread': False}},
            'WTF_CSRF_ENABLED': False,
            'RATELIMIT_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
            'SESSION_PERMANENT': False,
        })
    with a.app_context():
        db.create_all()
        yield a
        db.session.remove()


def test_dev_fake_login_creates_participant(fake_login_app):
    """First login creates the dev Participant with matching username and xid."""
    r = fake_login_app.test_client().get('/dev/login/dev-user-1')
    assert r.status_code == 302
    with fake_login_app.app_context():
        p = Participant.query.filter_by(mw_user_id=-1).first()
        assert p is not None
        assert p.mw_username == 'dev-user-1'
        assert p.xid == hashlib.sha256(b'dev-fake-dev-user-1').hexdigest()


def test_dev_fake_login_syncs_drifted_username(fake_login_app):
    """A reused dev row whose username/xid drifted is corrected on login."""
    with fake_login_app.app_context():
        db.session.add(Participant(mw_user_id=-2, mw_username='stale-name', xid='x' * 64))
        db.session.commit()

    r = fake_login_app.test_client().get('/dev/login/dev-user-2')
    assert r.status_code == 302

    with fake_login_app.app_context():
        # Same row (matched by mw_user_id), now consistent with the authenticated username.
        rows = Participant.query.filter_by(mw_user_id=-2).all()
        assert len(rows) == 1
        assert rows[0].mw_username == 'dev-user-2'
        assert rows[0].xid == hashlib.sha256(b'dev-fake-dev-user-2').hexdigest()
        # The row now matches both legacy username checks and stable xid session lookup.
        assert Participant.query.filter_by(mw_username='dev-user-2').first() is not None


def test_dev_fake_login_unknown_user_404(fake_login_app):
    assert fake_login_app.test_client().get('/dev/login/not-a-dev-user').status_code == 404


def _staging_app(tmp_path, tool_name='wiki-polis-dev', trusted_hosts='wiki-polis-dev.toolforge.org'):
    session_dir = tmp_path / f'sessions-{tool_name}'
    session_dir.mkdir()
    env = {
        'FLASK_DEBUG': '0',
        'DEV_LOGIN_USER': '',
        'DEV_FAKE_LOGIN': '',
        'TOOL_TOOLFORGE_API_URL': 'https://api.svc.tools.eqiad1.wikimedia.cloud',
        'TOOL_NAME': tool_name,
        'STAGING_DEV_TOKEN': 's' * 32,
        'TRUSTED_HOSTS': trusted_hosts,
    }
    with patch.dict(os.environ, env, clear=False):
        a = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/{tool_name}.db',
            'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': {'check_same_thread': False}},
            'WTF_CSRF_ENABLED': False,
            'RATELIMIT_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
            'SESSION_PERMANENT': False,
        })
    with a.app_context():
        db.create_all()
    return a


def test_staging_dev_login_requires_valid_hmac_token(tmp_path):
    app = _staging_app(tmp_path)
    client = app.test_client()

    assert app.config['DEV_FAKE_LOGIN'] is False
    assert app.config['STAGING_DEV_LOGIN'] is True
    base_url = 'https://wiki-polis-dev.toolforge.org'
    assert client.get('/dev/login/dev-user-1', base_url=base_url).status_code == 403
    assert client.get('/dev/login/dev-user-1?token=wrong', base_url=base_url).status_code == 403

    token = hmac.new(b's' * 32, b'dev-user-1', hashlib.sha256).hexdigest()
    resp = client.get(f'/dev/login/dev-user-1?token={token}', base_url=base_url)
    assert resp.status_code == 302

    with app.app_context():
        p = Participant.query.filter_by(mw_user_id=-1).first()
        assert p is not None
        assert p.mw_username == 'dev-user-1'
        db.session.remove()


def test_staging_dev_login_not_registered_on_production_tool(tmp_path):
    app = _staging_app(tmp_path, tool_name='wiki-polis',
                       trusted_hosts='wiki-polis.toolforge.org')

    assert app.config['STAGING_DEV_LOGIN'] is False
    resp = app.test_client().get('/dev/login/dev-user-1?token=anything',
                                 base_url='https://wiki-polis.toolforge.org')
    assert resp.status_code == 404

    with app.app_context():
        db.session.remove()
