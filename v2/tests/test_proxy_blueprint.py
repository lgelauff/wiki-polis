"""Direct tests for the proxy + statement-submit blueprint (issue #91, step 7).

These cover the security-critical behaviours the main suite does NOT exercise. The
shared `app` fixture runs with `WTF_CSRF_ENABLED=False`, so it cannot catch a broken
`csrf.exempt(proxy_bp)` — yet CSRF exemption (with same-origin as the compensating
control) is the whole security posture of these two routes. The extraction onto a
blueprint must keep all of this byte-identical to the prior inline routes:

- CSRF exemption is active on the blueprint;
- the same-origin check still gates state-changing requests;
- the pa_session <-> session cookie rename is preserved in both directions;
- the 403->200 rewrite on /results/ that keeps the web component usable.
"""
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from cachelib.file import FileSystemCache

from app import create_app
from db import Conversation, Participation, db


def _fake_upstream(status_code=200, content=b'{}', cookies=None,
                   content_type='application/json'):
    """Stand-in for a `requests` Response from Particiapi."""
    m = MagicMock()
    m.status_code = status_code
    m.content = content
    m.headers = {'Content-Type': content_type}
    m.cookies = cookies or {}
    return m


# ── CSRF exemption — needs a CSRF-ENABLED app (the shared fixture disables it) ────

@pytest.fixture
def csrf_client(tmp_path):
    session_dir = tmp_path / 'sessions'
    session_dir.mkdir()
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/t.db',
        'WTF_CSRF_ENABLED': True,
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'test-secret',
        'SESSION_TYPE': 'cachelib',
        'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
    })
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()


@pytest.mark.parametrize('path', ['/proxy/particiapi/api/foo',
                                  '/c/any-slug/statements/new'])
def test_blueprint_routes_are_csrf_exempt(csrf_client, path):
    # No CSRF token, not logged in. If the blueprint were NOT exempt, Flask-WTF would
    # reject at before_request with 400 'CSRF token missing'. Because it IS exempt the
    # request reaches the view, where @login_required redirects to login (302). So a
    # 400 here would mean the exemption silently broke in the extraction.
    resp = csrf_client.post(path, json={'text': 'x'})
    assert resp.status_code != 400, 'CSRF exemption broke — request rejected pre-view'
    assert resp.status_code == 302  # login redirect from inside the view


# ── Proxy cookie rename (both directions) ────────────────────────────────────────

def test_proxy_renames_upstream_session_to_pa_session(auth_client):
    up = _fake_upstream(cookies={'session': 'UPSTREAM123'})
    with patch('app.requests.request', return_value=up):
        resp = auth_client.get('/proxy/particiapi/api/conversations/abc/')
    set_cookies = resp.headers.getlist('Set-Cookie')
    # Particiapi's 'session' is re-emitted to the browser as 'pa_session', never raw.
    assert any(c.startswith('pa_session=UPSTREAM123') for c in set_cookies)
    assert not any(c.startswith('session=UPSTREAM123') for c in set_cookies)


def test_proxy_forwards_pa_session_as_session(auth_client):
    auth_client.set_cookie('pa_session', 'BROWSER456')
    up = _fake_upstream()
    with patch('app.requests.request', return_value=up) as req:
        auth_client.get('/proxy/particiapi/api/conversations/abc/')
    # The browser's 'pa_session' is forwarded upstream as Particiapi's 'session'.
    assert req.call_args.kwargs['cookies'] == {'session': 'BROWSER456'}


# ── 403 -> 200 rewrite (only on /results/) ───────────────────────────────────────

def test_proxy_rewrites_results_403_to_200(auth_client):
    up = _fake_upstream(status_code=403, content=b'forbidden')
    with patch('app.requests.request', return_value=up):
        resp = auth_client.get(
            '/proxy/particiapi/api/conversations/abc/math/results/')
    # Pre-math /results/ 403 would blank the UI; rewrite to an empty 200 instead.
    assert resp.status_code == 200
    assert resp.get_data() == b'{}'


def test_proxy_passes_through_non_results_403(auth_client):
    up = _fake_upstream(status_code=403, content=b'nope')
    with patch('app.requests.request', return_value=up):
        resp = auth_client.get('/proxy/particiapi/api/conversations/abc/')
    assert resp.status_code == 403  # the rewrite is scoped to /results/ only


