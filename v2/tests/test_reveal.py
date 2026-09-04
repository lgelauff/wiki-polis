"""Tests for the identity reveal window: state transitions and POST validation."""
from datetime import datetime, timedelta, timezone

from app import _reveal_context, _REVEAL_COOLDOWN_DAYS, _REVEAL_WINDOW_DAYS
from db import Conversation, Participant, Participation, db


def _closed_conv(app, slug, days_ago, polis_id):
    c = Conversation(
        slug=slug, polis_id=polis_id, title=slug.replace('-', ' ').title(),
        active=False, access_policy='public',
        closed_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.session.add(c)
    db.session.commit()
    return c


def _participate(participant, conv, pseudonym):
    p = Participation(participant_id=participant.id,
                      conversation_id=conv.id, pseudonym=pseudonym)
    db.session.add(p)
    db.session.commit()
    return p


# ── Window state (via the identity-reveal read endpoint) ─────────────────────
#
# These drove /c/<slug> and /c/<slug>/reveal and read the rendered page. Both are
# canonical SPA paths now: the shell is served ahead of route dispatch, so a GET
# returns 200 with empty HTML and every "phrase in page" assertion would be
# meaningless. The same states are decided by the server and published on
# GET /api/v1/conversations/<slug>/identity-reveal, so they are asserted there.
# The countdown element, the timeline block and the wording are the SPA's.

def _reveal(client, slug):
    resp = client.get(f'/api/v1/conversations/{slug}/identity-reveal')
    assert resp.status_code == 200
    return resp.get_json()['data']


def test_reveal_state_pending(auth_client, app, participant):
    """Closed < 30 days ago -> pending state, and the window is not yet offered."""
    conv = _closed_conv(app, 'pending-conv', 10, 'pnd1234567')
    _participate(participant, conv, 'quick-mouse')
    data = _reveal(auth_client, 'pending-conv')
    assert data['state'] == 'pending'
    assert data['capabilities']['revealIdentity'] is False
    assert data['timeline']['opensAt'] is not None      # the date the page announced


def test_reveal_timeline_shows_close_and_window_dates(auth_client, app, participant):
    """#70: the three timeline instants are closed -> +30d opens -> +60d closes.

    The page printed these as formatted dates; the server decides them. Asserting
    the exact offsets (rather than merely that the fields are present, which
    test_identity_reveal_api.py already does) is what keeps the 30/60-day window
    itself under test.
    """
    conv = _closed_conv(app, 'dated-conv', 10, 'dat1234567')
    _participate(participant, conv, 'quiet-fox')
    with app.app_context():
        closed = Conversation.query.filter_by(slug='dated-conv').first().closed_at
    if closed.tzinfo is None:                 # SQLite hands back a naive UTC instant
        closed = closed.replace(tzinfo=timezone.utc)

    timeline = _reveal(auth_client, 'dated-conv')['timeline']

    def _parse(value):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))

    assert _parse(timeline['closedAt']) == closed
    assert _parse(timeline['opensAt']) == closed + timedelta(days=_REVEAL_COOLDOWN_DAYS)
    assert _parse(timeline['closesAt']) == closed + timedelta(
        days=_REVEAL_COOLDOWN_DAYS + _REVEAL_WINDOW_DAYS)


def test_reveal_state_open(auth_client, app, participant):
    """Closed 30-59 days ago -> reveal window open and the opt-in is offered."""
    conv = _closed_conv(app, 'open-conv', 45, 'opn1234567')
    _participate(participant, conv, 'bold-hawk')
    data = _reveal(auth_client, 'open-conv')
    assert data['state'] == 'open'
    assert data['capabilities']['revealIdentity'] is True
    assert data['publicUsername'] is None
    # The live countdown had a target; the SPA renders it from this instant.
    assert data['timeline']['nextBoundaryAt'] == data['timeline']['closesAt']


def test_reveal_state_expired(auth_client, app, participant):
    """Closed >= 60 days ago -> window expired, nothing further to count down to."""
    conv = _closed_conv(app, 'expired-conv', 70, 'exp1234567')
    _participate(participant, conv, 'calm-deer')
    data = _reveal(auth_client, 'expired-conv')
    assert data['state'] == 'expired'
    assert data['capabilities']['revealIdentity'] is False
    assert data['timeline']['nextBoundaryAt'] is None


def test_reveal_state_already_revealed(auth_client, app, participant):
    """A participant who revealed is reported as revealed, with their public name."""
    conv = _closed_conv(app, 'revealed-conv', 45, 'rev1234567')
    p = _participate(participant, conv, 'wise-wolf')
    p.public_username = 'testuser'
    p.revealed_at = datetime.now(timezone.utc) - timedelta(days=2)
    db.session.commit()
    data = _reveal(auth_client, 'revealed-conv')
    assert data['state'] == 'revealed'
    assert data['publicUsername'] == 'testuser'
    assert data['capabilities']['revealIdentity'] is False   # nothing left to do


# ── Reveal availability ───────────────────────────────────────────────────────

def test_reveal_requires_closed_conversation(auth_client, app, participant):
    """Reveal is unavailable while the conversation is still running.

    The Jinja page 404'd; the API answers 409 conflict, which is the same refusal
    with a typed reason.
    """
    c = Conversation(slug='still-open', polis_id='opn9876543',
                     title='Still Open', active=True, access_policy='public')
    db.session.add(c)
    db.session.commit()
    _participate(participant, c, 'sharp-lynx')

    resp = auth_client.get('/api/v1/conversations/still-open/identity-reveal')

    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'conflict'


