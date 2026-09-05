"""Per-route rate limits on /api/v1, and the envelope a breach returns.

The rest of the suite runs with RATELIMIT_ENABLED False, so a decorator can be
added and never exercised. These tests build an app with the limiter actually
ON and hammer a real endpoint past its limit -- asserting that a 429 happens at
the documented boundary and that it arrives as the API's JSON error envelope
rather than an HTML page.

The independence test is load-bearing for the read limits: Flask-Limiter scopes
an unscoped decorator to the view function (flask_limiter/_limits.py, scope_for),
so each endpoint gets its own bucket. That is why the SPA fanning one page view
across several read endpoints does not concentrate consumption the way it would
under a shared limit.
"""
import os
from unittest.mock import patch

import pytest
from cachelib.file import FileSystemCache

from app import create_app
from db import db


@pytest.fixture
def limited_app(tmp_path):
    """App with rate limiting ON and an in-process (per-app) limiter store."""
    session_dir = tmp_path / 'sessions'
    session_dir.mkdir(exist_ok=True)
    env = {
        'FLASK_DEBUG': '0',
        'DEV_LOGIN_USER': '',
        'RATELIMIT_STORAGE_URI': '',
        'RATELIMIT_KEY_PREFIX': '',
        'RATELIMIT_IDENTITY_SECRET': '',
        'TRUST_PROXY_HEADERS': '',
        'TOOL_TOOLFORGE_API_URL': '',
        'TOOL_REDIS_URI': '',
    }
    with patch.dict(os.environ, env, clear=False):
        a = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/test.db',
            'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': {'check_same_thread': False}},
            'WTF_CSRF_ENABLED': False,
            'RATELIMIT_ENABLED': True,
            'RATELIMIT_STORAGE_URI': 'memory://',
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
            'SESSION_PERMANENT': False,
            'POLIS_DATABASE_URL': '',
            'POLIS_SERVER_URL': '',
        })
    with a.app_context():
        db.create_all()
        yield a
        db.session.remove()


# The identity-reveal POST is limited to 5/min and rejects a malformed body with
# a 400 before touching the DB -- so the limiter, which runs first, is the only
# thing under test here. A rejected request still consumes budget, which is the
# behaviour we want: a flood of junk must not be free.
REVEAL_LIMIT = 5


def test_identity_reveal_post_returns_429_after_its_limit(limited_app):
    client = limited_app.test_client()
    url = '/api/v1/conversations/anything/identity-reveal'

    statuses = [client.post(url, json={}).status_code for _ in range(REVEAL_LIMIT)]
    assert 429 not in statuses, (
        f'limit fired early, within its own budget: {statuses}'
    )

    breach = client.post(url, json={})
    assert breach.status_code == 429


def test_rate_limited_api_response_uses_the_json_envelope(limited_app):
    client = limited_app.test_client()
    url = '/api/v1/conversations/anything/identity-reveal'
    for _ in range(REVEAL_LIMIT):
        client.post(url, json={})

    breach = client.post(url, json={})

    assert breach.status_code == 429
    assert breach.mimetype == 'application/json', (
        'a rate-limited /api/v1 request must not fall back to an HTML page'
    )
    body = breach.get_json()
    assert set(body) == {'error'}
    assert body['error']['code'] == 'rate_limited'
    assert isinstance(body['error']['message'], str) and body['error']['message']
    # Same no-store contract as every other API response.
    assert breach.headers['Cache-Control'] == 'no-store'


def test_each_endpoint_gets_its_own_budget(limited_app):
    """Exhausting one route must not spend another route's allowance.

    This is the mechanism the read limits are sized against: the SPA renders one
    conversation page from several endpoints, each with an independent bucket.
    """
    client = limited_app.test_client()
    reveal = '/api/v1/conversations/anything/identity-reveal'
    for _ in range(REVEAL_LIMIT + 1):
        client.post(reveal, json={})
    assert client.post(reveal, json={}).status_code == 429

    # A different view function, well inside its own 120/min budget.
    other = client.get('/api/v1/conversations/anything/about')
    assert other.status_code != 429
