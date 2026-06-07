"""Rendered-markup regression guards for the accessibility work in PR #150.

These assert that the a11y affordances are actually present in the served HTML,
so a future template edit that drops an aria hook or breaks the
tab `aria-controls` -> panel `id` coupling fails CI instead of silently
regressing (the rest of the suite only proves templates still render).
"""
import re

import pytest

from db import Conversation, Participation, db


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


# ── Global landmarks (base.html) ───────────────────────────────────────────────

def test_skip_link_and_main_landmark(client, conv):
    """Every page exposes a skip link targeting a focusable main landmark (2.4.1)."""
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'class="skip-link" href="#main"' in resp.data
    assert b'<main id="main" tabindex="-1">' in resp.data


# ── Page headings (1.3.1 / 2.4.6) ──────────────────────────────────────────────

def test_home_has_h1_logged_out(client, conv):
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'<h1' in resp.data


def test_home_has_h1_logged_in(auth_client, conv):
    resp = auth_client.get('/')
    assert resp.status_code == 200
    assert b'<h1' in resp.data


def test_conversation_has_h1_with_title(auth_client, conv, participation):
    conv.phase_submission = True
    db.session.commit()
    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    assert re.search(rb'<h1[^>]*>\s*Test Conversation\s*</h1>', resp.data)


# ── Name/role/value affordances (4.1.2 / 1.3.1) ────────────────────────────────

def test_composer_textareas_have_accessible_names(auth_client, conv, participation):
    conv.phase_submission = True
    db.session.commit()
    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    assert b'aria-labelledby="composer-suggest-title"' in resp.data
    assert b'aria-labelledby="composer-newstmt-title"' in resp.data


def test_progressbar_has_static_valuenow(auth_client, conv, participation):
    """The vote progressbar must carry aria-valuenow before JS runs (m2)."""
    conv.phase_submission = True
    db.session.commit()
    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    bar = re.search(rb'role="progressbar"[^>]*>', resp.data)
    assert bar, 'progressbar not rendered'
    assert b'aria-valuenow=' in bar.group(0)


# ── The high-value coupling guard ──────────────────────────────────────────────

def test_tab_aria_controls_match_panel_ids(auth_client, conv, participation):
    """Each tab's aria-controls must point at a rendered panel id.

    A future panel-id rename would otherwise leave activate() selecting nothing
    while still flipping aria-selected — a silent break the render-only suite
    would never catch.
    """
    conv.phase_submission = True          # -> 'vote' tab
    conv.phase_argument_mapping = True     # -> 'arguments' tab (no Polis network)
    db.session.commit()
    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    html = resp.data.decode()

    # Pull aria-controls only off elements that are role="tab".
    tab_controls = re.findall(r'role="tab"[^>]*aria-controls="([^"]+)"', html)
    assert len(tab_controls) >= 2, f'expected a multi-tab tablist, got {tab_controls}'
    for panel_id in tab_controls:
        assert f'id="{panel_id}"' in html, \
            f'tab aria-controls="{panel_id}" has no matching panel id'
