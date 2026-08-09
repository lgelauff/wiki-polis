import hashlib
import os
from unittest.mock import patch

import pytest
from cachelib.file import FileSystemCache

import polis_admin
from app import create_app
from db import Conversation, Participant, db


@pytest.fixture(autouse=True)
def _reset_polis_pg_pools():
    """Drop the process-wide Polis-Postgres connection pools around each test.

    _pg_query pools connections per db_url for the life of the process. Tests
    patch psycopg2.connect per-test; without a reset the first test's pooled
    (mock) connection would be reused by later tests. Cheap no-op when no pool
    has been built.
    """
    polis_admin._reset_pg_pools()
    yield
    polis_admin._reset_pg_pools()


@pytest.fixture(autouse=True)
def _disable_phase6_results_cache():
    """Disable the in-process Phase 6 results cache in tests so mocked client
    return values are always seen fresh (no cross-test or within-test staleness)."""
    import app as _app
    saved = _app._PHASE6_AGG_TTL
    _app._PHASE6_AGG_TTL = 0.0
    # Also clear the process-local Phase-6 vote-session share cache/locks so a
    # bootstrap from one test can't be reused in another (SQLite ids reset per test).
    _app._p6_session_cache.clear()
    _app._p6_bootstrap_locks.clear()
    yield
    _app._PHASE6_AGG_TTL = saved
    _app._invalidate_phase6_results_cache()
    _app._p6_session_cache.clear()
    _app._p6_bootstrap_locks.clear()


@pytest.fixture
def app(tmp_path):
    """Fresh Flask app with isolated SQLite DB and filesystem sessions per test.

    FLASK_DEBUG and DEV_LOGIN_USER are cleared so the test app never enters dev
    mode — which would otherwise redirect /login → /dev-login and write to
    the dev.db instead of the isolated test DB.
    """
    session_dir = tmp_path / 'sessions'
    session_dir.mkdir()

    env_overrides = {
        'FLASK_DEBUG': '0',
        'DEV_LOGIN_USER': '',
        'RATELIMIT_STORAGE_URI': '',
        'RATELIMIT_KEY_PREFIX': '',
        'RATELIMIT_IDENTITY_SECRET': '',
        'TRUST_PROXY_HEADERS': '',
        'TOOL_TOOLFORGE_API_URL': '',
        'TOOL_REDIS_URI': '',
    }
    with patch.dict(os.environ, env_overrides, clear=False):
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


@pytest.fixture
def client(app):
    return app.test_client()


# ── DB helpers ────────────────────────────────────────────────────────────────

def _xid(mw_user_id: int) -> str:
    return hashlib.sha256(str(mw_user_id).encode()).hexdigest()


@pytest.fixture
def participant(app):
    """A regular Participant in the test DB."""
    p = Participant(mw_user_id=99999, mw_username='testuser', xid=_xid(99999))
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def admin_participant(app):
    """A Participant with is_global_admin=True in the test DB."""
    p = Participant(mw_user_id=88888, mw_username='adminuser', xid=_xid(88888),
                    is_global_admin=True)
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def conversation(app):
    """A public active Conversation in the test DB."""
    c = Conversation(
        slug='test-conv', polis_id='abc1234567',
        title='Test Conversation', active=True, access_policy='public',
    )
    db.session.add(c)
    db.session.commit()
    return c


# ── Session helpers ───────────────────────────────────────────────────────────

def login(client, username: str, emailable: bool = True) -> None:
    participant = Participant.query.filter_by(mw_username=username).first()
    xid = participant.xid if participant else hashlib.sha256(username.encode()).hexdigest()
    with client.session_transaction() as sess:
        sess['username'] = username
        sess['xid'] = xid
        sess['emailable'] = emailable


@pytest.fixture
def auth_client(client, participant):
    """Test client logged in as the regular participant."""
    login(client, 'testuser')
    return client


@pytest.fixture
def admin_client(client, admin_participant):
    """Test client logged in as the global admin."""
    login(client, 'adminuser')
    return client
