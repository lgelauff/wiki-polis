import pytest

import app as app_module


@pytest.fixture(autouse=True)
def spa_build_fixture(app, tmp_path, monkeypatch):
    build_dir = tmp_path / 'spa'
    build_dir.mkdir()
    (build_dir / 'index.html').write_text(
        '<!doctype html><div id="root"></div>', encoding='utf-8',
    )
    monkeypatch.setattr(app_module, '_SPA_BUILD_DIR', str(build_dir))
    app.config['SPA_DEFAULT_ENABLED'] = True


def test_canonical_route_serves_react_by_default(client, conversation):
    response = client.get(f'/c/{conversation.slug}')

    assert response.status_code == 200
    assert b'<div id="root"></div>' in response.data


def test_explicit_jinja_fallback_reaches_legacy_route(client, conversation):
    response = client.get(f'/c/{conversation.slug}?spa_only=0')

    assert response.status_code == 302
    assert '/login' in response.headers['Location']
    assert 'wiki-polis-spa-only=0' in response.headers['Set-Cookie']


@pytest.mark.parametrize('page', ['settings', 'termination', 'roles'])
def test_react_only_admin_route_has_authorized_jinja_fallback(
    admin_client, conversation, page,
):
    response = admin_client.get(
        f'/admin/conversations/{conversation.id}/{page}?spa_only=0',
    )

    assert response.status_code == 302
    assert response.headers['Location'] == f'/admin/conversations/{conversation.id}'


@pytest.mark.parametrize('page', ['settings', 'termination', 'roles'])
def test_react_only_admin_fallback_preserves_permissions(
    auth_client, conversation, page,
):
    response = auth_client.get(
        f'/admin/conversations/{conversation.id}/{page}?spa_only=0',
    )

    assert response.status_code == 403


def test_spa_only_query_serves_react_shell_on_canonical_route(client, conversation):
    response = client.get(f'/c/{conversation.slug}?spa_only=1')

    assert response.status_code == 200
    assert b'<div id="root"></div>' in response.data
    assert 'wiki-polis-spa-only=1' in response.headers['Set-Cookie']


def test_spa_only_cookie_persists_and_can_be_disabled(client):
    enabled = client.get('/admin?spa_only=1')
    assert b'<div id="root"></div>' in enabled.data

    persisted = client.get('/consultations')
    assert b'<div id="root"></div>' in persisted.data

    disabled = client.get('/consultations?spa_only=0')
    assert b'<div id="root"></div>' not in disabled.data
    assert 'wiki-polis-spa-only=0' in disabled.headers['Set-Cookie']

    persisted_fallback = client.get('/admin')
    assert b'<div id="root"></div>' not in persisted_fallback.data


def test_spa_only_cookie_is_long_lived(client):
    response = client.get('/consultations?spa_only=1')

    assert 'Max-Age=31536000' in response.headers['Set-Cookie']


def test_jinja_header_offers_spa_toggle_only_in_local_debug(app, client):
    app.config['DEBUG'] = True

    response = client.get('/consultations?spa_only=0')

    assert b'role="switch"' in response.data
    assert b'SPA only <span>off</span>' in response.data


def test_jinja_header_offers_spa_toggle_on_toolforge_staging(monkeypatch, client):
    monkeypatch.setenv('TOOL_NAME', 'wiki-polis-dev')
    monkeypatch.setenv(
        'TOOL_TOOLFORGE_API_URL',
        'https://api.svc.tools.eqiad1.wikimedia.cloud',
    )

    response = client.get('/consultations?spa_only=0')

    assert b'role="switch"' in response.data
    assert b'SPA only <span>off</span>' in response.data


def test_jinja_header_hides_spa_toggle_in_toolforge_production(monkeypatch, client):
    monkeypatch.setenv('TOOL_NAME', 'wiki-polis')
    monkeypatch.setenv(
        'TOOL_TOOLFORGE_API_URL',
        'https://api.svc.tools.eqiad1.wikimedia.cloud',
    )

    response = client.get('/consultations?spa_only=0')

    assert b'SPA only <span>off</span>' not in response.data
