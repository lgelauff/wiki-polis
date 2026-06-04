"""Tests for admin conversation management, roles, and phase toggles."""
from unittest.mock import patch

import pytest

from db import AdminRole, Conversation, ConversationInvite, db
from polis_admin import PolisServerError


@pytest.fixture
def conv(app):
    c = Conversation(
        slug='admin-conv', polis_id='adm1234567',
        title='Admin Test Conv', active=True, access_policy='public',
    )
    db.session.add(c)
    db.session.commit()
    return c


# ── Access control ────────────────────────────────────────────────────────────

def test_admin_index_requires_admin(auth_client):
    resp = auth_client.get('/admin')
    assert resp.status_code == 403


def test_admin_index_accessible_to_global_admin(admin_client):
    resp = admin_client.get('/admin')
    assert resp.status_code == 200


# ── Conversation CRUD ─────────────────────────────────────────────────────────

def test_create_conversation(admin_client):
    with patch('app.PolisServerClient.create_conversation',
               return_value='newpolis12'):
        resp = admin_client.post('/admin/conversations/new', data={
            'slug': 'new-conv',
            'title': 'New Conversation',
            'access_policy': 'public',
        })
    assert resp.status_code == 302
    conv = Conversation.query.filter_by(slug='new-conv').first()
    assert conv is not None
    assert conv.title == 'New Conversation'
    assert conv.polis_id == 'newpolis12'
    assert conv.active is True


def test_create_conversation_invalid_slug_rejected(admin_client):
    resp = admin_client.post('/admin/conversations/new', data={
        'slug': 'INVALID SLUG!',
        'polis_id': 'abc1234567',
        'title': 'Test',
        'access_policy': 'public',
    })
    assert resp.status_code == 400


def test_create_conversation_polis_failure_redirects(admin_client):
    """Polis server error on creation → redirect to admin with flash, no conv written."""
    with patch('app.PolisServerClient.create_conversation',
               side_effect=PolisServerError('test error')):
        resp = admin_client.post('/admin/conversations/new', data={
            'slug': 'should-not-exist',
            'title': 'Test',
            'access_policy': 'public',
        })
    assert resp.status_code == 302
    assert Conversation.query.filter_by(slug='should-not-exist').first() is None


def test_edit_conversation(admin_client, conv):
    resp = admin_client.post(f'/admin/conversations/{conv.id}/edit', data={
        'polis_id': 'new1234567',
        'title': 'Updated Title',
        'access_policy': 'invite_only',
    })
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.title == 'Updated Title'
    assert conv.access_policy == 'invite_only'


# ── Phase toggles ─────────────────────────────────────────────────────────────

def test_phase_toggles_on(admin_client, conv):
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phases', data={
        'phase_submission': '1',
        'phase_public_results': '1',
    })
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_submission is True
    assert conv.phase_public_results is True
    assert conv.phase_personal_results is False
    assert conv.phase_argument_mapping is False


def test_phase_toggles_off(admin_client, conv):
    conv.phase_submission = True
    db.session.commit()
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phases', data={})
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_submission is False


# ── Pause / close ─────────────────────────────────────────────────────────────

def test_pause_conversation(admin_client, conv):
    resp = admin_client.post(f'/admin/conversations/{conv.id}/pause')
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.paused is True


def test_unpause_conversation(admin_client, conv):
    conv.paused = True
    db.session.commit()
    resp = admin_client.post(f'/admin/conversations/{conv.id}/pause')
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.paused is False


def test_close_conversation_sets_closed_at(admin_client, conv):
    resp = admin_client.post(f'/admin/conversations/{conv.id}/close')
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.active is False
    assert conv.paused is False
    assert conv.closed_at is not None


def test_close_already_closed_rejected(admin_client, conv):
    conv.active = False
    db.session.commit()
    resp = admin_client.post(f'/admin/conversations/{conv.id}/close')
    assert resp.status_code == 400


def test_pause_closed_conversation_rejected(admin_client, conv):
    conv.active = False
    db.session.commit()
    resp = admin_client.post(f'/admin/conversations/{conv.id}/pause')
    assert resp.status_code == 400


# ── Roles ─────────────────────────────────────────────────────────────────────

