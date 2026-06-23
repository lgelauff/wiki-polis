"""Rendered-markup regression guards for the accessibility work in PR #150.

These assert that the a11y affordances are actually present in the served HTML,
so a future template edit that drops an aria hook or breaks the
tab `aria-controls` -> panel `id` coupling fails CI instead of silently
regressing (the rest of the suite only proves templates still render).
"""
import os
import re

import pytest

from db import Conversation, Participation, db

_STYLE_CSS = os.path.join(os.path.dirname(__file__), os.pardir, 'static', 'style.css')


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


# ── No hidden API-proxy controls (4.1.2 / #159) ───────────────────────────────

def test_conversation_has_no_hidden_pa_proxy_controls(auth_client, conv, participation):
    """The participant UI talks to Particiapi directly through same-origin routes.

    There must be no hidden pa-* controls left for keyboard or screen-reader users
    to encounter, and no web-component bundle imports in the rendered page.
    """
    conv.phase_submission = True
    db.session.commit()
    resp = auth_client.get('/c/test-conv')
    assert resp.status_code == 200
    html = resp.data.decode()
    css = open(_STYLE_CSS, encoding='utf-8').read()

    assert '<pa-' not in html
    assert 'pvb-hidden' not in html
    assert 'particiapp-web-components.js' not in html
    assert 'particiapp-web-client.js' not in html
    assert 'data-proxy-root="/proxy/particiapi/"' in html
    assert "api/session?create=true" in html
    assert "/votes/" in html
    assert '.pvb-hidden' not in css


# ── Consultation listing semantics (1.3.1 / 2.4.6 / 4.1.2) ─────────────────────

def test_home_listing_has_list_and_heading_semantics(client, conv):
    """The consultation listing is a real list with heading-navigable titles.

    Sibling <a> cards with no list role gave SR users no "list, N items" / item
    position; plain <span> titles were not heading-navigable (1.3.1 / 2.4.6).
    """
    resp = client.get('/')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert '<ul class="conv-list">' in html
    assert '<h2 class="home-section-label"' in html
    assert re.search(r'<h3 class="conv-card-title">\s*Test Conversation\s*</h3>', html)


def test_home_pseudonym_announced_with_context(auth_client, conv, participation):
    """A joined consultation announces the pseudonym labelled as such, not as a
    bare token, and the redundant visible badge is hidden from AT (1.3.1 / 4.1.2)."""
    resp = auth_client.get('/')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'your pseudonym: happy-fox' in html
    assert '<span class="conv-card-badge" aria-hidden="true">happy-fox</span>' in html


def test_home_output_symbols_expose_state_and_labels(auth_client, conv, participation):
    conv.phase_personal_results = True
    db.session.commit()
    resp = auth_client.get('/')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'class="conv-output-grid"' in html
    assert 'data-state="ready"' in html
    assert 'data-state="pending"' in html
    assert 'aria-label="After Explore phase: topic and participant clustering"' in html


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
