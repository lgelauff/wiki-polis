"""Branded 404/403/500 pages, exercised with the SPA build absent.

``static/spa`` is gitignored and produced at deploy time by bin/build-spa.sh. A
missing or half-written build makes every canonical path 404 out of
send_from_directory, which is the failure these handlers most need to cover — so
every test here points _SPA_BUILD_DIR at an empty directory rather than assuming
whatever happens to be on the machine running the suite.
"""

import pytest
from werkzeug.exceptions import Forbidden

import app as app_module


@pytest.fixture
def no_spa_build(monkeypatch, tmp_path):
    """Point the SPA build directory at an empty path for the whole test."""
    missing = tmp_path / 'spa-build-that-was-never-made'
    missing.mkdir()
    monkeypatch.setattr(app_module, '_SPA_BUILD_DIR', str(missing))
    return missing


def _assert_branded(response, status: int, heading: str):
    assert response.status_code == status
    body = response.get_data(as_text=True)
    assert response.mimetype == 'text/html'
    assert 'Proto' in body
    assert heading in body
    assert f'Error {status}' in body
    return body


def test_canonical_spa_path_serves_a_branded_404_when_the_build_is_missing(
    client, no_spa_build,
):
    """The case the handlers exist for: SPA on, bundle gone."""
    response = client.get('/consultations')

    _assert_branded(response, 404, 'Page not found')


def test_spa_shell_route_serves_a_branded_404_when_the_build_is_missing(
    client, no_spa_build,
):
    response = client.get('/app/admin/conversations/7')

    _assert_branded(response, 404, 'Page not found')


def test_unrouted_html_path_serves_a_branded_404(client, no_spa_build):
    response = client.get('/no-such-page')

    _assert_branded(response, 404, 'Page not found')


def test_error_page_needs_no_external_asset_or_script(client, no_spa_build):
    """Self-containment is the whole point — assert it, don't assume it.

    A stylesheet link or a bundle reference would make the page fail in exactly
    the situation it is meant to cover.
    """
    body = client.get('/no-such-page').get_data(as_text=True)

    assert '<link rel="stylesheet"' not in body
    assert '<script' not in body
    assert '/static/' not in body
    assert 'https://' not in body
    assert '<style>' in body  # the CSS is inline instead


def test_forbidden_and_server_error_render_branded_pages(app, no_spa_build):
    """403 and 500 have no convenient real route, so drive them directly."""
    @app.get('/_test/forbidden')
    def _forbidden():
        raise Forbidden()

    @app.get('/_test/boom')
    def _boom():
        raise RuntimeError('deliberate')

    app.config['PROPAGATE_EXCEPTIONS'] = False
    client = app.test_client()

    _assert_branded(client.get('/_test/forbidden'), 403, 'Not allowed')
    _assert_branded(client.get('/_test/boom'), 500, 'Something went wrong')


def test_server_error_page_does_not_leak_the_exception(app, no_spa_build):
    @app.get('/_test/boom')
    def _boom():
        raise RuntimeError('secret-internal-detail')

    app.config['PROPAGATE_EXCEPTIONS'] = False

    body = app.test_client().get('/_test/boom').get_data(as_text=True)

    assert 'secret-internal-detail' not in body
    assert 'Traceback' not in body


def test_api_v1_keeps_json_for_every_status_the_html_pages_now_claim(
    app, no_spa_build,
):
    """The branded handlers are per-status, which Flask prefers over the generic
    HTTPException handler — so they must hand /api/v1/* back to the JSON envelope."""
    @app.get('/api/v1/_test/forbidden')
    def _api_forbidden():
        raise Forbidden()

    @app.get('/api/v1/_test/boom')
    def _api_boom():
        raise RuntimeError('deliberate')

    app.config['PROPAGATE_EXCEPTIONS'] = False
    client = app.test_client()

    not_found = client.get('/api/v1/no-such-endpoint')
    forbidden = client.get('/api/v1/_test/forbidden')
    boom = client.get('/api/v1/_test/boom')

    assert not_found.status_code == 404
    assert not_found.is_json
    assert not_found.get_json()['error']['code'] == 'not_found'
    assert forbidden.status_code == 403
    assert forbidden.get_json()['error']['code'] == 'forbidden'
    assert boom.status_code == 500
    assert boom.is_json
    assert boom.get_json()['error']['code'] == 'http_error'
    assert 'Proto' not in boom.get_data(as_text=True)


def test_logout_opened_as_a_link_serves_a_branded_405(client, no_spa_build):
    """#356: /logout is POST-only, and a bookmarked or typed /logout reached
    Werkzeug's bare 405 page."""
    response = client.get('/logout')

    body = _assert_branded(response, 405, "This address can&#x27;t be opened directly")
    assert '<a href="/">' in body
    assert set(response.headers['Allow'].split(', ')) == {'POST', 'OPTIONS'}


def test_html_form_without_a_csrf_token_serves_a_branded_400(
    app, client, conversation, no_spa_build,
):
    """#356: a form sent after the session expired reached Werkzeug's bare 400 page.
    /logout is the exception (it redirects home, #514)."""
    from db import db
    app.config['WTF_CSRF_ENABLED'] = True
    conversation.gated = True
    conversation.gating_type = 'voucher'
    db.session.commit()

    response = client.post(f'/c/{conversation.slug}/v', data={'code': 'X7F3K9M2ABCD'})

    _assert_branded(response, 400, 'Session failure')