# ── Same-origin compensating control ─────────────────────────────────────────────

def test_proxy_post_blocks_cross_origin(auth_client):
    resp = auth_client.post('/proxy/particiapi/api/foo',
                            headers={'Sec-Fetch-Site': 'cross-site'}, json={})
    assert resp.status_code == 403


def test_proxy_post_allows_same_origin(auth_client):
    up = _fake_upstream()
    with patch('app.requests.request', return_value=up):
        resp = auth_client.post('/proxy/particiapi/api/foo',
                                headers={'Sec-Fetch-Site': 'same-origin'}, json={})
    assert resp.status_code == 200


# ── statement-submit route on the blueprint ──────────────────────────────────────

def test_proxy_rejects_path_traversal_and_non_api(auth_client):
    # CRIT-1 guard: only /api/ paths, no '..' segments — must never reach upstream.
    with patch('app.requests.request') as req:
        assert auth_client.get('/proxy/particiapi/api/../secret').status_code == 404
        assert auth_client.get('/proxy/particiapi/etc/passwd').status_code == 404
    req.assert_not_called()


def test_proxy_strips_unknown_query_params(auth_client):
    # HIGH-5 allowlist: only known-safe params are forwarded to Particiapi.
    up = _fake_upstream()
    with patch('app.requests.request', return_value=up) as req:
        auth_client.get('/proxy/particiapi/api/conversations/abc/'
                        '?zinvite=ok&evil=DROP&tid=3')
    assert req.call_args.kwargs['params'] == {'zinvite': 'ok', 'tid': '3'}


def test_statement_new_enforces_quota(auth_client, participant):
    conv = Conversation(slug='q', polis_id='qxxxxxxxxx', title='Q', active=True,
                        access_policy='public', phase_submission=True,
                        argument_vote_data={'new_stmt_max': 1})
    db.session.add(conv)
    db.session.commit()
    db.session.add(Participation(participant_id=participant.id,
                                 conversation_id=conv.id, pseudonym='p',
                                 new_stmt_ids=[101]))  # already at the cap of 1
    db.session.commit()
    with patch('app.requests.post') as post:
        resp = auth_client.post('/c/q/statements/new',
                                headers={'Sec-Fetch-Site': 'same-origin'},
                                json={'text': 'one too many'})
    assert resp.status_code == 403
    assert resp.get_json() == {'error': 'quota_exceeded'}
    post.assert_not_called()  # quota rejected before any upstream call


def test_statement_new_blocks_cross_origin(auth_client):
    resp = auth_client.post('/c/any/statements/new',
                            headers={'Sec-Fetch-Site': 'cross-site'},
                            json={'text': 'hi'})
    assert resp.status_code == 403


def test_statement_new_happy_path_records_polis_id(auth_client, participant):
    conv = Conversation(slug='sub', polis_id='subxxxxxxx', title='Sub', active=True,
                        access_policy='public', phase_submission=True,
                        argument_vote_data={'new_stmt_max': 3})
    db.session.add(conv)
    db.session.commit()
    db.session.add(Participation(participant_id=participant.id,
                                 conversation_id=conv.id, pseudonym='p'))
    db.session.commit()

    sess_resp = _fake_upstream(cookies={'session': 'NEWPA'})
    sess_resp.ok = True
    sess_resp.json = lambda: {'csrf_token': 'TOK'}
    stmt_resp = _fake_upstream(status_code=201, content=b'{"id":555}')
    stmt_resp.json = lambda: {'id': 555}

    with patch('app.requests.post', side_effect=[sess_resp, stmt_resp]):
        resp = auth_client.post('/c/sub/statements/new',
                                headers={'Sec-Fetch-Site': 'same-origin'},
                                json={'text': 'A genuinely new idea'})

    assert resp.status_code == 201
    part = Participation.query.filter_by(conversation_id=conv.id).first()
    assert 555 in (part.new_stmt_ids or [])  # Polis id recorded for novelty tracking
    assert any(c.startswith('pa_session=NEWPA')
               for c in resp.headers.getlist('Set-Cookie'))
