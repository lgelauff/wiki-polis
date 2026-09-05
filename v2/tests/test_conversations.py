"""Conversation lane, join, workspace and results flows over /api/v1.

Ported from the deleted Jinja routes. The behaviour these tests guard — lane
membership and demo/real space separation, invite-only admission, the synthetic
demo-guest lifecycle, the arrival space warning, results publication — is now
observable only through the JSON API, so every request goes to /api/v1 and every
assertion reads the payload or the database rather than rendered markup.
"""
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lane(client, space='real'):
    resp = client.get(f'/api/v1/conversations?space={space}')
    assert resp.status_code == 200
    return resp.get_json()['data']


def _lane_titles(data):
    return {card['title'] for group in data['groups'].values() for card in group}


def _lane_slugs(data, group):
    return [card['slug'] for card in data['groups'][group]]


def _workspace(client, slug):
    return client.get(f'/api/v1/conversations/{slug}/workspace')


def _entry(client, slug):
    return client.get(f'/api/v1/conversations/{slug}/participation-entry')


# ── Lanes ─────────────────────────────────────────────────────────────────────

def test_index_shows_fork_between_demo_and_real(client, conv):
    # The homepage demo/real fork (#293) is, server-side, the two-space lane API:
    # exactly `real` and `demo` are addressable and anything else is rejected.
    # (The fork's copy and the mode-switch markup are the SPA's half.)
    assert _lane(client, 'real')['space'] == 'real'
    assert _lane(client, 'demo')['space'] == 'demo'

    invalid = client.get('/api/v1/conversations?space=both')

    assert invalid.status_code == 400
    error = invalid.get_json()['error']
    assert error['code'] == 'validation_failed'
    assert 'space' in error['details']['fields']


def test_spa_history_routes_serve_the_same_built_shell(client, monkeypatch, tmp_path):
    import app as app_module

    shell = tmp_path / 'index.html'
    shell.write_text('<div id="root">SPA shell</div>', encoding='utf-8')
    monkeypatch.setattr(app_module, '_SPA_BUILD_DIR', str(tmp_path))

    root_response = client.get('/app')
    nested_response = client.get('/app/demo/conversations')

    assert root_response.status_code == 200
    assert nested_response.status_code == 200
    assert root_response.data == nested_response.data
    assert b'id="root"' in root_response.data


def test_consultations_unauthenticated_shows_public_conversations(client, conv):
    data = _lane(client)

    assert data['authenticated'] is False
    assert _lane_slugs(data, 'available') == ['test-conv']
    assert data['groups']['available'][0]['title'] == 'Test Conversation'


def test_consultations_unauthenticated_hides_paused_conversations(client, conv):
    c = Conversation(slug='paused', polis_id='xyz9876543', title='Paused Conv',
                     active=True, paused=True, access_policy='public')
    db.session.add(c)
    db.session.commit()

    data = _lane(client)

    # The unpaused conversation is the control: the lane really was built.
    assert 'Test Conversation' in _lane_titles(data)
    assert 'Paused Conv' not in _lane_titles(data)


def test_consultations_excludes_demo_conversations(client, conv):
    # Real lane must not surface demo conversations (#293).
    c = Conversation(slug='demo-home', polis_id='demohome12', title='Demo Home',
                     active=True, access_policy='demo')
    db.session.add(c)
    db.session.commit()

    real = _lane(client, 'real')

    assert 'Test Conversation' in _lane_titles(real)
    assert 'Demo Home' not in _lane_titles(real)
    # Control: the row exists and is visible — but only in the demo space.
    assert 'Demo Home' in _lane_titles(_lane(client, 'demo'))


def test_demo_lane_shows_only_demo_conversations(client, conv):
    # The demo space lists demo conversations and excludes real (public) ones (#293).
    c = Conversation(slug='demo-home', polis_id='demohome12', title='Demo Home',
                     active=True, access_policy='demo')
    db.session.add(c)
    db.session.commit()

    data = _lane(client, 'demo')

    assert data['space'] == 'demo'
    assert _lane_slugs(data, 'available') == ['demo-home']
    assert 'Test Conversation' not in _lane_titles(data)


