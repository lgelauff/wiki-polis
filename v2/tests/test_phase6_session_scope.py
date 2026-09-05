"""Phase 6 Particiapi sessions must be scoped per conversation, not per browser session.

Phase 2 keys its Particiapi session state per conversation
(``session['particiapi_api_sessions'][str(conv.id)]``). Phase 6 used to store a single
cookie/CSRF pair in two GLOBAL Flask-session scalars, ``_p6_pa`` / ``_p6_csrf``. Because
both Phase 6 write paths bootstrap only when that cookie is missing, and
``ExploreGateway.ensure_session`` is the only place ``X-Particiapi-Sub`` is ever sent, the
FIRST Phase 6 round a participant entered minted and bound the session, and every later
round in the same browser session reused it — skipping the bootstrap and never binding its
own conversation-scoped subject.

Two consequences, both covered here:

* the later round's votes land on an unbound Polis uid — confirmed on staging by direct
  query, one browser session four minutes apart: ``bound = t`` on the Phase 2 zid and
  ``bound = f`` on the Phase 6 zid;
* one Polis uid spans every Phase 6 round that participant enters, which is exactly the
  cross-conversation linkage chain ``_conversation_subject`` is keyed on ``conv.id`` to
  prevent (#246, enforced by construction on the proxy route by #263).

The tell that the global scalars were an oversight rather than a decision: the
process-local ``_p6_session_cache`` beside them was already keyed ``(xid, conv.id)``.
"""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

import app as app_module
from db import Conversation, FeaturedStatement, Participation, db

SECRET = 'shared-upstream-secret'


def _response(payload=None, *, status=200, cookies=None):
    response = MagicMock()
    response.status_code = status
    response.ok = status < 400
    response.content = b'{}' if payload is not None else b''
    response.json.return_value = payload or {}
    response.cookies = cookies or {}
    return response


def _session_response(cookie, csrf):
    return _response({'csrf_token': csrf}, cookies={'session': cookie})


def _subject(xid, conv_id):
    """Re-derive the conversation-scoped subject independently of app.py, so a change to
    the keying scheme breaks this test instead of silently passing."""
    return hmac.new(
        SECRET.encode(), f'{xid}:{conv_id}'.encode(), hashlib.sha256,
    ).hexdigest()


def _p6_conversation(participant, slug, *, polis_id, phase6_id):
    """A conversation with Phase 2 and Phase 6 both open, joined by ``participant``."""
    conv = Conversation(
        slug=slug, polis_id=polis_id, title=slug.title(), active=True,
        access_policy='public', phase_submission=True, phase_informed_voting=True,
        phase6_polis_conversation_id=phase6_id,
    )
    db.session.add(conv)
    db.session.flush()
    statement = FeaturedStatement(
        conversation_id=conv.id, polis_statement_id=11, phase6_polis_statement_id=51,
        statement_text='A featured statement', confirmed_by_admin=True,
    )
    db.session.add_all([
        Participation(participant_id=participant.id, conversation_id=conv.id,
                      pseudonym=f'{slug}-otter'),
        statement,
    ])
    db.session.commit()
    return conv, statement


def _informed_vote(client, slug, fs_id, choice='agree'):
    return client.put(
        f'/api/v1/conversations/{slug}/featured-statements/{fs_id}/informed-vote',
        json={'choice': choice},
    )


# ── The regression ────────────────────────────────────────────────────────────