def test_a_plain_bad_request_keeps_the_framework_page(app, no_spa_build):
    """Only the CSRF 400 is branded: its copy is about an expired session, which a
    malformed request or a bad Host header is not."""
    from werkzeug.exceptions import BadRequest

    @app.get('/_test/bad')
    def _bad():
        raise BadRequest()

    response = app.test_client().get('/_test/bad')

    assert response.status_code == 400
    assert 'Proto' not in response.get_data(as_text=True)


def test_a_csrf_refusal_logs_its_reason_but_not_the_query_or_a_forged_line(
    app, client, conversation, no_spa_build, caplog,
):
    """The branded page hides the reason, so the log keeps it. The log line comes from
    the CSRF handler, not the generic one, which is also what keeps #514's log-out
    redirect working. A voucher code can ride in the query string; it stays out."""
    import logging
    caplog.set_level(logging.INFO)
    app.config['WTF_CSRF_ENABLED'] = True

    response = client.post(f'/c/{conversation.slug}%0Aforged/v?v=SECRETCODE')

    assert response.status_code == 400
    refused = [r.getMessage() for r in caplog.records if r.getMessage().startswith('csrf refused')]
    assert len(refused) == 1
    assert 'The CSRF token is missing.' in refused[0]
    assert '\n' not in refused[0]
    assert 'SECRETCODE' not in caplog.text


def test_api_v1_keeps_json_for_400_and_405(app, client, no_spa_build):
    """The new per-status handlers must hand /api/v1/* back to the JSON envelope."""
    from werkzeug.exceptions import BadRequest

    @app.get('/api/v1/_test/bad')
    def _api_bad():
        raise BadRequest()

    not_allowed = client.delete('/api/v1/session')
    bad = app.test_client().get('/api/v1/_test/bad')

    assert not_allowed.status_code == 405
    assert not_allowed.get_json()['error']['code'] == 'method_not_allowed'
    assert bad.status_code == 400
    assert bad.is_json
    assert 'Proto' not in bad.get_data(as_text=True)

    app.config['WTF_CSRF_ENABLED'] = True
    csrf = client.post('/api/v1/conversations/test-conv/participation', json={})
    assert csrf.status_code == 400
    assert csrf.get_json()['error']['code'] == 'csrf_failed'


def test_unhandled_status_falls_back_to_the_server_error_page():
    from error_pages import render_error_page

    assert 'Something went wrong' in render_error_page(418)


def test_the_error_page_carries_the_text_direction(app):
    """Without dir an RTL locale renders left-to-right, and this is the page that renders
    when the SPA — which would otherwise fix it — is the thing that is broken."""
    import error_pages
    with app.test_request_context('/'):
        from flask import g
        g.locale, g.dir = 'he', 'rtl'
        page = error_pages.render_error_page(404)
    assert '<html lang="he" dir="rtl">' in page


def test_catalogue_text_cannot_inject_markup_into_the_error_page(app, tmp_path):
    """The copy now comes from a catalogue that translatewiki also writes to."""
    import error_pages, i18n
    directory = tmp_path / 'messages'
    directory.mkdir()
    (directory / 'en.json').write_text(
        '{"errorpage-404-title": "</title><script>alert(1)</script>"}', encoding='utf-8')
    i18n.load(str(directory))
    try:
        page = error_pages.render_error_page(404)
        assert '<script>alert(1)</script>' not in page
        assert '&lt;script&gt;' in page
    finally:
        i18n.load()


def test_the_error_page_still_renders_with_no_catalogue_at_all(tmp_path):
    """The guarantee the module exists for: it must not gain a new way to fail."""
    import error_pages, i18n
    empty = tmp_path / 'empty'
    empty.mkdir()
    i18n.load(str(empty))
    try:
        page = error_pages.render_error_page(403)
        assert 'Not allowed' in page
        assert 'ask an organizer' in page
        assert i18n._MISSING_L not in page
    finally:
        i18n.load()


@pytest.fixture
def delivered_catalogue(tmp_path):
    """Load a temporary catalogue for one test, and the real one again afterwards."""
    import i18n
    directory = tmp_path / 'i18n'
    directory.mkdir()
    yield directory
    i18n.load()


def test_a_hostile_translated_hint_does_not_reach_the_page_when_english_fails_to_load(app, delivered_catalogue):
    """The hint is rendered unescaped, so its markup check must not depend on English loading.

    Catches the check failing open: with no English to compare against, a translation would
    otherwise be served as it arrived. A malformed en.json is the degraded catalogue this module
    exists to survive."""
    import json

    import error_pages
    import i18n
    from flask import g

    (delivered_catalogue / 'en.json').write_text('{ not json', encoding='utf-8')
    (delivered_catalogue / 'nl.json').write_text(json.dumps({
        'errorpage-404-hint': 'Klik <img src=x onerror=alert(1)>',
    }), encoding='utf-8')
    i18n.load(str(delivered_catalogue))
    with app.test_request_context('/'):
        g.locale, g.dir = 'nl', 'ltr'
        body = error_pages.render_error_page(404)
    assert '<img' not in body
