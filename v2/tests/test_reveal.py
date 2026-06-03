"""Tests for the identity reveal window: state transitions and POST validation."""
from datetime import datetime, timedelta, timezone

import pytest

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


# ── Window state (via conversation page) ─────────────────────────────────────

def test_reveal_state_pending(auth_client, app, participant):
    """Closed < 30 days ago → pending state shows the date the window opens."""
    conv = _closed_conv(app, 'pending-conv', 10, 'pnd1234567')
    _participate(participant, conv, 'quick-mouse')
    resp = auth_client.get('/c/pending-conv')
    assert resp.status_code == 200
    assert b'reveal window opens' in resp.data.lower()


def test_reveal_state_open(auth_client, app, participant):
    """Closed 30–59 days ago → reveal window open link is shown."""
    conv = _closed_conv(app, 'open-conv', 45, 'opn1234567')
    _participate(participant, conv, 'bold-hawk')
    resp = auth_client.get('/c/open-conv')
    assert resp.status_code == 200
    assert b'reveal window is open' in resp.data.lower()


def test_reveal_state_expired(auth_client, app, participant):
    """Closed ≥ 60 days ago → window expired; only 'consultation is closed' shown."""
    conv = _closed_conv(app, 'expired-conv', 70, 'exp1234567')
    _participate(participant, conv, 'calm-deer')
    resp = auth_client.get('/c/expired-conv')
    assert resp.status_code == 200
    assert b'consultation is closed' in resp.data.lower()
    assert b'reveal window' not in resp.data.lower()


def test_reveal_state_already_revealed(auth_client, app, participant):
    """Participant who revealed sees their identity linked message."""
    conv = _closed_conv(app, 'revealed-conv', 45, 'rev1234567')
    p = _participate(participant, conv, 'wise-wolf')
    p.public_username = 'testuser'
    p.revealed_at = datetime.now(timezone.utc) - timedelta(days=2)
    db.session.commit()
    resp = auth_client.get('/c/revealed-conv')
    assert resp.status_code == 200
    assert b'linked your identity' in resp.data.lower()


# ── Reveal GET (form page) ────────────────────────────────────────────────────

def test_reveal_get_accessible_in_window(auth_client, app, participant):
    conv = _closed_conv(app, 'reveal-form', 45, 'frm1234567')
    _participate(participant, conv, 'swift-crane')
    resp = auth_client.get('/c/reveal-form/reveal')
    assert resp.status_code == 200


def test_reveal_get_requires_closed_conversation(auth_client, app, participant):
    """Reveal page 404s for an active (not closed) conversation."""
    c = Conversation(slug='still-open', polis_id='opn9876543',
                     title='Still Open', active=True, access_policy='public')
    db.session.add(c)
    db.session.commit()
    _participate(participant, c, 'sharp-lynx')
    resp = auth_client.get('/c/still-open/reveal')
    assert resp.status_code == 404


# ── Reveal POST ───────────────────────────────────────────────────────────────

def test_reveal_post_in_window_sets_public_username(auth_client, app, participant):
    conv = _closed_conv(app, 'do-reveal', 45, 'dor1234567')
    part = _participate(participant, conv, 'brave-fox')
    resp = auth_client.post('/c/do-reveal/reveal', data={'confirm': '1'})
    assert resp.status_code == 302
    db.session.refresh(part)
    assert part.public_username == 'testuser'
    assert part.revealed_at is not None


def test_reveal_post_without_confirm_redirects_back(auth_client, app, participant):
    conv = _closed_conv(app, 'no-confirm', 45, 'noc1234567')
    _participate(participant, conv, 'kind-bear')
    resp = auth_client.post('/c/no-confirm/reveal', data={})
    assert resp.status_code == 302
    assert '/reveal' in resp.headers['Location']


def test_reveal_post_before_window_rejected(auth_client, app, participant):
    """POST reveal before the 30-day cooldown returns 400."""
    conv = _closed_conv(app, 'too-early', 5, 'ear1234567')
    _participate(participant, conv, 'shy-duck')
    resp = auth_client.post('/c/too-early/reveal', data={'confirm': '1'})
    assert resp.status_code == 400


def test_reveal_post_after_window_rejected(auth_client, app, participant):
    """POST reveal after the 60-day window expires returns 400."""
    conv = _closed_conv(app, 'too-late', 70, 'lat1234567')
    _participate(participant, conv, 'slow-turtle')
    resp = auth_client.post('/c/too-late/reveal', data={'confirm': '1'})
    assert resp.status_code == 400


def test_reveal_post_already_revealed_rejected(auth_client, app, participant):
    conv = _closed_conv(app, 'already', 45, 'alr1234567')
    part = _participate(participant, conv, 'tall-crane')
    part.public_username = 'testuser'
    part.revealed_at = datetime.now(timezone.utc)
    db.session.commit()
    resp = auth_client.post('/c/already/reveal', data={'confirm': '1'})
    assert resp.status_code == 400


# ── Reveal permanence ─────────────────────────────────────────────────────────

def test_revealed_identity_remains_after_window(auth_client, app):
    """Voluntary public reveals remain visible after the opt-in window closes."""
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

    resp = auth_client.get('/c/old-conv')
    db.session.refresh(part)
    assert resp.status_code == 200
    assert b'linked your identity' in resp.data.lower()
    assert part.public_username == 'revealeduser'
    assert part.revealed_at is not None


def test_reveal_page_keeps_existing_reveal_after_window(auth_client, app):
    """The reveal detail page still shows an already-public reveal after day 60."""
    conv = _closed_conv(app, 'recent-conv', 65, 'rec1234567')
    p = Participant(mw_user_id=66666, mw_username='recentuser', xid='s' * 64)
    db.session.add(p)
    db.session.commit()
    part = Participation(
        participant_id=p.id, conversation_id=conv.id, pseudonym='fast-eagle',
        public_username='recentuser',
        revealed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db.session.add(part)
    db.session.commit()
    with auth_client.session_transaction() as sess:
        sess['username'] = p.mw_username
        sess['xid'] = p.xid

    resp = auth_client.get('/c/recent-conv/reveal')
    db.session.refresh(part)
    assert resp.status_code == 200
    assert b'identity linked' in resp.data.lower()
    assert part.public_username == 'recentuser'
