def test_canonical_route_keeps_jinja_as_default_fallback(client, conversation):
    response = client.get(f'/c/{conversation.slug}')

    assert response.status_code == 302
    assert '/login' in response.headers['Location']


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
    assert 'wiki-polis-spa-only=;' in disabled.headers['Set-Cookie']
