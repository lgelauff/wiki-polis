"""Tests for admin conversation management, roles, and phase toggles."""
from unittest.mock import patch

import pytest

from db import AdminRole, Conversation, ConversationInvite, Participant, db
from polis_admin import PolisServerError
from tests.conftest import login


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

def test_create_conversation(app, admin_client):
    app.config.update({
        'POLIS_SERVER_URL': 'http://polis.test',
        'POLIS_ADMIN_EMAIL': 'admin@example.org',
        'POLIS_ADMIN_PASSWORD': 'test-password',
    })
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
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'lowercase letters' in resp.data.lower() or b'invalid slug' in resp.data.lower()


def test_create_conversation_polis_failure_redirects(app, admin_client):
    """Polis server error on creation → redirect to admin with flash, no conv written."""
    app.config.update({
        'POLIS_SERVER_URL': 'http://polis.test',
        'POLIS_ADMIN_EMAIL': 'admin@example.org',
        'POLIS_ADMIN_PASSWORD': 'test-password',
    })
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


# ── Simple-mode phase advance (#140) ──────────────────────────────────────────

from app import PHASE_SEQUENCE, _current_stage_index, _is_linear_phase_state


def _advance(admin_client, conv):
    """POST the advance route with set_vis_type stubbed; return the response."""
    with patch('app.PolisServerClient.set_vis_type'):
        return admin_client.post(f'/admin/conversations/{conv.id}/phase/advance')


def test_advance_from_preparation_opens_submission(admin_client, conv):
    resp = _advance(admin_client, conv)
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_submission is True
    assert conv.phase_personal_results is False
    assert conv.phase_argument_mapping is False
    assert conv.phase_informed_voting is False
    assert conv.phase_public_results is False


def test_advance_is_exclusive_through_full_sequence(admin_client, conv):
    """Each advance turns the next flag on and the prior flag off — one active stage."""
    flags = [s['flag'] for s in PHASE_SEQUENCE]   # [None, submission, ...]
    for i in range(1, len(PHASE_SEQUENCE)):
        _advance(admin_client, conv)
        db.session.refresh(conv)
        # Exactly one phase flag should be on: the i-th stage's flag.
        on = [f for f in flags if f and getattr(conv, f)]
        assert on == [flags[i]], f'stage {i}: expected only {flags[i]} on, got {on}'


def test_advance_at_final_stage_is_noop(admin_client, conv):
    conv.phase_public_results = True   # already at the final stage
    db.session.commit()
    resp = _advance(admin_client, conv)
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_public_results is True
    assert _current_stage_index(conv) == len(PHASE_SEQUENCE) - 1


def test_advance_requires_global_admin(auth_client, conv):
    """A non-global-admin (regular participant / moderator) cannot advance."""
    resp = auth_client.post(f'/admin/conversations/{conv.id}/phase/advance')
    assert resp.status_code == 403
    db.session.refresh(conv)
    assert conv.phase_submission is False


def test_advance_to_informed_voting_does_not_init_phase6(admin_client, conv):
    """Advancing to the informed-voting stage flips the flag but does not create
    a Phase 6 Polis conversation — that stays an explicit separate action."""
    conv.phase_argument_mapping = True   # at stage 4; next advance → informed voting
    db.session.commit()
    _advance(admin_client, conv)
    db.session.refresh(conv)
    assert conv.phase_informed_voting is True
    assert conv.phase_argument_mapping is False
    assert conv.phase6_polis_conversation_id is None


def test_advance_syncs_vis_type(admin_client, conv):
    """vis_type=1 when advancing into a results stage, 0 otherwise."""
    # Preparation → submission: no results phase → vis_type 0.
    with patch('app.PolisServerClient.set_vis_type') as m:
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance')
    m.assert_called_once_with(conv.polis_id, 0)

    # Submission → featured selection (personal results) → vis_type 1.
    with patch('app.PolisServerClient.set_vis_type') as m:
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance')
    m.assert_called_once_with(conv.polis_id, 1)

    # Featured selection → argument mapping → vis_type 0.
    with patch('app.PolisServerClient.set_vis_type') as m:
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance')
    m.assert_called_once_with(conv.polis_id, 0)


def test_current_stage_index_and_linearity():
    c = Conversation(slug='x', polis_id='p', title='t', active=True,
                     access_policy='public')
    assert _current_stage_index(c) == 0          # all off → preparation
    assert _is_linear_phase_state(c) is True
    c.phase_argument_mapping = True
    assert _current_stage_index(c) == 3
    assert _is_linear_phase_state(c) is True
    c.phase_submission = True                     # two flags on → non-linear
    assert _is_linear_phase_state(c) is False
    assert _current_stage_index(c) == 3           # still furthest-along


def test_simple_panel_shows_advance_button(admin_client, conv):
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'Advance to next phase' in resp.data
    assert b'phase-stepper' in resp.data


def test_non_linear_state_suppresses_advance_button(admin_client, conv):
    conv.phase_submission = True
    conv.phase_public_results = True              # non-linear
    db.session.commit()
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'custom state' in resp.data
    assert b'Advance to next phase' not in resp.data


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


def test_scoped_moderator_cannot_see_global_role_controls(client, conv, participant):
    other = Participant(mw_user_id=33333, mw_username='otheruser', xid='t' * 64)
    db.session.add(other)
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='moderator'))
    db.session.commit()
    login(client, 'testuser')

    resp = client.get(f'/admin/conversations/{conv.id}')

    assert resp.status_code == 200
    assert b'testuser' in resp.data
    assert b'otheruser' not in resp.data
    assert b'Add moderator' not in resp.data
    assert b'class="btn-small btn-danger">remove</button>' not in resp.data


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

    # Public results on → vis_type = 1
    server = MagicMock()
    with patch('app._polis_server_client', return_value=server):
        r = admin_client.post(f'/admin/conversations/{conv.id}/phases',
                              data={'phase_public_results': 'on'})
    assert r.status_code == 302
    server.set_vis_type.assert_called_once_with('adm1234567', 1)

    # Personal results ALONE also enables it → vis_type = 1 (guards the `or` arm)
    server_p = MagicMock()
    with patch('app._polis_server_client', return_value=server_p):
        admin_client.post(f'/admin/conversations/{conv.id}/phases',
                          data={'phase_personal_results': 'on'})
    server_p.set_vis_type.assert_called_once_with('adm1234567', 1)

    # No results phase on → vis_type = 0
    server2 = MagicMock()
    with patch('app._polis_server_client', return_value=server2):
        admin_client.post(f'/admin/conversations/{conv.id}/phases',
                          data={'phase_submission': 'on'})
    server2.set_vis_type.assert_called_once_with('adm1234567', 0)