def test_index_authenticated_shows_joined_conversations(auth_client, participation, conv):
    data = _lane(auth_client)

    assert data['authenticated'] is True
    # No phase is enabled on the fixture conversation, so it buckets as inactive.
    assert _lane_slugs(data, 'inactive') == ['test-conv']
    card = data['groups']['inactive'][0]
    assert card['relationship'] == 'joined'
    assert card['pseudonym'] == 'happy-fox'


def test_consultations_excludes_demo_from_logged_in_joined_list(auth_client, participant, participation, conv):
    # Defense-in-depth: even a (contrived) demo participation tied to the real
    # participant must not surface in the real lane (#293).
    demo = Conversation(slug='demo-joined', polis_id='demojoin001', title='Demo Joined',
                        active=True, access_policy='demo')
    db.session.add(demo)
    db.session.commit()
    db.session.add(Participation(participant_id=participant.id, conversation_id=demo.id,
                                 pseudonym='demo-mole'))
    db.session.commit()

    real = _lane(auth_client, 'real')

    assert 'Test Conversation' in _lane_titles(real)   # the real joined conv still shows
    assert 'Demo Joined' not in _lane_titles(real)     # the demo one never does
    # Control: the demo participation is real and does show in the demo space.
    assert 'Demo Joined' in _lane_titles(_lane(auth_client, 'demo'))


def test_consultations_moderating_excludes_demo_for_admin(admin_client, app):
    # #293: the real lane's "You moderate" must not list demo conversations, even
    # for a global admin (who moderates everything).
    demo = Conversation(slug='demo-mod', polis_id='demomod001', title='Demo Mod',
                        active=True, access_policy='demo')
    real = Conversation(slug='real-mod', polis_id='realmod001', title='Real Mod',
                        active=True, access_policy='public')
    db.session.add_all([demo, real])
    db.session.commit()

    data = _lane(admin_client, 'real')

    assert _lane_slugs(data, 'moderating') == ['real-mod']
    assert 'Demo Mod' not in _lane_titles(data)
    # Control: the admin does moderate the demo one — in the demo space.
    assert _lane_slugs(_lane(admin_client, 'demo'), 'moderating') == ['demo-mod']


# DELETED (Jinja markup only): test_demo_lane_applies_demo_theme_and_switch and
# test_consultations_real_lane_has_switch_not_demo_theme asserted the
# `data-demo="true"` theme attribute and the `mode-switch` element. Their only
# server-side half is the lane payload's `space` discriminator, which
# test_index_shows_fork_between_demo_and_real asserts for both spaces.


# ── Joining (participation entry + join command) ──────────────────────────────

def test_accept_get_renders_pseudonym_options(auth_client, conv):
    resp = _entry(auth_client, 'test-conv')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['state'] == 'join'
    assert len(data['pseudonyms']) == 5
    for name in data['pseudonyms']:
        assert '-' in name


# DELETED (Jinja markup only): test_accept_get_uses_concise_pseudonym_setup_copy
# asserted heading/copy strings and the id="accept-privacy-note" element. The
# participation-entry payload carries no copy — only state, conversation,
# pseudonyms, emailable, reveal windows and links — so there is no server-side
# counterpart to port. The privacy note's data half (reveal cooldown/window days)
# is asserted in tests/test_participation_api.py.


def test_accept_get_already_joined_redirects(auth_client, conv, participation):
    resp = _entry(auth_client, 'test-conv')

    assert resp.status_code == 200
    assert resp.get_json()['data'] == {
        'state': 'redirect',
        'reason': 'already_participating',
        'href': '/c/test-conv',
    }


