"""Direct tests for the Particiapi proxy and statement-submit bridge.

These cover the security-critical behaviours the main suite does NOT exercise. The
shared `app` fixture runs with `WTF_CSRF_ENABLED=False`, so it cannot catch a broken
`csrf.exempt(proxy_bp)` — yet CSRF exemption (with same-origin as the compensating
control) is the core proxy security posture. These tests lock the expected boundary:

- CSRF exemption is active on the generic proxy blueprint only;
- first-party statement submit is a participant route with normal CSRF plus the
  same-origin provenance check;
- the same-origin check still gates state-changing requests and fails closed
  when browser provenance headers are missing;
- the pa_session <-> session cookie rename is preserved in both directions;
- the 403->200 rewrite on /results/ that keeps the web component usable.
"""
import hashlib
import hmac
import re
from unittest.mock import MagicMock, patch

import pytest
from cachelib.file import FileSystemCache

from app import create_app
from db import Conversation, Participant, Participation, db


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
def csrf_enabled_app(tmp_path):
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
        yield app
        db.session.remove()


@pytest.fixture
def csrf_client(csrf_enabled_app):
    return csrf_enabled_app.test_client()


@pytest.mark.parametrize('path', ['/proxy/particiapi/api/foo'])
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


def test_proxy_post_blocks_missing_provenance_headers(auth_client):
    resp = auth_client.post('/proxy/particiapi/api/foo', json={})
    assert resp.status_code == 403


def test_proxy_post_allows_same_origin(auth_client):
    up = _fake_upstream()
    with patch('app.requests.request', return_value=up):
        resp = auth_client.post('/proxy/particiapi/api/foo',
                                headers={'Sec-Fetch-Site': 'same-origin'}, json={})
    assert resp.status_code == 200


# ── statement-submit participant route ────────────────────────────────────────────

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


