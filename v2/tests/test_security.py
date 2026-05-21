"""Tests for security headers, redirect safety, and dev DB isolation."""
import os
from unittest.mock import patch

from db import Conversation, db


def test_security_headers_on_every_response(client):
    """All responses carry the required security headers including CSP."""
    resp = client.get('/')
    assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
    assert resp.headers.get('X-Frame-Options') == 'DENY'
    assert resp.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    csp = resp.headers.get('Content-Security-Policy', '')
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_safe_redirect_blocks_absolute_external(app):
    from app import _safe_redirect
    with app.test_request_context('/'):
        assert _safe_redirect('https://evil.com/steal', '/') == '/'
        assert _safe_redirect('http://evil.com', '/') == '/'


def test_safe_redirect_blocks_protocol_relative(app):
    """//evil.com bypass is rejected."""
    from app import _safe_redirect
    with app.test_request_context('/'):
        assert _safe_redirect('//evil.com', '/') == '/'


def test_safe_redirect_allows_relative_paths(app):
    from app import _safe_redirect
    with app.test_request_context('/'):
        assert _safe_redirect('/admin', '/') == '/admin'
        assert _safe_redirect('/c/some-slug', '/') == '/c/some-slug'
        assert _safe_redirect('/accept/foo', '/') == '/accept/foo'


def test_admin_role_redirect_to_cannot_escape(app, admin_client, admin_participant, participant):
    """redirect_to field in role forms is sanitised through _safe_redirect."""
    conv = Conversation(slug='sec-conv', polis_id='sec1234567',
                        title='Security Test Conv', active=True, access_policy='public')
    db.session.add(conv)
    db.session.commit()
    resp = admin_client.post('/admin/roles/add', data={
        'participant_id': participant.id,
        'conversation_id': conv.id,
        'role': 'moderator',
        'redirect_to': '//evil.com',
    })
    assert resp.status_code == 302
    assert 'evil.com' not in resp.headers['Location']


def test_dev_db_isolation_refuses_non_sqlite(tmp_path):
    """create_app raises RuntimeError when DEV_DATABASE_URL is not sqlite://."""
    env = {
        'FLASK_DEBUG': '1',
        'DEV_LOGIN_USER': 'testuser',
        'DEV_DATABASE_URL': 'mysql://prod-host/db',
        # Make sure we don't collide with real secrets
        'SECRET_KEY': 'test',
    }
    import pytest
    with patch.dict(os.environ, env, clear=False):
        from app import create_app
        with pytest.raises(RuntimeError, match='sqlite'):
            create_app()


def test_dev_db_isolation_skipped_without_dev_login_user(tmp_path):
    """Without DEV_LOGIN_USER set, the isolation check is bypassed."""
    env_patch = {'DEV_LOGIN_USER': '', 'FLASK_DEBUG': '1'}
    with patch.dict(os.environ, env_patch, clear=False):
        from app import create_app
        # Should not raise — no isolation check when DEV_LOGIN_USER is empty
        a = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/iso.db',
            'SESSION_TYPE': 'filesystem',
            'SESSION_FILE_DIR': str(tmp_path),
        })
        assert a is not None


def test_proxy_delete_method_not_allowed(auth_client):
    """DELETE is not in the allowed proxy methods."""
    resp = auth_client.delete('/proxy/particiapi/api/conversations/')
    assert resp.status_code == 405
