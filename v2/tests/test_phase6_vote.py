"""Phase 6 (informed voting) vote submission and readback.

Covers the three defects fixed together:
  - identity binding: a Phase 6 vote asserts the participant's stable per-conversation
    subject (X-Particiapi-Sub) so it lands under their real Polis uid, not a throwaway;
  - Polis-native sign: the app's button convention (1=agree) is converted to Polis's
    (-1=agree) on write, so informed-vote counts match Phase 2;
  - readback: prior votes are restored from Polis (resolved via particiapi_users) so a
    reload shows the participant's choices.
"""
import hashlib
import hmac
import re
from unittest.mock import MagicMock, patch

import pytest

from db import Conversation, FeaturedStatement, Participation, db
from polis_admin import PolisServerClient

_SECRET = 'sub-secret-test'


def _fake_resp(status_code=200, cookies=None, csrf='TOK', ok=True):
    m = MagicMock()
    m.status_code = status_code
    m.ok = ok
    m.cookies = cookies or {}
    m.json = lambda: {'csrf_token': csrf}
    return m


def _setup_phase6(participant, *, p6_conv='p6conv0001', p6_tid=7):
    conv = Conversation(slug='p6', polis_id='p6main0001', title='P6', active=True,
                        access_policy='public', phase_informed_voting=True,
                        phase6_polis_conversation_id=p6_conv)
    db.session.add(conv)
    db.session.commit()
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=5,
                           confirmed_by_admin=True, statement_text='A statement',
                           phase6_polis_statement_id=p6_tid)
    db.session.add(fs)
    db.session.add(Participation(participant_id=participant.id,
                                 conversation_id=conv.id, pseudonym='p'))
    db.session.commit()
    return conv, fs


def _expected_subject(xid, conv_id):
    """Re-derive the conversation-scoped subject independently, so a change to the
    keying scheme in app.py breaks this test rather than silently passing."""
    return hmac.new(_SECRET.encode(), f'{xid}:{conv_id}'.encode(),
                    hashlib.sha256).hexdigest()


# ── Bug B: identity binding ─────────────────────────────────────────────────────

def test_phase6_vote_binds_participant_identity(app, auth_client, participant):
    app.config['PARTICIAPI_SUB_SECRET'] = _SECRET
    conv, fs = _setup_phase6(participant)
    with patch('app.requests.post', return_value=_fake_resp(cookies={'session': 'PA'})) as post, \
         patch('app.requests.put', return_value=_fake_resp()):
        resp = auth_client.post('/c/p6/phase6/vote', json={'fs_id': fs.id, 'vote': 1})
    assert resp.status_code == 200
    headers = post.call_args.kwargs['headers']
    assert headers['X-Particiapi-Sub'] == _expected_subject(participant.xid, conv.id)
    assert headers['X-Particiapi-Sub-Secret'] == _SECRET
    # the asserted subject must never be the bare xid, and a bind must not forward a
    # stale session cookie (which would make Particiapi skip the bind).
    assert headers['X-Particiapi-Sub'] != participant.xid
    assert post.call_args.kwargs['cookies'] == {}


def test_phase6_vote_no_secret_does_not_bind(app, auth_client, participant):
    app.config['PARTICIAPI_SUB_SECRET'] = ''
    conv, fs = _setup_phase6(participant)
    with patch('app.requests.post', return_value=_fake_resp(cookies={'session': 'PA'})) as post, \
         patch('app.requests.put', return_value=_fake_resp()):
        resp = auth_client.post('/c/p6/phase6/vote', json={'fs_id': fs.id, 'vote': 1})
    assert resp.status_code == 200
    assert 'X-Particiapi-Sub' not in post.call_args.kwargs.get('headers', {})
    assert post.call_args.kwargs['params'] == {'create': 'true'}


# ── Bug C: Polis-native sign on write ───────────────────────────────────────────

@pytest.mark.parametrize('button_vote,polis_value', [(1, -1), (-1, 1), (0, 0)])
def test_phase6_vote_converts_to_polis_sign(app, auth_client, participant,
                                            button_vote, polis_value):
    """Agree(1) -> -1, Disagree(-1) -> +1, Pass(0) -> 0 (Polis convention, matching
    Phase 2 so the informed-vote counts are not inverted)."""
    app.config['PARTICIAPI_SUB_SECRET'] = _SECRET
    conv, fs = _setup_phase6(participant)
    with patch('app.requests.post', return_value=_fake_resp(cookies={'session': 'PA'})), \
         patch('app.requests.put', return_value=_fake_resp()) as put:
        resp = auth_client.post('/c/p6/phase6/vote',
                                json={'fs_id': fs.id, 'vote': button_vote})
    assert resp.status_code == 200
    assert put.call_args.kwargs['json'] == {'value': polis_value}


# ── Bug A: readback ─────────────────────────────────────────────────────────────

def test_get_personal_votes_by_subject_resolves_via_particiapi_users():
    client = PolisServerClient('http://x', 'e', 'p', db_url='postgresql://x')
    with patch.object(client, '_pg_query', return_value=[(7, -1), (9, 0)]) as q:
        out = client.get_personal_votes_by_subject('p6conv0001', 'subj123')
    assert out == {7: -1, 9: 0}
    # resolved by (zinvite, issuer, subject) against the trusted-sub identity map
    assert q.call_args.args[1] == ('p6conv0001', 'wiki-polis', 'subj123')


def test_phase6_card_renders_restored_vote(app, auth_client, participant):
    """A prior Agree vote (Polis -1 on the card's tid) renders the card as voted with
    the Agree option selected — so a reload shows the participant's earlier choice."""
    app.config['PARTICIAPI_SUB_SECRET'] = _SECRET
    conv, fs = _setup_phase6(participant, p6_tid=7)
    server = MagicMock()
    server.get_personal_votes_by_subject.return_value = {7: -1}  # tid 7 -> agree
    with patch('app._polis_server_client', return_value=server), \
         patch('app._build_phase6_results', return_value=None):
        html = auth_client.get('/c/p6').get_data(as_text=True)
    # Assert on server-rendered markup, not substrings that also occur in the page JS:
    # the card div carries p6-card--voted, and the badge modifier class p6-voted-badge--agree
    # (built dynamically in JS, so its literal only appears in server-rendered voted state).
    assert re.search(r'class="p6-card[^"]*p6-card--voted', html)
    assert 'p6-voted-badge--agree' in html
    # resolver was queried for the phase6 conversation
    server.get_personal_votes_by_subject.assert_called_once()
    assert server.get_personal_votes_by_subject.call_args.args[0] == 'p6conv0001'


def test_phase6_card_unvoted_when_no_prior_vote(app, auth_client, participant):
    app.config['PARTICIAPI_SUB_SECRET'] = _SECRET
    conv, fs = _setup_phase6(participant, p6_tid=7)
    server = MagicMock()
    server.get_personal_votes_by_subject.return_value = {}
    with patch('app._polis_server_client', return_value=server), \
         patch('app._build_phase6_results', return_value=None):
        html = auth_client.get('/c/p6').get_data(as_text=True)
    assert not re.search(r'class="p6-card[^"]*p6-card--voted', html)
    assert 'p6-voted-badge--agree' not in html