def test_phase6_session_is_not_shared_across_conversations(app, auth_client, participant):
    """Two conversations, one browser session: each Phase 6 round gets its OWN session.

    This is the regression test. Before the fix, conversation B found conversation A's
    cookie in ``_p6_pa``, skipped the bootstrap entirely, and voted through A's Polis
    identity — so ``post.call_count`` was 1, not 2.
    """
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    conv_a, fs_a = _p6_conversation(
        participant, 'p6-alpha', polis_id='alpha-p2', phase6_id='alpha-p6')
    conv_b, fs_b = _p6_conversation(
        participant, 'p6-beta', polis_id='beta-p2', phase6_id='beta-p6')
    xid, a_id, b_id = participant.xid, conv_a.id, conv_b.id

    with patch('app.polis_http.post', side_effect=[
        _session_response('cookie-A', 'csrf-A'),
        _session_response('cookie-B', 'csrf-B'),
    ]) as post, patch('app.polis_http.put', return_value=_response({})) as put:
        first = _informed_vote(auth_client, 'p6-alpha', fs_a.id)
        second = _informed_vote(auth_client, 'p6-beta', fs_b.id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert post.call_count == 2, (
        'the second conversation reused the first conversation\'s Phase 6 Particiapi '
        'session instead of bootstrapping and binding its own'
    )
    assert [c.kwargs['cookies']['session'] for c in put.call_args_list] == [
        'cookie-A', 'cookie-B',
    ]
    # Each round asserted ITS OWN conversation-scoped subject.
    subjects = [c.kwargs['headers']['X-Particiapi-Sub'] for c in post.call_args_list]
    assert subjects == [_subject(xid, a_id), _subject(xid, b_id)]
    assert subjects[0] != subjects[1], 'one Polis uid spanned both conversations'
    assert xid not in subjects


def test_legacy_phase6_route_does_not_share_a_session_across_conversations(
    app, auth_client, participant,
):
    """Same regression on the legacy Jinja ``/c/<slug>/phase6/vote`` route.

    It manipulates ``_p6_pa`` directly and shares ``_p6_session_cache`` with the API path,
    so fixing only one surface would leave the other leaking — and, because the cache is
    shared, would let the broken surface hand a wrongly-scoped session to the fixed one.
    """
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    conv_a, fs_a = _p6_conversation(
        participant, 'p6-gamma', polis_id='gamma-p2', phase6_id='gamma-p6')
    conv_b, fs_b = _p6_conversation(
        participant, 'p6-delta', polis_id='delta-p2', phase6_id='delta-p6')
    xid, a_id, b_id = participant.xid, conv_a.id, conv_b.id

    with patch.object(app_module.polis_http, 'post', side_effect=[
        _session_response('cookie-A', 'csrf-A'),
        _session_response('cookie-B', 'csrf-B'),
    ]) as post, patch.object(
        app_module.polis_http, 'put', return_value=_response({}),
    ) as put:
        first = auth_client.post('/c/p6-gamma/phase6/vote',
                                 json={'fs_id': fs_a.id, 'vote': -1})
        second = auth_client.post('/c/p6-delta/phase6/vote',
                                  json={'fs_id': fs_b.id, 'vote': -1})

    assert first.status_code == 200
    assert second.status_code == 200
    assert post.call_count == 2, (
        'the legacy route reused the first conversation\'s Phase 6 session'
    )
    assert [c.kwargs['cookies']['session'] for c in put.call_args_list] == [
        'cookie-A', 'cookie-B',
    ]
    subjects = [c.kwargs['headers']['X-Particiapi-Sub'] for c in post.call_args_list]
    assert subjects == [_subject(xid, a_id), _subject(xid, b_id)]


def test_stale_global_phase6_session_is_discarded_not_migrated(
    app, auth_client, participant,
):
    """A stored ``_p6_pa`` is either unbound or bound to the WRONG conversation's subject.

    Carrying it forward under the new per-conversation key would preserve the bug, so it is
    dropped: one extra bootstrap, correctly bound. The stale keys must not linger in the
    session store either.
    """
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    conv, fs = _p6_conversation(
        participant, 'p6-stale', polis_id='stale-p2', phase6_id='stale-p6')

    with auth_client.session_transaction() as browser_session:
        browser_session['_p6_pa'] = 'LEAKED-COOKIE'
        browser_session['_p6_csrf'] = 'LEAKED-CSRF'

    with patch('app.polis_http.post',
               return_value=_session_response('fresh-cookie', 'fresh-csrf')) as post, \
         patch('app.polis_http.put', return_value=_response({})) as put:
        response = _informed_vote(auth_client, 'p6-stale', fs.id)

    assert response.status_code == 200
    assert post.call_count == 1, 'the stale global session was reused instead of discarded'
    assert put.call_args.kwargs['cookies'] == {'session': 'fresh-cookie'}
    with auth_client.session_transaction() as browser_session:
        assert '_p6_pa' not in browser_session
        assert '_p6_csrf' not in browser_session
        assert browser_session['phase6_api_sessions'][str(conv.id)] == {
            'cookie': 'fresh-cookie', 'csrfToken': 'fresh-csrf',
        }


# ── What the fix must NOT break ───────────────────────────────────────────────

def test_phase6_session_is_reused_across_votes_in_one_conversation(
    app, auth_client, participant,
):
    """The 2026-07-08 per-vote reuse optimisation (6e85cea) must survive the scoping fix.

    ``_p6_session_cache`` is cleared between the two votes on purpose: without that, the
    process-local cache alone would satisfy this assertion and the test would say nothing
    about whether the FLASK session state is being reused.
    """
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    _conv, fs = _p6_conversation(
        participant, 'p6-reuse', polis_id='reuse-p2', phase6_id='reuse-p6')

    with patch('app.polis_http.post',
               return_value=_session_response('cookie-R', 'csrf-R')) as post, \
         patch('app.polis_http.put', return_value=_response({})) as put:
        first = _informed_vote(auth_client, 'p6-reuse', fs.id)
        app_module._p6_session_cache.clear()
        second = _informed_vote(auth_client, 'p6-reuse', fs.id, choice='disagree')

    assert first.status_code == 200
    assert second.status_code == 200
    assert post.call_count == 1, 'the fix re-bootstrapped instead of reusing the session'
    assert put.call_count == 2
    assert [c.kwargs['cookies']['session'] for c in put.call_args_list] == [
        'cookie-R', 'cookie-R',
    ]


def test_phase2_and_phase6_of_one_conversation_do_not_share_a_session(
    app, auth_client, participant,
):
    """The two rounds are separate Polis conversations and keep separate Particiapi
    sessions, even though ``_conversation_subject`` deliberately gives them one subject.

    A per-conversation Phase 6 key that collided with Phase 2's would silently hand the
    Phase 2 session to Phase 6 — the same class of bug, one scope down.
    """
    app.config['PARTICIAPI_SUB_SECRET'] = SECRET
    conv, fs = _p6_conversation(
        participant, 'p6-both', polis_id='both-p2', phase6_id='both-p6')
    conv_id = conv.id

    with patch('app.polis_http.post', side_effect=[
        _session_response('cookie-P2', 'csrf-P2'),
        _session_response('cookie-P6', 'csrf-P6'),
    ]) as post, patch('app.polis_http.get', side_effect=[
        _response({'7': {'id': 7, 'text': 'A statement'}}),
        _response({'votes': [], 'statements': []}),
    ]) as get, patch('app.polis_http.put', return_value=_response({})) as put:
        explore = auth_client.get('/api/v1/conversations/p6-both/explore')
        vote = _informed_vote(auth_client, 'p6-both', fs.id)

    assert explore.status_code == 200
    assert vote.status_code == 200
    assert post.call_count == 2, 'Phase 6 reused the Phase 2 Particiapi session'
    # Phase 2's reads went out on the Phase 2 cookie...
    assert {c.kwargs['cookies']['session'] for c in get.call_args_list} == {'cookie-P2'}
    # ...and the Phase 6 vote on its own.
    assert put.call_args.kwargs['cookies'] == {'session': 'cookie-P6'}
    with auth_client.session_transaction() as browser_session:
        assert browser_session['particiapi_api_sessions'][str(conv_id)]['cookie'] == (
            'cookie-P2')
        assert browser_session['phase6_api_sessions'][str(conv_id)]['cookie'] == (
            'cookie-P6')
