"""The deliberately-failing endpoint that proves the branded error pages on a
real deployment (`/dev/error-page-check/<code>`).

Two things need guarding. First, that it is not registered on production — it is
gated on the same STAGING_DEV_LOGIN / DEV_FAKE_LOGIN switches as the dev logins,
so its absence is the whole security story. Second, that it exercises BOTH ways a
status reaches the handlers: abort() raises an HTTPException, while a real bug is
an uncaught exception, and only the latter proves the 500 page.
"""
import os
from unittest.mock import patch

import pytest
from cachelib.file import FileSystemCache

import app as app_module
from app import create_app
from db import Participant, db


def _build_app(tmp_path, env):
    session_dir = tmp_path / 'sessions'
    session_dir.mkdir(exist_ok=True)
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
            'PROPAGATE_EXCEPTIONS': False,
        })
    with a.app_context():
        db.create_all()
        yield a
        db.session.remove()


@pytest.fixture
def selftest_app(tmp_path, monkeypatch):
    """Local-debug app with the dev gate on, and the SPA build deliberately absent."""
    missing = tmp_path / 'no-spa-build'
    missing.mkdir()
    monkeypatch.setattr(app_module, '_SPA_BUILD_DIR', str(missing))
    yield from _build_app(tmp_path, {
        'FLASK_DEBUG': '1',
        'DEV_LOGIN_USER': '',
        'DEV_FAKE_LOGIN': '1',
        'TOOL_TOOLFORGE_API_URL': '',
    })


@pytest.fixture
def production_app(tmp_path):
    """The gate off, as on the production Toolforge tool."""
    yield from _build_app(tmp_path, {
        'FLASK_DEBUG': '',
        'DEV_LOGIN_USER': '',
        'DEV_FAKE_LOGIN': '',
        'TOOL_TOOLFORGE_API_URL': '',
    })


@pytest.fixture
def admin_client(selftest_app):
    client = selftest_app.test_client()
    client.get('/dev/login/dev-user-1')
    with selftest_app.app_context():
        participant = Participant.query.filter_by(mw_username='dev-user-1').first()
        assert participant is not None
        participant.is_global_admin = True
        db.session.commit()
    return client


def _assert_branded(response, status, heading):
    assert response.status_code == status
    body = response.get_data(as_text=True)
    assert response.mimetype == 'text/html'
    assert 'ProtoWiki' in body
    assert heading in body


def test_route_is_absent_when_the_dev_gate_is_off(production_app):
    """The only thing keeping this off production is that it is never registered."""
    assert 'dev_error_page_check' not in production_app.view_functions
    assert production_app.test_client().get('/dev/error-page-check/500').status_code == 404


@pytest.mark.parametrize(('code', 'heading'), [
    (403, 'Not allowed'),
    (404, 'Page not found'),
])
def test_abort_path_renders_the_branded_page(admin_client, code, heading):
    _assert_branded(admin_client.get(f'/dev/error-page-check/{code}'), code, heading)


def test_uncaught_exception_renders_the_branded_500(admin_client):
    """The path a real bug takes — not abort(500), which is a different code path."""
    _assert_branded(
        admin_client.get('/dev/error-page-check/500'), 500, 'Something went wrong',
    )


def test_abort_mode_reaches_the_same_500_page(admin_client):
    _assert_branded(
        admin_client.get('/dev/error-page-check/500?mode=abort'),
        500, 'Something went wrong',
    )


def test_self_test_does_not_leak_the_exception_text(admin_client):
    body = admin_client.get('/dev/error-page-check/500').get_data(as_text=True)

    assert 'deliberate error-page self-test' not in body
    assert 'Traceback' not in body


def test_unsupported_status_is_rejected(admin_client):
    assert admin_client.get('/dev/error-page-check/418').status_code == 400


def test_route_is_admin_only(selftest_app):
    """Belt and braces on top of the gate: a non-admin session cannot reach it."""
    anonymous = selftest_app.test_client().get('/dev/error-page-check/500')

    assert anonymous.status_code in {302, 403}
    assert anonymous.status_code != 500