def test_accept_post_creates_participation(auth_client, conv, participant):
    resp = auth_client.post('/api/v1/conversations/test-conv/participation',
                            json={'pseudonym': 'silly-goat'})

    assert resp.status_code == 201
    p = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id).first()
    assert p is not None
    assert p.pseudonym == 'silly-goat'


def test_accept_post_invalid_pseudonym_rejected(auth_client, conv, participant):
    resp = auth_client.post('/api/v1/conversations/test-conv/participation',
                            json={'pseudonym': 'bad name!'})

    assert resp.status_code == 400
    error = resp.get_json()['error']
    assert error['code'] == 'validation_failed'
    assert 'pseudonym' in error['details']['fields']
    assert Participation.query.count() == 0


def test_accept_post_pseudonym_too_short_rejected(auth_client, conv, participant):
    resp = auth_client.post('/api/v1/conversations/test-conv/participation',
                            json={'pseudonym': 'a-b'})

    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'validation_failed'
    assert Participation.query.count() == 0


def test_accept_post_duplicate_pseudonym_shows_error(auth_client, conv, participant, app):
    """Attempting to claim a pseudonym already in use is a typed conflict."""
    other = Participant(mw_user_id=11111, mw_username='other',
                        xid='o' * 64)
    db.session.add(other)
    db.session.commit()
    taken = Participation(participant_id=other.id, conversation_id=conv.id,
                          pseudonym='taken-name')
    db.session.add(taken)
    db.session.commit()

    resp = auth_client.post('/api/v1/conversations/test-conv/participation',
                            json={'pseudonym': 'taken-name'})

    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'pseudonym_unavailable'
    assert Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id).first() is None


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
        resp = auth_client.post('/api/v1/conversations/test-conv/participation',
                                json={'pseudonym': 'silly-goat'})

    assert resp.status_code == 201
    assert resp.get_json()['data']['eligibilityStatus'] == 'eligible'
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

    # The requirement label the denial page showed is served by the join screen's
    # own payload; the denial itself carries the upstream reason.
    assert _entry(auth_client, 'test-conv').get_json()[
        'data']['conversation']['eligibilityLabel'] == 'extended-confirmed'

    with patch('app.requests.get', return_value=_eligibility_response(
            False, reason='Needs 500 edits.')):
        resp = auth_client.post('/api/v1/conversations/test-conv/participation',
                                json={'pseudonym': 'silly-goat'})

    assert resp.status_code == 403
    error = resp.get_json()['error']
    assert error['code'] == 'eligibility_denied'
    assert error['details'] == {
        'status': 'ineligible',
        'displayMessage': 'Needs 500 edits.',
    }
    assert Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id).first() is None


def test_accept_post_eligibility_gate_fails_closed_without_endpoint(auth_client, conv, participant):
    conv.eligibility_event_id = 'event-123'
    db.session.commit()

    resp = auth_client.post('/api/v1/conversations/test-conv/participation',
                            json={'pseudonym': 'silly-goat'})

    assert resp.status_code == 403
    error = resp.get_json()['error']
    assert error['code'] == 'eligibility_unavailable'
    assert error['details']['status'] == 'unavailable'
    assert error['details']['displayMessage'] == 'eligibility checker is not configured'
    assert Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id).first() is None


def test_accept_pseudonyms_endpoint_returns_list(auth_client, conv):
    resp = auth_client.get('/api/v1/conversations/test-conv/pseudonym-suggestions')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert 'pseudonyms' in data
    assert len(data['pseudonyms']) == 5
    for name in data['pseudonyms']:
        assert '-' in name


# DELETED (Jinja markup only): test_guidance_pages_are_public asserted the
# rendered headings of /help/statements and /help/arguments. That copy now lives
# in the React StatementGuidancePage/ArgumentGuidancePage; there is no API
# endpoint serving guidance text, and the routes' public availability is asserted
# by tests/test_spa_canonical_routes.py.


# ── Conversation workspace ────────────────────────────────────────────────────