# The reveal POST tests are gone because test_identity_reveal_api.py already holds
# each of their assertions against the surviving endpoint, and holds them at least
# as strictly:
#   test_reveal_post_in_window_sets_public_username and
#   test_reveal_post_already_revealed_is_safe_replay ->
#       test_identity_reveal_command_is_irreversible_and_idempotent, which asserts
#       201 then 200, state 'revealed', and the same two Participation columns.
#   test_reveal_post_without_confirm_redirects_back ->
#       test_identity_reveal_requires_explicit_true_confirmation (400, and
#       public_username still unset).
#   test_reveal_post_before_window_rejected ->
#       test_identity_reveal_command_rejects_closed_window_with_typed_state, which
#       uses the same 10-days-closed conversation and asserts details.state
#       'pending'.
# test_reveal_get_accessible_in_window is also gone: it asserted only a 200, which
# the SPA shell made vacuously true, and test_reveal_state_open above now covers
# the in-window read properly.
#
# The expired half of the POST rejection was NOT covered anywhere, so it stays:

def test_reveal_post_after_window_rejected(auth_client, app, participant):
    """POST reveal after the 60-day window expires is refused, naming the state."""
    conv = _closed_conv(app, 'too-late', 70, 'lat1234567')
    part = _participate(participant, conv, 'slow-turtle')
    resp = auth_client.post('/api/v1/conversations/too-late/identity-reveal',
                            json={'confirm': True})
    assert resp.status_code == 409
    error = resp.get_json()['error']
    assert error['code'] == 'identity_reveal_unavailable'
    assert error['details'] == {'state': 'expired'}
    db.session.refresh(part)
    assert part.public_username is None                # nothing was linked


# ── Reveal permanence ─────────────────────────────────────────────────────────

def test_revealed_identity_remains_after_window(auth_client, app):
    """A voluntary reveal stays public after the opt-in window closes.

    Merged with test_reveal_page_keeps_existing_reveal_after_window, which asserted
    the same property through the other deleted page; both now read one endpoint.
    """
    conv = _closed_conv(app, 'old-conv', 65, 'old1234567')
    p = Participant(mw_user_id=77777, mw_username='revealeduser', xid='r' * 64)
    db.session.add(p)
    db.session.commit()
    part = Participation(
        participant_id=p.id, conversation_id=conv.id, pseudonym='gentle-bear',
        public_username='revealeduser',
        revealed_at=datetime.now(timezone.utc) - timedelta(days=35),
    )
    db.session.add(part)
    db.session.commit()
    with auth_client.session_transaction() as sess:
        sess['username'] = p.mw_username
        sess['xid'] = p.xid

    data = _reveal(auth_client, 'old-conv')

    db.session.refresh(part)
    # The window is long gone, but the reveal it produced is not withdrawn.
    assert data['state'] == 'revealed'
    assert data['publicUsername'] == 'revealeduser'
    assert part.public_username == 'revealeduser'
    assert part.revealed_at is not None


# ── _reveal_context: countdown target, tz-normalization, boundaries (#70) ──────

def _ctx(days_ago, revealed=False):
    """Call _reveal_context on a lightweight (unpersisted) closed conversation."""
    conv = Conversation(slug='x', polis_id='p', title='t', active=False,
                        access_policy='public',
                        closed_at=datetime.now(timezone.utc) - timedelta(days=days_ago))
    part = Participation(public_username='Someone' if revealed else None)
    return _reveal_context(conv, part)


def test_reveal_context_target_pending_is_opens_at():
    ctx = _ctx(10)
    assert ctx['state'] == 'pending'
    assert ctx['countdown_target_iso'] == ctx['opens_at'].isoformat()
    assert ctx['opens_at'].tzinfo is not None          # aware UTC instant for the JS clock


def test_reveal_context_target_open_is_closes_at():
    ctx = _ctx(_REVEAL_COOLDOWN_DAYS + 5)
    assert ctx['state'] == 'open'
    assert ctx['countdown_target_iso'] == ctx['closes_at'].isoformat()


def test_reveal_context_no_target_when_expired_or_revealed():
    assert _ctx(_REVEAL_COOLDOWN_DAYS + _REVEAL_WINDOW_DAYS + 5)['countdown_target_iso'] is None
    assert _ctx(_REVEAL_COOLDOWN_DAYS + 5, revealed=True)['countdown_target_iso'] is None


def test_reveal_context_boundaries():
    """Just inside the cooldown → pending; just past it → open; past the window → expired."""
    assert _ctx(_REVEAL_COOLDOWN_DAYS - 0.01)['state'] == 'pending'
    assert _ctx(_REVEAL_COOLDOWN_DAYS + 0.01)['state'] == 'open'
    assert _ctx(_REVEAL_COOLDOWN_DAYS + _REVEAL_WINDOW_DAYS + 0.01)['state'] == 'expired'


def test_reveal_context_normalizes_naive_closed_at():
    """#1: a naive closed_at is normalized to aware UTC, so the derived window dates and
    the countdown target are correct UTC instants (isoformat carries a +00:00 offset)."""
    conv = Conversation(slug='x', polis_id='p', title='t', active=False,
                        access_policy='public',
                        closed_at=(datetime.now(timezone.utc) - timedelta(days=10)).replace(tzinfo=None))  # naive
    ctx = _reveal_context(conv, Participation())
    assert ctx['opens_at'].tzinfo is not None and ctx['closes_at'].tzinfo is not None
    assert ctx['countdown_target_iso'].endswith('+00:00')