def test_demo_proxy_allows_bound_vote_endpoint(client):
    conv = Conversation(slug='demo-proxy', polis_id='demoproxy1', title='Demo',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(conv)
    db.session.commit()
    client.get('/c/demo-proxy')

    up = _fake_upstream()
    with patch('app.requests.request', return_value=up) as req:
        resp = client.put('/proxy/particiapi/api/conversations/demoproxy1/votes/7',
                          headers={'Sec-Fetch-Site': 'same-origin'},
                          json={'value': 1})

    assert resp.status_code == 200
    assert req.called


def test_demo_proxy_blocks_statement_write_endpoint(client):
    conv = Conversation(slug='demo-proxy2', polis_id='demoproxy2', title='Demo',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(conv)
    db.session.commit()
    client.get('/c/demo-proxy2')

    with patch('app.requests.request') as req:
        resp = client.post('/proxy/particiapi/api/conversations/demoproxy2/statements/',
                           headers={'Sec-Fetch-Site': 'same-origin'},
                           json={'text': 'blocked'})

    assert resp.status_code == 403
    req.assert_not_called()


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


def test_statement_new_blocks_missing_provenance_headers(auth_client):
    resp = auth_client.post('/c/any/statements/new', json={'text': 'hi'})
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


def test_statement_new_requires_csrf_when_csrf_enabled(csrf_enabled_app):
    client = csrf_enabled_app.test_client()
    p = Participant(mw_user_id=10101, mw_username='csrfuser', xid='c' * 64)
    conv = Conversation(slug='csrf-sub', polis_id='csrfxxxxxx', title='CSRF',
                        active=True, access_policy='public', phase_submission=True)
    db.session.add_all([p, conv])
    db.session.commit()
    db.session.add(Participation(participant_id=p.id,
                                 conversation_id=conv.id,
                                 pseudonym='csrf-user'))
    db.session.commit()
    with client.session_transaction() as sess:
        sess['username'] = p.mw_username
        sess['xid'] = p.xid

    with patch('app.requests.post') as post:
        resp = client.post('/c/csrf-sub/statements/new',
                           headers={'Sec-Fetch-Site': 'same-origin'},
                           json={'text': 'Needs a token'})

    assert resp.status_code == 400
    post.assert_not_called()


def test_statement_new_accepts_valid_csrf_when_csrf_enabled(csrf_enabled_app):
    client = csrf_enabled_app.test_client()
    p = Participant(mw_user_id=20202, mw_username='csrfok', xid='d' * 64)
    conv = Conversation(slug='csrf-ok', polis_id='csrfokxxxx', title='CSRF OK',
                        active=True, access_policy='public', phase_submission=True,
                        argument_vote_data={'new_stmt_max': 3})
    db.session.add_all([p, conv])
    db.session.commit()
    db.session.add(Participation(participant_id=p.id,
                                 conversation_id=conv.id,
                                 pseudonym='csrf-ok'))
    db.session.commit()
    with client.session_transaction() as sess:
        sess['username'] = p.mw_username
        sess['xid'] = p.xid

    page = client.get('/c/csrf-ok')
    token_match = re.search(rb"var csrfToken = '([^']+)'", page.data)
    assert token_match is not None
    csrf_token = token_match.group(1).decode()

    sess_resp = _fake_upstream(cookies={'session': 'NEWPA'})
    sess_resp.ok = True
    sess_resp.json = lambda: {'csrf_token': 'TOK'}
    stmt_resp = _fake_upstream(status_code=201, content=b'{"id":556}')
    stmt_resp.json = lambda: {'id': 556}

    with patch('app.requests.post', side_effect=[sess_resp, stmt_resp]):
        resp = client.post('/c/csrf-ok/statements/new',
                           headers={
                               'Sec-Fetch-Site': 'same-origin',
                               'X-CSRFToken': csrf_token,
                           },
                           json={'text': 'A token-backed idea'})

    assert resp.status_code == 201


def test_statement_new_allows_missing_provenance_after_valid_manual_csrf(csrf_enabled_app):
    """Safari-style fetches may omit Fetch Metadata; the CSRF token remains required."""
    client = csrf_enabled_app.test_client()
    p = Participant(mw_user_id=30303, mw_username='csrfonly', xid='e' * 64)
    conv = Conversation(slug='csrf-only', polis_id='csrfonlyxx', title='CSRF Only',
                        active=True, access_policy='public', phase_submission=True,
                        argument_vote_data={'new_stmt_max': 3})
    db.session.add_all([p, conv])
    db.session.commit()
    db.session.add(Participation(participant_id=p.id,
                                 conversation_id=conv.id,
                                 pseudonym='csrf-only'))
    db.session.commit()
    with client.session_transaction() as sess:
        sess['username'] = p.mw_username
        sess['xid'] = p.xid

    page = client.get('/c/csrf-only')
    token_match = re.search(rb"var csrfToken = '([^']+)'", page.data)
    assert token_match is not None
    csrf_token = token_match.group(1).decode()

    sess_resp = _fake_upstream(cookies={'session': 'NEWPA'})
    sess_resp.ok = True
    sess_resp.json = lambda: {'csrf_token': 'TOK'}
    stmt_resp = _fake_upstream(status_code=201, content=b'{"id":557}')
    stmt_resp.json = lambda: {'id': 557}

    with patch('app.requests.post', side_effect=[sess_resp, stmt_resp]):
        resp = client.post('/c/csrf-only/statements/new',
                           headers={'X-CSRFToken': csrf_token},
                           json={'text': 'A CSRF-backed browser submit'})

    assert resp.status_code == 201


# ── Upstream redirects must NOT be followed (PR #245 review, Issue 1) ─────────────

def test_proxy_does_not_follow_upstream_redirect(auth_client):
    """A proxy hands 3xx back to the browser; it must never follow them itself.
    `requests` preserves custom headers (incl. X-Particiapi-Sub-Secret) across
    cross-host redirects, so following one could replay the shared secret."""
    up = _fake_upstream(status_code=302, content=b'')
    up.headers = {'Content-Type': 'text/html', 'Location': 'https://evil.example/'}
    with patch('app.requests.request', return_value=up) as req:
        resp = auth_client.get('/proxy/particiapi/api/conversations/abc/')
    assert resp.status_code == 302  # passed back unchanged, not chased
    assert req.call_args.kwargs['allow_redirects'] is False
    # a 3xx handed back with no Location is useless to the browser
    assert resp.headers.get('Location') == 'https://evil.example/'


def test_proxy_vote_redirect_does_not_count_as_engagement(bind_client):
    """upstream.ok is True for 3xx too; a redirected-not-confirmed vote must not
    be credited as engagement now that redirects are surfaced instead of chased."""
    conv = _make_conv('bind-r', 'bindr00001')
    up = _fake_upstream(status_code=302, content=b'')
    up.headers = {'Location': 'https://particiapi.example/'}
    with patch('app.requests.request', return_value=up):
        with patch('app._touch_last_engagement') as touch:
            bind_client.post(f'/c/bind-r/proxy/particiapi/api/conversations/{conv.polis_id}/votes',
                             headers=_SAME_ORIGIN, json={})
    touch.assert_not_called()


# ── Identity binding on POST /api/session (PR #245) ──────────────────────────────
#
# The shared `app` fixture leaves PARTICIAPI_SUB_SECRET unset, so the bind path is
# otherwise never exercised. `bind_client` configures the secret AND logs in, which
# are the two preconditions (alongside POST api/session on a scoped route) for a bind.

_BIND_SECRET = 'sub-secret'
_SAME_ORIGIN = {'Sec-Fetch-Site': 'same-origin'}


@pytest.fixture
def bind_client(app, participant):
    app.config['PARTICIAPI_SUB_SECRET'] = _BIND_SECRET
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = participant.mw_username
        sess['xid'] = participant.xid
    return client


def _make_conv(slug, polis_id):
    c = Conversation(slug=slug, polis_id=polis_id, title=slug.upper(),
                     active=True, access_policy='public')
    db.session.add(c)
    db.session.commit()
    return c


def _expected_subject(xid, conv_id):
    """Re-derive the conversation-scoped subject independently, so a change to the
    keying scheme in app.py breaks this test instead of silently passing."""
    return hmac.new(_BIND_SECRET.encode(), f'{xid}:{conv_id}'.encode(),
                    hashlib.sha256).hexdigest()


def test_scoped_session_post_binds_conversation_subject(bind_client, participant):
    conv = _make_conv('bind-a', 'binda00001')
    up = _fake_upstream(cookies={'session': 'NEWBOUND'})
    with patch('app.requests.request', return_value=up) as req:
        resp = bind_client.post('/c/bind-a/proxy/particiapi/api/session',
                                headers=_SAME_ORIGIN, json={})
    assert resp.status_code == 200
    sent = req.call_args.kwargs['headers']
    assert sent['X-Particiapi-Sub'] == _expected_subject(participant.xid, conv.id)
    assert sent['X-Particiapi-Sub-Secret'] == _BIND_SECRET
    # bare xid must never be the asserted subject on a scoped bind
    assert sent['X-Particiapi-Sub'] != participant.xid


def test_scoped_subject_differs_per_conversation(bind_client, participant):
    """The core #246 privacy property: same person → different subject per conv,
    and never the bare xid."""
    _make_conv('bind-1', 'bind100001')
    _make_conv('bind-2', 'bind200002')
    subs = []
    for slug in ('bind-1', 'bind-2'):
        up = _fake_upstream()
        with patch('app.requests.request', return_value=up) as req:
            bind_client.post(f'/c/{slug}/proxy/particiapi/api/session',
                             headers=_SAME_ORIGIN, json={})
        subs.append(req.call_args.kwargs['headers']['X-Particiapi-Sub'])
    assert subs[0] != subs[1]
    assert participant.xid not in subs


def test_scoped_subject_stable_within_conversation(bind_client):
    _make_conv('bind-s', 'binds00001')
    seen = []
    for _ in range(2):
        up = _fake_upstream()
        with patch('app.requests.request', return_value=up) as req:
            bind_client.post('/c/bind-s/proxy/particiapi/api/session',
                             headers=_SAME_ORIGIN, json={})
        seen.append(req.call_args.kwargs['headers']['X-Particiapi-Sub'])
    assert seen[0] == seen[1]  # stable across devices/sessions within one conversation


def test_bind_drops_stale_pa_session_cookie(bind_client):
    """On a bind the stale (possibly anonymous) pa_session must NOT be forwarded,
    or Particiapi skips the bind path and pins a throwaway uid forever."""
    _make_conv('bind-c', 'bindc00001')
    bind_client.set_cookie('pa_session', 'STALE_ANON')
    up = _fake_upstream()
    with patch('app.requests.request', return_value=up) as req:
        bind_client.post('/c/bind-c/proxy/particiapi/api/session',
                         headers=_SAME_ORIGIN, json={})
    assert 'session' not in req.call_args.kwargs['cookies']


def test_bind_only_on_session_post(bind_client):
    """Exposure-surplus guard: the secret/subject go out ONLY on POST api/session,
    never on other paths or methods."""
    _make_conv('bind-x', 'bindx00001')
    up = _fake_upstream()
    with patch('app.requests.request', return_value=up) as req:
        bind_client.post('/c/bind-x/proxy/particiapi/api/votes/3',
                         headers=_SAME_ORIGIN, json={})
        post_headers = req.call_args.kwargs['headers']
        bind_client.get('/c/bind-x/proxy/particiapi/api/session')
        get_headers = req.call_args.kwargs['headers']
    for h in (post_headers, get_headers):
        assert 'X-Particiapi-Sub' not in h
        assert 'X-Particiapi-Sub-Secret' not in h


def test_no_bind_without_secret(auth_client):
    """Secret unset → legacy anonymous behaviour: no sub headers, ?create=true added."""
    _make_conv('bind-n', 'bindn00001')
    up = _fake_upstream()
    with patch('app.requests.request', return_value=up) as req:
        auth_client.post('/c/bind-n/proxy/particiapi/api/session',
                         headers=_SAME_ORIGIN, json={})
    sent = req.call_args.kwargs
    assert 'X-Particiapi-Sub' not in sent['headers']
    assert sent['params'].get('create') == 'true'


def test_unscoped_route_never_emits_identity_headers(bind_client):
    """Privacy tripwire (#246): the legacy unscoped route must NEVER bind identity,
    so a logged-in user is never re-linked across conversations via a bare xid.
    NOTE: this MUST run under `bind_client` (secret set + xid present) — with the
    no-secret `auth_client` it would pass even if the `conv is None` guard were
    deleted, i.e. it would test nothing. Do not 'simplify' the fixture."""
    up = _fake_upstream()
    with patch('app.requests.request', return_value=up) as req:
        bind_client.post('/proxy/particiapi/api/session',
                         headers=_SAME_ORIGIN, json={})
    sent = req.call_args.kwargs
    assert 'X-Particiapi-Sub' not in sent['headers']
    assert 'X-Particiapi-Sub-Secret' not in sent['headers']
    assert sent['params'].get('create') == 'true'  # falls back to anonymous create


# ── Cleartext-transport warning for the sub-secret (PR #245 review, Issue 2) ──────

def test_is_secure_pa_transport():
    from app import _is_secure_pa_transport
    assert _is_secure_pa_transport('https://particiapi.example')
    assert _is_secure_pa_transport('http://localhost:8000')
    assert _is_secure_pa_transport('http://127.0.0.1:8000')
    assert _is_secure_pa_transport('http://[::1]:8000')
    assert not _is_secure_pa_transport('http://10.0.0.5:8000')      # private but cleartext
    assert not _is_secure_pa_transport('http://particiapi.example')  # cleartext non-loopback


def test_bind_warns_on_cleartext_but_still_binds(bind_client, app, caplog):
    """Cleartext non-loopback transport logs a loud warning on bind, but still binds —
    the warning must not silently disable the live cross-device feature."""
    import logging
    app.config['PARTICIAPI_BASE'] = 'http://10.0.0.5:8000'
    _make_conv('bind-w', 'bindw00001')
    up = _fake_upstream()
    with caplog.at_level(logging.WARNING), \
            patch('app.requests.request', return_value=up) as req:
        bind_client.post('/c/bind-w/proxy/particiapi/api/session',
                         headers=_SAME_ORIGIN, json={})
    assert 'X-Particiapi-Sub-Secret' in req.call_args.kwargs['headers']  # still binds
    assert any('cleartext non-loopback' in r.message for r in caplog.records)


def test_bind_no_warning_on_loopback(bind_client, app, caplog):
    import logging
    app.config['PARTICIAPI_BASE'] = 'http://localhost:8000'
    _make_conv('bind-l', 'bindl00001')
    up = _fake_upstream()
    with caplog.at_level(logging.WARNING), \
            patch('app.requests.request', return_value=up):
        bind_client.post('/c/bind-l/proxy/particiapi/api/session',
                         headers=_SAME_ORIGIN, json={})
    assert not any('cleartext non-loopback' in r.message for r in caplog.records)