def test_conversation_without_participation_redirects_to_accept(auth_client, conv):
    resp = _workspace(auth_client, 'test-conv')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['viewer'] == {'state': 'join_required', 'pseudonym': None}
    assert data['links']['join'] == '/accept/test-conv'
    assert data['capabilities']['participate'] is False


def test_conversation_with_participation_renders(auth_client, conv, participation):
    """With a valid participation the workspace is served (no join_required)."""
    resp = _workspace(auth_client, 'test-conv')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['viewer'] == {'state': 'participant', 'pseudonym': 'happy-fox'}
    # No phases enabled → nothing is available yet.
    assert data['tabs'] == []
    assert data['defaultTab'] is None


def test_demo_conversation_creates_scoped_synthetic_participation(client, app):
    demo = Conversation(slug='demo', polis_id='demopolis1', title='Demo',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(demo)
    db.session.commit()

    resp = _workspace(client, 'demo')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    # `space: demo` is the server-side flag the client turns into the demo theme,
    # the noindex meta and the "demonstration conversation" notice.
    assert data['space'] == 'demo'
    assert data['viewer']['state'] == 'participant'
    part = Participation.query.filter_by(conversation_id=demo.id).one()
    assert part.participant.is_demo is True
    assert part.participant.mw_username.startswith('Demo-guest-')
    with client.session_transaction() as sess:
        assert sess['demo_conversation_id'] == demo.id
        assert 'username' not in sess


def test_no_first_vote_confirm_on_real_conversation(auth_client, conv, participation):
    # #293: the on-vote first-vote confirm was removed in favour of the single
    # arrival banner. Server-side that banner is `spaceWarning`: raised once on
    # arrival and cleared for every later request, so nothing re-warns per vote.
    conv.phase_submission = True
    db.session.commit()

    first = _workspace(auth_client, 'test-conv')
    second = _workspace(auth_client, 'test-conv')

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json()['data']['spaceWarning'] == 'real'
    assert second.get_json()['data']['spaceWarning'] is None
    assert second.get_json()['data']['capabilities']['participate'] is True


def test_conversation_shows_scheduled_transition_target_and_localizable_time(
    auth_client, conv, participation,
):
    conv.phase_submission = True
    conv.scheduled_transition_at = datetime(2026, 8, 20, 14, 30)
    conv.scheduled_transition_target = 'informed_voting'
    db.session.commit()

    resp = _workspace(auth_client, 'test-conv')

    assert resp.status_code == 200
    assert resp.get_json()['data']['scheduledTransition'] == {
        'at': '2026-08-20T14:30:00Z',
        'target': 'informed_voting',
        'targetLabel': 'Informed vote',
    }


def test_real_conversation_warns_on_direct_arrival(auth_client, conv, participation):
    # #293 state model: arriving at a real conversation without having chosen the
    # real space (deep link) warns once. The "I understand" acknowledgement is
    # the client's rendering of this flag.
    resp = _workspace(auth_client, 'test-conv')

    assert resp.status_code == 200
    assert resp.get_json()['data']['spaceWarning'] == 'real'


def test_real_conversation_no_warning_after_choosing_real(auth_client, conv, participation):
    _lane(auth_client, 'real')                        # explicit choice of real space

    resp = _workspace(auth_client, 'test-conv')

    assert resp.status_code == 200
    assert resp.get_json()['data']['spaceWarning'] is None


def test_demo_conversation_warns_on_direct_arrival(client, app):
    demo = Conversation(slug='demo-direct', polis_id='demodirect', title='Demo Direct',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(demo)
    db.session.commit()

    resp = _workspace(client, 'demo-direct')

    assert resp.status_code == 200
    assert resp.get_json()['data']['spaceWarning'] == 'demo'


def test_demo_conversation_no_warning_after_choosing_demo(client, app):
    demo = Conversation(slug='demo-chosen', polis_id='demochosen', title='Demo Chosen',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(demo)
    db.session.commit()
    _lane(client, 'demo')                             # explicit choice of demo space

    resp = _workspace(client, 'demo-chosen')

    assert resp.status_code == 200
    assert resp.get_json()['data']['spaceWarning'] is None


def test_admin_never_sees_space_warning(admin_client, admin_participant, conv):
    # Admin-access users are exempt from the space warning (#293) even on a
    # direct arrival that would warn a normal participant (see
    # test_real_conversation_warns_on_direct_arrival).
    db.session.add(Participation(participant_id=admin_participant.id,
                                 conversation_id=conv.id, pseudonym='admin-pseudo'))
    db.session.commit()

    resp = _workspace(admin_client, 'test-conv')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['viewer']['state'] == 'participant'   # actually served, not join_required
    assert data['spaceWarning'] is None
    assert data['capabilities']['moderate'] is True


def test_demo_roaming_reuses_one_synthetic_guest(app):
    # #293: roaming across demos reuses the SAME synthetic guest (no orphan rows).
    # Uses a fresh request context per visit so `g` (which caches the current
    # participant) is fresh — as it is per-request in production. The shared-client
    # path can't observe this: conftest holds one app-context for the whole test,
    # so g leaks between client.get() calls and _current_participant returns stale None.
    from flask import session, g
    from app import _ensure_demo_participation

    d1 = Conversation(slug='roam-a', polis_id='roampolisa', title='Roam A',
                      active=True, access_policy='demo')
    d2 = Conversation(slug='roam-b', polis_id='roampolisb', title='Roam B',
                      active=True, access_policy='demo')
    db.session.add_all([d1, d2])
    db.session.commit()

    with app.test_request_context('/c/roam-a'):
        g.pop('participant', None)            # fresh per-request identity (as in prod)
        p1 = _ensure_demo_participation(d1)   # brand-new guest
        guest_id = p1.participant_id
        xid = session['xid']

    with app.test_request_context('/c/roam-b'):
        g.pop('participant', None)            # fresh per-request identity (as in prod)
        session['xid'] = xid                  # same guest arrives at another demo
        session['demo_conversation_id'] = d1.id
        p2 = _ensure_demo_participation(d2)
        assert p2.participant_id == guest_id  # reused, not a new guest

    assert Participant.query.filter_by(is_demo=True).count() == 1
    guest = Participant.query.filter_by(is_demo=True).one()
    assert Participation.query.filter_by(participant_id=guest.id).count() == 2


def test_logged_in_user_stays_logged_in_in_demo(auth_client, participant, app):
    # #293: a logged-in user entering a demo participates as themselves and is
    # NOT logged out; a real (non-synthetic) participation is created.
    demo = Conversation(slug='demo-logged-in', polis_id='demologged', title='Demo LoggedIn',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(demo)
    db.session.commit()

    resp = _workspace(auth_client, 'demo-logged-in')
    assert resp.status_code == 200

    with auth_client.session_transaction() as sess:
        assert sess.get('username') == 'testuser'         # still logged in
        assert 'demo_conversation_id' not in sess         # no synthetic demo binding

    part = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=demo.id).one()
    assert part.participant.is_demo is False               # their real identity


def test_logged_out_visitor_gets_synthetic_demo_guest(client, app):
    demo = Conversation(slug='demo-anon', polis_id='demoanon01', title='Demo Anon',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(demo)
    db.session.commit()

    resp = _workspace(client, 'demo-anon')

    assert resp.status_code == 200
    part = Participation.query.filter_by(conversation_id=demo.id).one()
    assert part.participant.is_demo is True
    with client.session_transaction() as sess:
        assert sess['demo_conversation_id'] == demo.id
        assert 'username' not in sess


def test_demo_session_can_roam_between_demos(client, app):
    # #293: a demo session is no longer locked to one demo — it may move freely
    # between demo conversations (rebinding to each).
    d1 = Conversation(slug='demo-a', polis_id='demopolisa', title='Demo A',
                      active=True, access_policy='demo')
    d2 = Conversation(slug='demo-b', polis_id='demopolisb', title='Demo B',
                      active=True, access_policy='demo')
    db.session.add_all([d1, d2])
    db.session.commit()

    assert _workspace(client, 'demo-a').status_code == 200
    assert _workspace(client, 'demo-b').status_code == 200   # was 403 before #293
    with client.session_transaction() as sess:
        assert sess['demo_conversation_id'] == d2.id         # rebound to the latest


def test_demo_session_entering_real_exits_demo_not_forbidden(client, app):
    # #293: leaving the demo for a real consultation exits the demo and falls back
    # to the normal authentication requirement — it is not forbidden.
    demo = Conversation(slug='demo2', polis_id='demopolis2', title='Demo',
                        active=True, access_policy='demo')
    public = Conversation(slug='public-after-demo', polis_id='pubdemo123',
                          title='Public', active=True, access_policy='public')
    db.session.add_all([demo, public])
    db.session.commit()
    _workspace(client, 'demo2')

    resp = _workspace(client, 'public-after-demo')

    assert resp.status_code == 401                        # unauthenticated, not 403
    assert resp.get_json()['error']['code'] == 'unauthorized'
    with client.session_transaction() as sess:
        assert 'demo_conversation_id' not in sess         # demo binding cleared


def test_demo_conversation_allows_statement_route_past_auth(client, app):
    # Demo runs the full flow (#293): the statement-submit command no longer
    # bounces a demo session at the auth gate. It reaches statement preparation
    # (proved by the policy call) and fails there because Polis is unconfigured —
    # no statement is written and nothing is posted upstream.
    from flask import g

    from services.admin_statements import ModerationPolicyUpstreamFailed

    demo = Conversation(slug='demo3', polis_id='demopolis3', title='Demo',
                        active=True, access_policy='demo', phase_submission=True)
    db.session.add(demo)
    db.session.commit()
    _workspace(client, 'demo3')
    # conftest holds one app context for the whole test, so `g` (which caches the
    # resolved participant) leaks across client calls; in production it is fresh
    # per request. Drop it so the POST resolves the demo guest from the session.
    g.pop('participant', None)

    with patch('app._ensure_statement_moderation_policy',
               side_effect=ModerationPolicyUpstreamFailed()) as policy:
        resp = client.post('/api/v1/conversations/demo3/statements',
                           headers={'Idempotency-Key': 'demo-statement-key-1'},
                           json={'text': 'anonymous write'})

    assert resp.status_code == 502                       # was 401 under the old rule
    assert resp.get_json()['error']['code'] == 'upstream_unavailable'
    policy.assert_called_once()                          # got past the auth gate
    part = Participation.query.filter_by(conversation_id=demo.id).one()
    assert (part.new_stmt_ids or []) == []               # nothing recorded


# ── Intermediate results ──────────────────────────────────────────────────────

def test_personal_results_renders_clustering_data(auth_client, conv, participation,
                                                  monkeypatch):
    """#81: with ONLY the Personal results toggle on, the intermediate-results
    payload must carry the clustering results — not fall back to an unpublished
    state. Regression guard for the bug where both the fetch and the render were
    gated on phase_public_results only."""
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

    resp = auth_client.get('/api/v1/conversations/test-conv/intermediate-results')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['state'] == 'ready'                       # results projected
    assert data['consensus'] == [{
        'choice': 'agree',
        'statement': 'Cats make excellent companions',
        'percentage': 82,
    }]


def test_empty_polis_results_shows_not_enough_votes(auth_client, conv, participation,
                                                    monkeypatch):
    """Particiapi returns all-empty arrays when there aren't enough votes for
    clustering. The payload must report the pending state rather than a
    half-built 'ready' projection."""
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
    # Simulate a recent trigger so rate-limit suppresses recompute → plain pending.
    import time
    monkeypatch.setitem(app_module._math_recompute_last, conv.id, time.monotonic())

    resp = auth_client.get('/api/v1/conversations/test-conv/intermediate-results')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['state'] == 'pending'
    assert data['consensus'] == []
    assert data['groups'] == []


def test_none_polis_results_shows_not_enough_votes(auth_client, conv, participation,
                                                   monkeypatch):
    """When Particiapi errors or returns None (e.g. math hasn't run), the payload
    must report the pending state rather than a blank 'ready' projection."""
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

    resp = auth_client.get('/api/v1/conversations/test-conv/intermediate-results')

    assert resp.status_code == 200
    assert resp.get_json()['data']['state'] == 'pending'


def test_empty_results_triggers_recompute_and_shows_computing_message(
        auth_client, conv, participation, monkeypatch):
    """When results are empty and the cooldown has elapsed, queue_math_recompute
    is called and the payload reports 'recomputing' instead of 'pending'."""
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

    resp = auth_client.get('/api/v1/conversations/test-conv/intermediate-results')

    assert resp.status_code == 200
    assert recompute_called == [conv.polis_id]
    assert resp.get_json()['data']['state'] == 'recomputing'


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

    resp = auth_client.get('/api/v1/conversations/test-conv/intermediate-results')

    assert resp.status_code == 200
    assert recompute_called == []
    assert resp.get_json()['data']['state'] == 'pending'   # falls back to pending


# ── Report ────────────────────────────────────────────────────────────────────

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
        resp = client.get('/api/v1/conversations/test-conv/results')

    assert resp.status_code == 200
    assert seen['filter'] == Phase6ResultsFilter(
        excluded_tids=frozenset({42}),
        excluded_pids=frozenset({7}),
    )


def test_personal_report_redirects_anonymous_viewer_to_login(client, conv):
    conv.active = False
    conv.phase_personal_results = True
    conv.closed_at = datetime.now(timezone.utc)
    db.session.commit()

    response = client.get('/api/v1/conversations/test-conv/results')

    assert response.status_code == 401
    assert response.get_json()['error']['code'] == 'unauthorized'


# ── Access control ────────────────────────────────────────────────────────────

def test_invite_only_blocks_uninvited(client, app, participant):
    login(client, 'testuser')
    c = Conversation(slug='private', polis_id='pri1234567', title='Private',
                     active=True, access_policy='invite_only')
    db.session.add(c)
    db.session.commit()

    entry = _entry(client, 'private')
    assert entry.status_code == 200
    assert entry.get_json()['data']['state'] == 'invite_denied'

    workspace = _workspace(client, 'private')
    assert workspace.status_code == 403
    assert workspace.get_json()['error']['code'] == 'invite_only'


def test_invite_only_allows_invited(client, app, participant):
    login(client, 'testuser')
    c = Conversation(slug='private2', polis_id='pr21234567', title='Private2',
                     active=True, access_policy='invite_only')
    db.session.add(c)
    db.session.commit()
    inv = ConversationInvite(conversation_id=c.id, mw_username='testuser')
    db.session.add(inv)
    db.session.commit()

    entry = _entry(client, 'private2')
    assert entry.status_code == 200
    assert entry.get_json()['data']['state'] == 'join'

    workspace = _workspace(client, 'private2')
    assert workspace.status_code == 200
    assert workspace.get_json()['data']['viewer']['state'] == 'join_required'


def test_invite_only_allows_already_joined(client, app, participant):
    """A participant who already joined can visit even without an invite row."""
    c = Conversation(slug='private3', polis_id='pr31234567', title='Private3',
                     active=True, access_policy='invite_only')
    db.session.add(c)
    db.session.commit()
    part = Participation(participant_id=participant.id,
                         conversation_id=c.id, pseudonym='quick-otter')
    db.session.add(part)
    db.session.commit()
    login(client, 'testuser')

    assert ConversationInvite.query.filter_by(conversation_id=c.id).count() == 0
    resp = _workspace(client, 'private3')

    assert resp.status_code == 200
    assert resp.get_json()['data']['viewer'] == {
        'state': 'participant', 'pseudonym': 'quick-otter',
    }
