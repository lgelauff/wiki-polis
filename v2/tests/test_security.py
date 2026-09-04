"""Tests for security headers, redirect safety, and dev DB isolation."""
import hashlib
import hmac
import os
from pathlib import Path
from unittest.mock import patch

from cachelib.file import FileSystemCache
import pytest

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


def test_flash_toasts_do_not_inject_messages_with_innerhtml():
    base_template = Path(__file__).resolve().parents[1] / 'templates' / 'base.html'
    source = base_template.read_text()

    assert 'el.innerHTML' not in source
    assert 'msg.textContent = message' in source


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


def test_trusted_hosts_rejects_unexpected_host(tmp_path):
    """Flask rejects requests whose Host header is outside TRUSTED_HOSTS."""
    session_dir = tmp_path / 'sessions-trusted-hosts'
    session_dir.mkdir()
    from app import create_app
    a = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/trusted-hosts.db',
        'SECRET_KEY': 'test-secret',
        'SESSION_TYPE': 'cachelib',
        'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
        'TRUSTED_HOSTS': ['wiki-polis.test'],
        # This unit test isolates host validation and does not build SPA assets.
    })
    with a.app_context():
        db.create_all()
    client = a.test_client()

    assert client.get('/', headers={'Host': 'wiki-polis.test'}).status_code == 200
    assert client.get('/', headers={'Host': 'evil.test'}).status_code == 400


def test_production_requires_trusted_hosts(tmp_path):
    """Production must declare the expected hostnames before startup."""
    with patch.dict(os.environ, {'FLASK_DEBUG': '0', 'TRUSTED_HOSTS': ''}, clear=False):
        from app import create_app
        with pytest.raises(RuntimeError, match='TRUSTED_HOSTS is not set'):
            create_app({
                'TESTING': False,
                'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/prod-missing-hosts.db',
                'SECRET_KEY': 'test-secret',
                'RATELIMIT_STORAGE_URI': 'redis://localhost:6379/0',
            })


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


def test_fake_login_ignored_on_toolforge(tmp_path):
    """DEV_FAKE_LOGIN must not register auth-bypass routes on Toolforge."""
    session_dir = tmp_path / 'sessions-toolforge'
    session_dir.mkdir()
    env = {
        'DEV_FAKE_LOGIN': '1',
        'FLASK_DEBUG': '1',
        'TOOL_TOOLFORGE_API_URL': 'https://api.svc.tools.eqiad1.wikimedia.cloud',
        'SECRET_KEY': 'test',
    }
    with patch.dict(os.environ, env, clear=False):
        from app import create_app
        a = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/fake-toolforge.db',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
        })
    assert a.config['DEV_FAKE_LOGIN'] is False
    assert a.config['DEV_TEST_USERS'] == []
    assert a.test_client().get('/dev/login/dev-user-1').status_code == 404


def test_fake_login_ignored_when_not_debug(tmp_path):
    """DEV_FAKE_LOGIN must not register auth-bypass routes in production mode."""
    session_dir = tmp_path / 'sessions-prod'
    session_dir.mkdir()
    env = {
        'DEV_FAKE_LOGIN': '1',
        'FLASK_DEBUG': '0',
        'TOOL_TOOLFORGE_API_URL': '',
        'SECRET_KEY': 'test',
    }
    with patch.dict(os.environ, env, clear=False):
        from app import create_app
        a = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/fake-prod.db',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
        })
    assert a.config['DEV_FAKE_LOGIN'] is False
    assert a.test_client().get('/dev/login/dev-user-1').status_code == 404


def test_production_requires_ratelimit_storage_uri(tmp_path):
    """Production must not silently fall back to per-worker limiter storage."""
    with patch.dict(os.environ, {
        'FLASK_DEBUG': '0',
        'RATELIMIT_STORAGE_URI': '',
        'TOOL_REDIS_URI': '',
    }, clear=False):
        from app import create_app
        with pytest.raises(RuntimeError, match='RATELIMIT_STORAGE_URI is not set'):
            create_app({
                'TESTING': False,
                'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/prod-missing-rate.db',
                'SECRET_KEY': 'test-secret',
                'TRUSTED_HOSTS': ['wiki-polis.test'],
            })


def test_production_rejects_local_ratelimit_storage_uri(tmp_path):
    """Production limiter storage must use Redis, not a local memory backend."""
    with patch.dict(os.environ, {'FLASK_DEBUG': '0'}, clear=False):
        from app import create_app
        with pytest.raises(RuntimeError, match='Redis backend'):
            create_app({
                'TESTING': False,
                'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/prod-local-rate.db',
                'SECRET_KEY': 'test-secret',
                'RATELIMIT_STORAGE_URI': 'memory://',
                'TRUSTED_HOSTS': ['wiki-polis.test'],
            })


