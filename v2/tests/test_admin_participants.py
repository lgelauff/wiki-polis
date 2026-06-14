"""Tests for the admin participants tab + last_engagement tracking (#42)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import g

from app import _touch_engagement, _touch_engagement_by_polis_id
from db import Participation, db


def _fake_upstream(status_code=200, content=b'{}'):
    """Stand-in for a requests Response from Particiapi (mirrors test_proxy_blueprint)."""
    m = MagicMock()
    m.status_code = status_code
    m.content = content
    m.headers = {'Content-Type': 'application/json'}
    m.cookies = {}
    return m


@pytest.fixture
def participation(app, participant, conversation):
    p = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='quiet-otter',
    )
    db.session.add(p)
    db.session.commit()
    return p


# ── last_engagement helper ──────────────────────────────────────────────────

def test_touch_sets_when_none(participation):
    assert participation.last_engagement is None
    _touch_engagement(participation)
    assert participation.last_engagement is not None


def test_touch_is_throttled(participation):
    # naive-UTC, as the column stores it (SQLite/MySQL strip tzinfo on round-trip).
    recent = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)
    participation.last_engagement = recent
    db.session.commit()
    _touch_engagement(participation)
    # Within the throttle window → unchanged.
    assert participation.last_engagement == recent


def test_touch_updates_past_throttle(participation):
    stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    participation.last_engagement = stale
    db.session.commit()
    _touch_engagement(participation)
    assert participation.last_engagement > stale


def test_touch_none_is_noop(app):
    # Must not raise on a missing participation.
    _touch_engagement(None)


def test_touch_by_polis_id_resolves_participant(app, participant, conversation, participation):
    with app.test_request_context():
        g.participant = participant
        _touch_engagement_by_polis_id(conversation.polis_id)
    db.session.refresh(participation)
    assert participation.last_engagement is not None


def test_touch_by_polis_id_unknown_conv_is_silent(app, participant):
    with app.test_request_context():
        g.participant = participant
        _touch_engagement_by_polis_id('nope9999')  # no matching conversation


# ── admin participants route ────────────────────────────────────────────────

def test_participants_tab_ok_for_admin(admin_client, conversation, participation):
    resp = admin_client.get(f'/admin/conversations/{conversation.id}/participants')
    assert resp.status_code == 200
    assert b'testuser' in resp.data          # the participant's username
    assert b'Last engagement' in resp.data


def test_participants_tab_forbidden_for_non_moderator(auth_client, conversation, participation):
    resp = auth_client.get(f'/admin/conversations/{conversation.id}/participants')
    assert resp.status_code == 403


# ── Phase-2 vote through the proxy bumps last_engagement (regression: the web
#    client casts votes with PUT .../votes/<tid>, not POST .../votes) ───────────

def test_phase2_vote_put_via_proxy_touches_engagement(auth_client, conversation, participation):
    assert participation.last_engagement is None
    with patch('app.requests.request', return_value=_fake_upstream()):
        resp = auth_client.put(
            f'/proxy/particiapi/api/conversations/{conversation.polis_id}/votes/7',
            headers={'Sec-Fetch-Site': 'same-origin'}, json={'value': -1})
    assert resp.status_code == 200
    db.session.refresh(participation)
    assert participation.last_engagement is not None


def test_proxy_vote_fetch_get_does_not_touch_engagement(auth_client, conversation, participation):
    # A GET to the votes path is a read, not an action — must NOT count as engagement.
    with patch('app.requests.request', return_value=_fake_upstream()):
        resp = auth_client.get(
            f'/proxy/particiapi/api/conversations/{conversation.polis_id}/votes')
    assert resp.status_code == 200
    db.session.refresh(participation)
    assert participation.last_engagement is None
