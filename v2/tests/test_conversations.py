"""Tests for the conversation listing, accept, and participation flows."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from db import (Conversation, ConversationInvite, Participant, Participation,
                db)

from tests.conftest import login


@pytest.fixture
def conv(app):
    c = Conversation(
        slug='test-conv', polis_id='abc1234567',
        title='Test Conversation', active=True, access_policy='public',
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def participation(app, participant, conv):
    p = Participation(
        participant_id=participant.id,
        conversation_id=conv.id,
        pseudonym='happy-fox',
    )
    db.session.add(p)
    db.session.commit()
    return p


# ── Index ─────────────────────────────────────────────────────────────────────

def test_index_shows_fork_between_demo_and_real(client):
    # The homepage is the explicit demo/real fork (#293).
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Try out the platform' in resp.data
    assert b'Participate in real consultations' in resp.data


def test_consultations_unauthenticated_shows_public_conversations(client, conv):
    resp = client.get('/consultations')
    assert resp.status_code == 200
    assert b'Test Conversation' in resp.data


def test_consultations_unauthenticated_hides_paused_conversations(client, app):
    c = Conversation(slug='paused', polis_id='xyz9876543', title='Paused Conv',
                     active=True, paused=True, access_policy='public')
    db.session.add(c)
    db.session.commit()
    resp = client.get('/consultations')
    assert b'Paused Conv' not in resp.data


def test_consultations_excludes_demo_conversations(client, app):
    # Real lane must not surface demo conversations (#293).
    c = Conversation(slug='demo-home', polis_id='demohome12', title='Demo Home',
                     active=True, access_policy='demo')
    db.session.add(c)
    db.session.commit()
    resp = client.get('/consultations')
    assert resp.status_code == 200
    assert b'Demo Home' not in resp.data


def test_demo_lane_shows_only_demo_conversations(client, conv):
    # /demo lists demo conversations and excludes real (public) ones (#293).
    c = Conversation(slug='demo-home', polis_id='demohome12', title='Demo Home',
                     active=True, access_policy='demo')
    db.session.add(c)
    db.session.commit()

    resp = client.get('/demo')

    assert resp.status_code == 200
    assert b'Demo Home' in resp.data
    assert b'Test Conversation' not in resp.data  # the public conv from `conv`


def test_index_authenticated_shows_joined_conversations(auth_client, participation, conv):
    resp = auth_client.get('/consultations')
    assert resp.status_code == 200
    assert b'Test Conversation' in resp.data


# ── Accept ────────────────────────────────────────────────────────────────────

def test_accept_get_renders_pseudonym_options(auth_client, conv):
    resp = auth_client.get('/accept/test-conv')
    assert resp.status_code == 200
    assert b'pseudonym' in resp.data.lower()


def test_accept_get_uses_concise_pseudonym_setup_copy(auth_client, conv):
    resp = auth_client.get('/accept/test-conv')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Choose a pseudonym' in html
    assert 'Pick the name you will use in this consultation.' in html
    assert 'Quick setup before you start' not in html
    assert 'Privacy &amp; data handling' in html
    assert 'id="accept-privacy-note"' in html


def test_accept_get_already_joined_redirects(auth_client, conv, participation):
    resp = auth_client.get('/accept/test-conv')
    assert resp.status_code == 302
    assert '/c/test-conv' in resp.headers['Location']


def test_accept_post_creates_participation(auth_client, conv, participant):
    resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'silly-goat'})
    assert resp.status_code == 302
    p = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id).first()
    assert p is not None
    assert p.pseudonym == 'silly-goat'


def test_accept_post_invalid_pseudonym_rejected(auth_client, conv):
    resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'bad name!'})
    assert resp.status_code == 400


def test_accept_post_pseudonym_too_short_rejected(auth_client, conv):
    resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'a-b'})
    assert resp.status_code == 400


def test_accept_post_duplicate_pseudonym_shows_error(auth_client, conv, app):
    """Attempting to claim a pseudonym already in use re-renders with an error."""
    other = Participant(mw_user_id=11111, mw_username='other',
                        xid='o' * 64)
    db.session.add(other)
    db.session.commit()
    taken = Participation(participant_id=other.id, conversation_id=conv.id,
                          pseudonym='taken-name')
    db.session.add(taken)
    db.session.commit()

    resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'taken-name'})
    assert resp.status_code == 200
    assert b'taken' in resp.data.lower()


def _eligibility_response(eligible, **extra):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {'eligible': eligible, **extra}
    return resp


def test_accept_post_eligibility_gate_allows_and_caches_verdict(auth_client, conv, participant, app):
    conv.eligibility_event_id = 'event-123'
    conv.eligibility_label = 'autoconfirmed on examplewiki'
    app.config['ACCOUNT_ELIGIBILITY_URL'] = 'https://account.example/check'
    db.session.commit()

    with patch('app.requests.get', return_value=_eligibility_response(True, event='event-123')) as req:
        resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'silly-goat'})

    assert resp.status_code == 302
    req.assert_called_once()
    assert req.call_args.kwargs['params'] == {
        'user': participant.mw_username,
        'event': 'event-123',
        'format': 'json',
    }
    p = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id).first()
    assert p is not None
    assert p.eligibility_status == 'eligible'
    assert p.eligibility_checked_at is not None
    assert p.eligibility_detail == {'event': 'event-123'}


def test_accept_post_eligibility_gate_blocks_ineligible(auth_client, conv, participant, app):
    conv.eligibility_event_id = 'event-123'
    conv.eligibility_label = 'extended-confirmed'
    app.config['ACCOUNT_ELIGIBILITY_URL'] = 'https://account.example/check'
    db.session.commit()

    with patch('app.requests.get', return_value=_eligibility_response(
            False, reason='Needs 500 edits.')):
        resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'silly-goat'})

    assert resp.status_code == 403
    assert b'extended-confirmed' in resp.data
    assert b'Needs 500 edits.' in resp.data
    assert Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id).first() is None


def test_accept_post_eligibility_gate_fails_closed_without_endpoint(auth_client, conv, participant):
    conv.eligibility_event_id = 'event-123'
    db.session.commit()

    resp = auth_client.post('/accept/test-conv', data={'pseudonym': 'silly-goat'})

    assert resp.status_code == 403
    assert b'eligibility checker is not configured' in resp.data
    assert Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id).first() is None


def test_accept_pseudonyms_endpoint_returns_list(auth_client, conv):
    resp = auth_client.get('/accept/test-conv/pseudonyms')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'pseudonyms' in data
    assert len(data['pseudonyms']) == 5
    for name in data['pseudonyms']:
        assert '-' in name


@pytest.mark.parametrize(('path', 'heading'), [
    ('/help/statements', b'Writing good statements'),
    ('/help/arguments', b'Writing good arguments'),
])
def test_guidance_pages_are_public(client, path, heading):
    resp = client.get(path)
    assert resp.status_code == 200
    assert heading in resp.data


# ── Conversation page ─────────────────────────────────────────────────────────

def test_conversation_without_participation_redirects_to_accept(auth_client, conv):
    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 302
    assert '/accept/test-conv' in resp.headers['Location']


def test_conversation_with_participation_renders(auth_client, conv, participation):
    """With a valid participation, the conversation page renders (no redirect)."""
    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    # No phases enabled → shows the "nothing available" placeholder.
    assert b'Nothing is available yet' in resp.data


def test_demo_conversation_creates_scoped_synthetic_participation(client, app):
    demo = Conversation(slug='demo', polis_id='demopolis1', title='Demo',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(demo)
    db.session.commit()

    resp = client.get('/c/demo')

    assert resp.status_code == 200
    assert b'noindex,nofollow' in resp.data
    assert b'nothing here is recorded' in resp.data
    part = Participation.query.filter_by(conversation_id=demo.id).one()
    assert part.participant.is_demo is True
    assert part.participant.mw_username.startswith('Demo-guest-')
    with client.session_transaction() as sess:
        assert sess['demo_conversation_id'] == demo.id
        assert 'username' not in sess


def test_demo_lane_applies_demo_theme_and_switch(client, app):
    # The demo lane marks the page as demo (blue theme) and offers the switch (#293).
    c = Conversation(slug='demo-theme', polis_id='demotheme1', title='Demo Theme',
                     active=True, access_policy='demo')
    db.session.add(c)
    db.session.commit()
    html = client.get('/demo').data.decode()
    assert 'data-demo="true"' in html
    assert 'class="mode-switch"' in html


def test_consultations_real_lane_has_switch_not_demo_theme(client, conv):
    html = client.get('/consultations').data.decode()
    assert 'class="mode-switch"' in html
    assert 'data-demo="true"' not in html


def test_real_conversation_shows_first_vote_confirm(auth_client, conv, participation):
    # A live (non-demo) conversation carries the one-time first-vote confirm;
    # a demo one never does (#293).
    conv.phase_submission = True
    db.session.commit()
    html = auth_client.get('/c/test-conv').data.decode()
    assert 'id="live-vote-confirm"' in html
    assert 'your vote will be recorded' in html
    assert 'data-demo="true"' not in html


def test_demo_conversation_has_no_first_vote_confirm(client, app):
    demo = Conversation(slug='demo-noconf', polis_id='demoncf001', title='Demo NoConf',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(demo)
    db.session.commit()
    html = client.get('/c/demo-noconf').data.decode()
    assert 'id="live-vote-confirm"' not in html
    assert 'data-demo="true"' in html


def test_demo_session_cannot_enter_other_conversation(client, app):
    demo = Conversation(slug='demo2', polis_id='demopolis2', title='Demo',
                        active=True, access_policy='demo')
    public = Conversation(slug='public-after-demo', polis_id='pubdemo123',
                          title='Public', active=True, access_policy='public')
    db.session.add_all([demo, public])
    db.session.commit()
    client.get('/c/demo2')

    resp = client.get('/c/public-after-demo')

    assert resp.status_code == 403


def test_demo_conversation_blocks_statement_submission(client, app):
    demo = Conversation(slug='demo3', polis_id='demopolis3', title='Demo',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(demo)
    db.session.commit()
    client.get('/c/demo3')

    with patch('app.requests.post') as post:
        resp = client.post('/c/demo3/statements/new',
                           headers={'Sec-Fetch-Site': 'same-origin'},
                           json={'text': 'anonymous write'})

    assert resp.status_code == 302
    post.assert_not_called()


def test_personal_results_renders_clustering_data(auth_client, conv, participation,
                                                  monkeypatch):
    """#81: with ONLY the Personal results toggle on, the Results tab must render the
    clustering results — not fall through to the 'not published yet' message. Regression
    guard for the bug where both the route fetch and the template render were gated on
    phase_public_results only."""
    import polis_admin
    conv.phase_personal_results = True
    conv.phase_public_results = False
    db.session.commit()

    fake_results = {
        'majority': {
            'agree': [{'statement_text': 'Cats make excellent companions', 'value': 0.82}],
            'disagree': [],
        },
        'groups': [],
    }
    monkeypatch.setattr(polis_admin.PolisParticipantClient, 'get_results',
                        lambda self, cid: fake_results)
    monkeypatch.setattr(polis_admin.PolisServerClient, 'get_polis_stats',
                        lambda self, cid: None)

    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    assert b'Cats make excellent companions' in resp.data           # results rendered
    assert b"Results haven't been published yet" not in resp.data   # not the empty fallback


def test_empty_polis_results_shows_not_enough_votes(auth_client, conv, participation,
                                                    monkeypatch):
    """Particiapi returns all-empty arrays when there aren't enough votes for clustering.
    The Results tab must show the 'not enough votes' message rather than a blank panel."""
    import polis_admin
    import app as app_module
    conv.phase_public_results = True
    db.session.commit()

    monkeypatch.setattr(polis_admin.PolisParticipantClient, 'get_results',
                        lambda self, cid: {'groups': [], 'majority': {'agree': [], 'disagree': []}})
    monkeypatch.setattr(polis_admin.PolisServerClient, 'get_polis_stats',
                        lambda self, cid: None)
    monkeypatch.setattr(polis_admin.PolisServerClient, 'queue_math_recompute',
                        lambda self, zinvite: False)
    # Simulate a recent trigger so rate-limit suppresses recompute → shows "enough votes".
    import time
    monkeypatch.setitem(app_module._math_recompute_last, conv.id, time.monotonic())

    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    assert b'enough votes' in resp.data
    assert b"Results haven't been published yet" not in resp.data


def test_none_polis_results_shows_not_enough_votes(auth_client, conv, participation,
                                                   monkeypatch):
    """When Particiapi errors or returns None (e.g. math hasn't run), the Results tab
    must show the 'not enough votes' message rather than a blank panel."""
    import polis_admin
    import app as app_module
    conv.phase_public_results = True
    db.session.commit()

    monkeypatch.setattr(polis_admin.PolisParticipantClient, 'get_results',
                        lambda self, cid: None)
    monkeypatch.setattr(polis_admin.PolisServerClient, 'get_polis_stats',
                        lambda self, cid: None)
    monkeypatch.setattr(polis_admin.PolisServerClient, 'queue_math_recompute',
                        lambda self, zinvite: False)
    import time
    monkeypatch.setitem(app_module._math_recompute_last, conv.id, time.monotonic())

    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    assert b'enough votes' in resp.data
    assert b"Results haven't been published yet" not in resp.data


def test_empty_results_triggers_recompute_and_shows_computing_message(
        auth_client, conv, participation, monkeypatch):
    """When results are empty and POLIS_DATABASE_URL is set, queue_math_recompute is
    called and the template shows 'being computed' instead of 'not enough votes'."""
    import polis_admin
    import app as app_module
    conv.phase_public_results = True
    db.session.commit()

    monkeypatch.setattr(polis_admin.PolisParticipantClient, 'get_results',
                        lambda self, cid: {'groups': [], 'majority': {'agree': [], 'disagree': []}})
    monkeypatch.setattr(polis_admin.PolisServerClient, 'get_polis_stats',
                        lambda self, cid: None)
    recompute_called = []
    monkeypatch.setattr(polis_admin.PolisServerClient, 'queue_math_recompute',
                        lambda self, zinvite: recompute_called.append(zinvite) or True)
    # Reset rate-limit state so the trigger fires. The gate is
    # `time.monotonic() - _last > _MATH_RECOMPUTE_COOLDOWN`, so _last must be set
    # to the PAST relative to now — not 0. On a freshly-booted CI runner
    # monotonic() is near 0, so `now - 0` is < cooldown and the trigger wouldn't
    # fire (passed locally, where monotonic() is large, but failed in CI).
    import time
    monkeypatch.setitem(app_module._math_recompute_last, conv.id,
                        time.monotonic() - app_module._MATH_RECOMPUTE_COOLDOWN - 1)

    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    assert recompute_called == [conv.polis_id]
    assert b'being computed' in resp.data
    assert b'enough votes' not in resp.data


def test_recompute_rate_limited_within_cooldown(auth_client, conv, participation,
                                                monkeypatch):
    """queue_math_recompute is NOT called again within the cooldown window."""
    import time
    import polis_admin
    import app as app_module
    conv.phase_public_results = True
    db.session.commit()

    monkeypatch.setattr(polis_admin.PolisParticipantClient, 'get_results',
                        lambda self, cid: {'groups': [], 'majority': {'agree': [], 'disagree': []}})
    monkeypatch.setattr(polis_admin.PolisServerClient, 'get_polis_stats',
                        lambda self, cid: None)
    recompute_called = []
    monkeypatch.setattr(polis_admin.PolisServerClient, 'queue_math_recompute',
                        lambda self, zinvite: recompute_called.append(zinvite) or True)
    # Simulate a recent trigger (within cooldown).
    monkeypatch.setitem(app_module._math_recompute_last, conv.id, time.monotonic())

    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    assert recompute_called == []
    assert b'enough votes' in resp.data  # falls back to normal message


def test_report_route_uses_filter_snapshot(client, conv):
    from app import Phase6ResultsFilter
    conv.active = False
    conv.phase_public_results = True
    conv.closed_at = datetime.now(timezone.utc)
    conv.phase6_polis_conversation_id = 'p6conv1234'
    conv.report_filter_snapshot = {'excluded_tids': [42], 'excluded_pids': [7]}
    db.session.commit()
    seen = {}

    def fake_build(_conv, participation, results_filter=None):
        seen['filter'] = results_filter
        return None

    with patch('app._build_phase6_results', side_effect=fake_build):
        resp = client.get('/c/test-conv/report')

    assert resp.status_code == 200
    assert seen['filter'] == Phase6ResultsFilter(
        excluded_tids=frozenset({42}),
        excluded_pids=frozenset({7}),
    )


# ── Access control ────────────────────────────────────────────────────────────

def test_invite_only_blocks_uninvited(client, app, participant):
    login(client, 'testuser')
    c = Conversation(slug='private', polis_id='pri1234567', title='Private',
                     active=True, access_policy='invite_only')
    db.session.add(c)
    db.session.commit()
    resp = client.get('/accept/private')
    assert resp.status_code == 403


def test_invite_only_allows_invited(client, app, participant):
    login(client, 'testuser')
    c = Conversation(slug='private2', polis_id='pr21234567', title='Private2',
                     active=True, access_policy='invite_only')
    db.session.add(c)
    db.session.commit()
    inv = ConversationInvite(conversation_id=c.id, mw_username='testuser')
    db.session.add(inv)
    db.session.commit()
    resp = client.get('/accept/private2')
    assert resp.status_code == 200


def test_invite_only_allows_already_joined(client, app, participant):
    """A participant who already joined can visit even after invite is removed."""
    c = Conversation(slug='private3', polis_id='pr31234567', title='Private3',
                     active=True, access_policy='invite_only')
    db.session.add(c)
    db.session.commit()
    part = Participation(participant_id=participant.id,
                         conversation_id=c.id, pseudonym='quick-otter')
    db.session.add(part)
    db.session.commit()
    login(client, 'testuser')
    resp = client.get('/c/private3')
    assert resp.status_code == 200
