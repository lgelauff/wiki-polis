"""The server's SPA route table, and the guard that keeps it from drifting.

With the Jinja frontend gone there is no fallback: a canonical path is answered
with the React shell, and anything outside the table 404s (see test_error_pages).
That is a deliberate choice over a catch-all — it is what keeps the branded 404
reachable — but an explicit table can drift out of step with the React router,
which is how #310 shipped three React routes with no server counterpart.

test_every_react_route_has_a_server_counterpart is the fix: it reads the route
table straight out of the React sources, so adding a React route without adding
it to _SPA_ROUTE_PATTERNS fails here instead of 404ing in production.

A guard that reads source is only as good as its parse, and this one has failed
quietly twice over in principle:

  * it required `path` to be the first attribute, so `<Route element={…} path="/x" />`
    — a shape Prettier can produce on reflow — parsed to nothing; and
  * an empty parametrize list is a *skip*, not a failure (pytest's
    `empty_parameter_set_mark` defaults to `skip` and pyproject.toml does not
    override it), and this file already contains one legitimate skip for the
    catch-all, so a second would not have looked wrong.

Together those meant a rename or a reflow of app.tsx would have turned the guard
into a no-op reporting "passed". So the parse now globs the whole SPA source tree,
does not care about attribute order, and
test_the_react_route_parse_is_not_silently_empty asserts a floor on what it found
— that one fails loudly where an empty parametrize would only have skipped.
"""

import re
from pathlib import Path

import pytest

import app as app_module

SPA_SRC = Path(__file__).resolve().parents[1] / 'frontend' / 'src'

# A floor, not an exact count: it exists to catch a parse that collapsed to
# nothing (or nearly), not to force an edit every time a route is added or
# removed. app.tsx carries 47 routes at the time of writing.
_MINIMUM_REACT_ROUTES = 40

# `\b` keeps this off `<Routes>`, the container element.
_ROUTE_TAG = re.compile(r'<Route\b')
_PATH_ATTR = re.compile(r'\bpath="([^"]*)"')

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
    """Every `path` on a `<Route>` anywhere in the SPA sources.

    Attribute order is irrelevant: each `<Route` opens a window that runs to the
    next `<Route` (or end of file), and the first `path="…"` in that window is the
    route's own. `element={<Page />}` cannot be mistaken for one, so the window
    does not need to know where the tag ends — which matters, because the `/>`
    inside an `element` prop means the tag's own `>` cannot be found by eye.
    """
    paths: list[str] = []
    for source_file in sorted(SPA_SRC.rglob('*.tsx')):
        source = source_file.read_text(encoding='utf-8')
        tag_starts = [match.end() for match in _ROUTE_TAG.finditer(source)]
        for index, start in enumerate(tag_starts):
            end = tag_starts[index + 1] if index + 1 < len(tag_starts) else len(source)
            match = _PATH_ATTR.search(source, start, end)
            if match:
                paths.append(match.group(1))
    return paths


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


def test_the_react_route_parse_is_not_silently_empty():
    """The guard below is parametrized over a source parse, and an empty parametrize
    list *skips* rather than fails. Assert the floor here so a rename, a reflow or a
    move of the route table breaks the build instead of quietly reporting 'passed'."""
    routes = _react_route_paths()

    assert len(routes) >= _MINIMUM_REACT_ROUTES, (
        f'parsed only {len(routes)} React routes from {SPA_SRC}; expected at least '
        f'{_MINIMUM_REACT_ROUTES}. The route table has probably moved or changed '
        f'shape — fix _react_route_paths rather than lowering the floor, or the '
        f'server/React drift guard stops guarding anything.'
    )


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
