"""The server's SPA route table, and the guard that keeps it from drifting.

With the Jinja frontend gone there is no fallback: a canonical path is answered
with the React shell, and anything outside the table 404s (see test_error_pages).
That is a deliberate choice over a catch-all — it is what keeps the branded 404
reachable — but an explicit table can drift out of step with the React router,
which is how #310 shipped three React routes with no server counterpart.

test_every_react_route_has_a_server_counterpart is the fix: it reads the route
table straight out of frontend/src/app.tsx, so adding a React route without
adding it to _SPA_ROUTE_PATTERNS fails here instead of 404ing in production.
"""

import re
from pathlib import Path

import pytest

import app as app_module

APP_TSX = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'app.tsx'

# React path params -> a concrete path segment the server table should accept.
_SAMPLE_SEGMENTS = {
    'conversationId': '42',
    'outputKey': 'report',
}


@pytest.fixture(autouse=True)
def spa_build_fixture(app, tmp_path, monkeypatch):
    build_dir = tmp_path / 'spa'
    build_dir.mkdir()
    (build_dir / 'index.html').write_text(
        '<!doctype html><div id="root"></div>', encoding='utf-8',
    )
    monkeypatch.setattr(app_module, '_SPA_BUILD_DIR', str(build_dir))


def _react_route_paths() -> list[str]:
    source = APP_TSX.read_text(encoding='utf-8')
    return re.findall(r'<Route\s+path="([^"]+)"', source)


def _as_concrete_path(route: str) -> str:
    """Turn a React route pattern into one example path a browser could request."""
    return '/'.join(
        _SAMPLE_SEGMENTS.get(part[1:], 'sample-slug') if part.startswith(':') else part
        for part in route.split('/')
    )


def test_canonical_route_serves_react_by_default(client, conversation):
    response = client.get(f'/c/{conversation.slug}')

    assert response.status_code == 200
    assert b'<div id="root"></div>' in response.data


def test_admin_route_with_no_view_function_still_serves_the_shell(client, conversation):
    """These paths have no Flask endpoint at all — the before-request hook owns them."""
    response = client.get(f'/admin/conversations/{conversation.id}/settings')

    assert response.status_code == 200
    assert b'<div id="root"></div>' in response.data


@pytest.mark.parametrize('route', sorted(set(_react_route_paths())))
def test_every_react_route_has_a_server_counterpart(client, route):
    """Guard against the #310 failure: a React route the server does not know."""
    if route == '*':
        pytest.skip('client-side catch-all, not a server path')
    path = _as_concrete_path(route)

    # /app/* is served by the spa_shell view rather than the canonical table.
    if path.startswith('/app'):
        assert client.get(path).status_code == 200
        return

    assert app_module._is_canonical_spa_path(path), (
        f'{route} is routed by app.tsx but not by _SPA_ROUTE_PATTERNS in app.py'
    )
    assert client.get(path).status_code == 200


def test_a_path_outside_the_table_is_not_served_the_shell(client):
    """The other half of the bargain: unknown paths must stay 404, not 200."""
    response = client.get('/c/some-slug/not-a-real-tab')

    assert response.status_code == 404
    assert b'<div id="root"></div>' not in response.data