def test_grant_moderator_role(admin_client, admin_participant, conv, participant):
    resp = admin_client.post('/admin/roles/add', data={
        'participant_id': participant.id,
        'conversation_id': conv.id,
        'role': 'moderator',
        'redirect_to': f'/admin/conversations/{conv.id}',
    })
    assert resp.status_code == 302
    role = AdminRole.query.filter_by(
        participant_id=participant.id,
        conversation_id=conv.id,
        role='moderator',
    ).first()
    assert role is not None


def test_grant_invalid_role_rejected(admin_client, participant):
    resp = admin_client.post('/admin/roles/add', data={
        'participant_id': participant.id,
        'role': 'superadmin',
    })
    assert resp.status_code == 400


def test_remove_role(admin_client, admin_participant, conv, participant):
    role = AdminRole(participant_id=participant.id,
                     conversation_id=conv.id, role='moderator')
    db.session.add(role)
    db.session.commit()

    resp = admin_client.post(f'/admin/roles/{role.id}/remove')
    assert resp.status_code == 302
    assert db.session.get(AdminRole, role.id) is None


# ── Invites ───────────────────────────────────────────────────────────────────

def test_add_invite(admin_client, conv):
    resp = admin_client.post(
        f'/admin/conversations/{conv.id}/invites/add',
        data={'mw_usernames': 'Alice\nBob\n'},
    )
    assert resp.status_code == 302
    invites = ConversationInvite.query.filter_by(conversation_id=conv.id).all()
    usernames = {inv.mw_username for inv in invites}
    assert usernames == {'Alice', 'Bob'}


def test_remove_invite(admin_client, conv):
    inv = ConversationInvite(conversation_id=conv.id, mw_username='Charlie')
    db.session.add(inv)
    db.session.commit()

    resp = admin_client.post(
        f'/admin/conversations/{conv.id}/invites/{inv.id}/remove')
    assert resp.status_code == 302
    assert db.session.get(ConversationInvite, inv.id) is None


# ── Template-render smoke test (#92 blueprint extraction) ───────────────────────
# The admin routes moved onto Blueprint('admin'), so every `url_for('admin…')` in the
# admin templates was requalified to `url_for('admin.admin…')`. The rest of this suite
# hits admin routes by URL path, which only catches a broken template url_for if that
# template is GET-rendered — and admin_conversation.html (13 url_for calls),
# admin_invites.html, and admin_statements.html are NOT otherwise rendered here. This
# guards them (and future renames) by GET-rendering all three end to end.
def test_admin_template_pages_render(admin_client, conv):
    # Pure-DB pages — no backend needed.
    assert admin_client.get(f'/admin/conversations/{conv.id}').status_code == 200
    assert admin_client.get(f'/admin/conversations/{conv.id}/invites').status_code == 200

    # Statements page pulls from Polis; stub both clients so it renders offline.
    from unittest.mock import MagicMock
    server = MagicMock()
    server.get_statements.return_value = ([], [], [])
    with patch('app._polis_server_client', return_value=server), \
         patch('app.PolisParticipantClient') as ppc:
        ppc.return_value.get_settings.return_value = {}
        resp = admin_client.get(f'/admin/conversations/{conv.id}/statements')
    assert resp.status_code == 200


def test_phases_toggle_mirrors_results_into_polis_vis_type(admin_client, conv):
    """Enabling a results phase must flip Polis `vis_type` on (1); turning both results
    phases off flips it back to 0 — otherwise GET /results/ stays empty regardless of votes."""
    from unittest.mock import MagicMock

    # Enabling a results phase → vis_type = 1
    server = MagicMock()
    with patch('app._polis_server_client', return_value=server):
        r = admin_client.post(f'/admin/conversations/{conv.id}/phases',
                              data={'phase_public_results': 'on'})
    assert r.status_code == 302
    server.set_vis_type.assert_called_once_with('adm1234567', 1)

    # No results phase on → vis_type = 0
    server2 = MagicMock()
    with patch('app._polis_server_client', return_value=server2):
        admin_client.post(f'/admin/conversations/{conv.id}/phases',
                          data={'phase_submission': 'on'})
    server2.set_vis_type.assert_called_once_with('adm1234567', 0)
