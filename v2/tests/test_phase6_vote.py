"""Phase 6 vote route: server-side Particiapi session/CSRF reuse across votes (A5)."""

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
    return r


def test_phase6_vote_reuses_session_across_votes(auth_client, participant):
    c, fs = _p6_conv()
    db.session.add(Participation(participant_id=participant.id, conversation_id=c.id,
                                 pseudonym='p6-lion'))
    db.session.commit()

    with patch.object(app_module.polis_http, 'post', return_value=_session_resp()) as post, \
         patch.object(app_module.polis_http, 'put', return_value=_put_resp()) as put:
        r1 = auth_client.post('/c/p6-conv/phase6/vote', json={'fs_id': fs.id, 'vote': -1})
        r2 = auth_client.post('/c/p6-conv/phase6/vote', json={'fs_id': fs.id, 'vote': 1})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert post.call_count == 1   # session bootstrap happens once, then is reused
    assert put.call_count == 2    # both votes forwarded


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
        ra = client_a.post('/c/p6-conv/phase6/vote', json={'fs_id': fs.id, 'vote': -1})
        rb = client_b.post('/c/p6-conv/phase6/vote', json={'fs_id': fs.id, 'vote': 1})

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
        r = auth_client.post('/c/p6-conv/phase6/vote', json={'fs_id': fs.id, 'vote': -1})

    assert r.status_code == 200
    assert post.call_count == 1   # the stale reused token 403s -> exactly one re-bootstrap
    assert put.call_count == 2    # first PUT 403, retry PUT 200


def test_both_phase6_surfaces_send_the_polis_agree_sign():
    """Guard the sign at BOTH phase-6 write sites.

    Polis stores -1 = agree (polis_admin.py:211, guide_runbook.md). The API route
    maps `choice` server-side; the legacy Jinja route forwards the client's raw
    data-vote attribute unchanged (app.py:6591), so for that surface the template
    IS the contract. A divergence writes both signs into one votes table depending
    only on whether the participant is on the SPA or ?spa_only=0 — worse than the
    original bug, because the rows become indistinguishable. Nothing else in the
    suite covers the legacy attribute.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent

    template = (root / 'templates' / 'conversation.html').read_text()
    # Only the phase-6 deck uses btn-p6-vote; phase 2 has its own vote controls.
    buttons = re.findall(
        r'btn-p6-vote"\s+data-vote="(-?\d)"\s*>\s*'
        r'<span class="vote-dot vote-dot--(\w+)"></span>(\w+)',
        template,
    )
    assert len(buttons) == 3, f'expected 3 phase-6 vote buttons, found {len(buttons)}'
    mapping = {label: int(value) for value, _dot, label in buttons}
    assert mapping == {'Agree': -1, 'Pass': 0, 'Disagree': 1}, mapping

    app_src = (root / 'app.py').read_text()
    assert app_src.count("polis_values = {'agree': -1, 'pass': 0, 'disagree': 1}") == 2, \
        'both the Explore and informed-vote API paths must map agree to -1'
