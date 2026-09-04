"""Phase 6 vote: server-side Particiapi session/CSRF reuse across votes (A5).

Ported from the deleted /c/<slug>/phase6/vote Jinja route onto
PUT /api/v1/conversations/<slug>/featured-statements/<id>/informed-vote, which
shares the same `_phase6_gateway` and `_p6_session_cache` underneath. What is
covered here is the session *management* around that gateway -- bootstrap reuse,
cross-session sharing and stale-token recovery -- which nothing in
test_informed_voting_api.py asserts.

Two tests from the Jinja version are gone rather than ported, because the
surface they guarded no longer exists and the surviving half is already covered:

  * test_both_phase6_surfaces_send_the_polis_agree_sign parsed
    templates/conversation.html to pin the data-vote integers and the badge
    label map, guarding the sign at the *second* phase-6 write site. That site
    is gone; only the API route writes phase-6 votes now, and its mapping is
    asserted per choice -- agree -1, pass 0, disagree +1 -- by
    test_informed_voting_api.py::test_informed_vote_sends_polis_signs_for_every_choice.
    The deleted test said so itself in its closing comment.

  * test_phase6_binds_the_same_identity_explore_uses is duplicated exactly, down
    to the independent re-derivation of the HMAC subject, by
    test_informed_voting_api.py::test_informed_vote_api_binds_the_same_identity_explore_uses.
"""

from unittest.mock import MagicMock, patch

import app as app_module
from db import Conversation, FeaturedStatement, Participation, db
from tests.conftest import login


def _p6_conv():
    c = Conversation(
        slug='p6-conv', polis_id='p2conv1234',
        title='P6', active=True, access_policy='public',
        phase_informed_voting=True, phase6_polis_conversation_id='p6conv1234',
    )
    db.session.add(c)
    db.session.flush()
    fs = FeaturedStatement(
        conversation_id=c.id, polis_statement_id=10,
        statement_text='S', confirmed_by_admin=True, phase6_polis_statement_id=55,
    )
    db.session.add(fs)
    db.session.commit()
    return c, fs


def _vote_url(fs_id):
    return f'/api/v1/conversations/p6-conv/featured-statements/{fs_id}/informed-vote'


def _session_resp(csrf='TOK', cookie='PA1'):
    r = MagicMock()
    r.ok = True
    r.json.return_value = {'csrf_token': csrf}
    r.cookies.get.return_value = cookie
    return r


def _put_resp(status=200):
    r = MagicMock()
    r.ok = status < 400
    r.status_code = status
    r.json.return_value = {}
    return r


def test_phase6_vote_reuses_session_across_votes(auth_client, participant):
    c, fs = _p6_conv()
    db.session.add(Participation(participant_id=participant.id, conversation_id=c.id,
                                 pseudonym='p6-lion'))
    db.session.commit()

    with patch.object(app_module.polis_http, 'post', return_value=_session_resp()) as post, \
         patch.object(app_module.polis_http, 'put', return_value=_put_resp()) as put:
        r1 = auth_client.put(_vote_url(fs.id), json={'choice': 'agree'})
        r2 = auth_client.put(_vote_url(fs.id), json={'choice': 'disagree'})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert post.call_count == 1   # session bootstrap happens once, then is reused
    assert put.call_count == 2    # both votes forwarded
    # Polis stores -1 = agree, +1 = disagree. Asserted per choice in
    # test_informed_voting_api.py; repeated across a reused session here so a
    # bootstrap change cannot quietly alter what the second vote writes.
    assert [c.kwargs['json'] for c in put.call_args_list] == [{'value': -1}, {'value': 1}]


def test_phase6_bootstrap_shared_across_sessions_same_participant(app, participant):
    # #275 M1: two concurrent first-time Phase-6 votes from the SAME participant
    # (separate Flask sessions — e.g. two tabs) must reuse ONE Polis session, not
    # mint two uids that COUNT(DISTINCT pid) would double-count. The process-local
    # share cache makes the second session reuse the first's bootstrap.
    c, fs = _p6_conv()
    db.session.add(Participation(participant_id=participant.id, conversation_id=c.id,
                                 pseudonym='p6-bear'))
    db.session.commit()

    client_a = app.test_client()
    client_b = app.test_client()
    login(client_a, 'testuser')
    login(client_b, 'testuser')   # same participant/xid, independent sessions

    with patch.object(app_module.polis_http, 'post', return_value=_session_resp()) as post, \
         patch.object(app_module.polis_http, 'put', return_value=_put_resp()) as put:
        ra = client_a.put(_vote_url(fs.id), json={'choice': 'agree'})
        rb = client_b.put(_vote_url(fs.id), json={'choice': 'disagree'})

    assert ra.status_code == 200
    assert rb.status_code == 200
    assert post.call_count == 1   # ONE bootstrap shared across both sessions
    assert put.call_count == 2


def test_phase6_vote_rebootstraps_on_stale_token(auth_client, participant):
    c, fs = _p6_conv()
    db.session.add(Participation(participant_id=participant.id, conversation_id=c.id,
                                 pseudonym='p6-fox'))
    db.session.commit()
    # Prime the session with a stored (now-stale) Phase 6 session + token.
    with auth_client.session_transaction() as sess:
        sess['_p6_pa'] = 'OLD'
        sess['_p6_csrf'] = 'STALE'

    with patch.object(app_module.polis_http, 'post',
                      return_value=_session_resp('FRESH', 'NEW')) as post, \
         patch.object(app_module.polis_http, 'put',
                      side_effect=[_put_resp(403), _put_resp(200)]) as put:
        r = auth_client.put(_vote_url(fs.id), json={'choice': 'agree'})

    assert r.status_code == 200
    assert post.call_count == 1   # the stale reused token 403s -> exactly one re-bootstrap
    assert put.call_count == 2    # first PUT 403, retry PUT 200