def test_production_uses_toolforge_redis_uri(tmp_path):
    """Toolforge's global Redis URI is the production default."""
    session_dir = tmp_path / 'sessions-toolforge-redis'
    session_dir.mkdir()
    toolforge_redis = 'redis://redis.svc.tools.eqiad1.wikimedia.cloud:6379'
    with patch.dict(os.environ, {
        'FLASK_DEBUG': '0',
        'RATELIMIT_STORAGE_URI': '',
        'TOOL_TOOLFORGE_API_URL': 'https://api.svc.tools.eqiad1.wikimedia.cloud',
        'TOOL_REDIS_URI': toolforge_redis,
    }, clear=False):
        from app import create_app
        a = create_app({
            'TESTING': False,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/prod-toolforge-redis.db',
            'SECRET_KEY': 'test-secret',
            'RATELIMIT_KEY_PREFIX': 'wiki-polis-test:prefix:',
            'RATELIMIT_IDENTITY_SECRET': 'x' * 32,
            'TRUSTED_HOSTS': ['wiki-polis.test'],
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
        })
    assert a.config['RATELIMIT_STORAGE_URI'] == toolforge_redis
    assert a.config['TRUST_PROXY_HEADERS'] is True


def test_production_requires_ratelimit_key_prefix(tmp_path):
    """Shared Toolforge Redis keys must be namespaced per deployment."""
    with patch.dict(os.environ, {
        'FLASK_DEBUG': '0',
        'RATELIMIT_KEY_PREFIX': '',
        'RATELIMIT_IDENTITY_SECRET': 'x' * 32,
    }, clear=False):
        from app import create_app
        with pytest.raises(RuntimeError, match='RATELIMIT_KEY_PREFIX is not set'):
            create_app({
                'TESTING': False,
                'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/prod-missing-prefix.db',
                'SECRET_KEY': 'test-secret',
                'RATELIMIT_STORAGE_URI': 'redis://localhost:6379/0',
                'TRUSTED_HOSTS': ['wiki-polis.test'],
            })


def test_production_requires_ratelimit_identity_secret(tmp_path):
    """Production limiter keys must not expose raw client identity values."""
    with patch.dict(os.environ, {
        'FLASK_DEBUG': '0',
        'RATELIMIT_IDENTITY_SECRET': '',
    }, clear=False):
        from app import create_app
        with pytest.raises(RuntimeError, match='RATELIMIT_IDENTITY_SECRET is not set'):
            create_app({
                'TESTING': False,
                'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/prod-missing-identity.db',
                'SECRET_KEY': 'test-secret',
                'RATELIMIT_STORAGE_URI': 'redis://localhost:6379/0',
                'RATELIMIT_KEY_PREFIX': 'wiki-polis-test:prefix:',
                'TRUSTED_HOSTS': ['wiki-polis.test'],
            })


def test_ratelimit_identity_key_hashes_forwarded_client_identity(app):
    """The limiter stores HMAC output, not the raw forwarded client address."""
    from app import _ratelimit_identity_key
    secret = 'x' * 32
    app.config['RATELIMIT_IDENTITY_SECRET'] = secret
    app.config['TRUST_PROXY_HEADERS'] = True
    with app.test_request_context('/', headers={
        'X-Forwarded-For': '203.0.113.10, 10.0.0.1',
    }):
        expected = 'ip:' + hmac.new(
            secret.encode('utf-8'),
            b'203.0.113.10',
            hashlib.sha256,
        ).hexdigest()
        actual = _ratelimit_identity_key()

    assert actual == expected
    assert '203.0.113.10' not in actual


def test_ratelimit_identity_key_ignores_untrusted_forwarded_client(app):
    """Direct VPS requests cannot spoof rate-limit identity through X-Forwarded-For."""
    from app import _ratelimit_identity_key
    secret = 'x' * 32
    app.config['RATELIMIT_IDENTITY_SECRET'] = secret
    app.config['TRUST_PROXY_HEADERS'] = False
    with app.test_request_context('/', headers={
        'X-Forwarded-For': '203.0.113.10',
    }, environ_base={'REMOTE_ADDR': '198.51.100.20'}):
        expected = 'ip:' + hmac.new(
            secret.encode('utf-8'),
            b'198.51.100.20',
            hashlib.sha256,
        ).hexdigest()
        actual = _ratelimit_identity_key()

    assert actual == expected
    assert '203.0.113.10' not in actual
    assert '198.51.100.20' not in actual


def test_test_config_may_disable_distributed_ratelimit_storage(tmp_path):
    """Tests keep the lightweight in-memory limiter unless they opt into storage."""
    session_dir = tmp_path / 'sessions-rate-test'
    session_dir.mkdir()
    with patch.dict(os.environ, {
        'FLASK_DEBUG': '0',
        'RATELIMIT_STORAGE_URI': '',
        'TOOL_REDIS_URI': '',
    }, clear=False):
        from app import create_app
        a = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/test-rate.db',
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
        })
    assert 'RATELIMIT_STORAGE_URI' not in a.config


def test_proxy_delete_method_not_allowed(auth_client):
    """DELETE is not in the allowed proxy methods."""
    resp = auth_client.delete('/proxy/particiapi/api/conversations/')
    assert resp.status_code == 405
