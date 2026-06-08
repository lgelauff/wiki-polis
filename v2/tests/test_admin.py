"""Tests for admin conversation management, roles, and phase toggles."""
from datetime import datetime, timezone
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


# ── Guided phase transition (#140 + #156) ─────────────────────────────────────

from app import (PHASE_SEQUENCE, PHASE_TRANSITIONS, _current_stage_index,
                 _is_linear_phase_state, _advance_target_index)
from db import FeaturedStatement


def _checks_for(conv):
    """All precondition checkbox ids for the conversation's next transition, ticked."""
    target = _advance_target_index(conv)
    if target is None:
        return {}
    key = PHASE_SEQUENCE[target]['key']
    return {p['id']: 'on' for p in PHASE_TRANSITIONS[key]['preconditions']}


def _add_featured(conv, tid=1, text='A featured statement'):
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=tid,
                           statement_text=text, confirmed_by_admin=True)
    db.session.add(fs)
    db.session.commit()
    return fs


def _move(admin_client, conv, data=None):
    """POST the guided transition with all readiness checks ticked and Polis stubbed."""
    payload = _checks_for(conv) if data is None else data
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6conv1234'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=42):
        return admin_client.post(f'/admin/conversations/{conv.id}/phase/advance', data=payload)


def test_move_from_preparation_opens_submission(admin_client, conv):
    resp = _move(admin_client, conv)
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_submission is True
    assert conv.phase_personal_results is False
    assert conv.phase_public_results is False


def test_move_blocked_without_all_checks(admin_client, conv):
    """Omitting any readiness checkbox blocks the transition (server-side gate)."""
    checks = _checks_for(conv)
    checks.pop(next(iter(checks)))                 # drop one
    resp = _move(admin_client, conv, data=checks)
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_submission is False          # no change


def test_move_is_exclusive_through_full_sequence(admin_client, conv):
    """Each move turns the next flag on and the prior off — one active stage."""
    _add_featured(conv)                            # needed for the machine-checked stages
    flags = [s['flag'] for s in PHASE_SEQUENCE]
    for i in range(1, len(PHASE_SEQUENCE)):
        _move(admin_client, conv)
        db.session.refresh(conv)
        on = [f for f in flags if f and getattr(conv, f)]
        assert on == [flags[i]], f'stage {i}: expected only {flags[i]} on, got {on}'


def test_move_at_final_stage_is_noop(admin_client, conv):
    conv.phase_public_results = True
    db.session.commit()
    resp = _move(admin_client, conv)
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_public_results is True
    assert _current_stage_index(conv) == len(PHASE_SEQUENCE) - 1


def test_move_forbidden_for_regular_participant(auth_client, conv):
    resp = auth_client.post(f'/admin/conversations/{conv.id}/phase/advance')
    assert resp.status_code == 403
    db.session.refresh(conv)
    assert conv.phase_submission is False


def test_move_forbidden_for_moderator(client, conv, participant):
    """Phase control is global-admin only — a moderator cannot move phases."""
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='moderator'))
    db.session.commit()
    login(client, 'testuser')
    resp = client.post(f'/admin/conversations/{conv.id}/phase/advance',
                       data=_checks_for(conv))
    assert resp.status_code == 403
    db.session.refresh(conv)
    assert conv.phase_submission is False


def test_moderator_sees_readonly_stepper(client, conv, participant):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='moderator'))
    db.session.commit()
    login(client, 'testuser')
    resp = client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'phase-stepper' in resp.data           # same interface
    assert b'phase-move-box' not in resp.data       # no guided box
    assert b'disabled' in resp.data                # read-only button
    assert b'Advanced phase controls' not in resp.data
    assert b'phase/advance' not in resp.data        # no actionable form


def test_move_from_non_linear_state_rejected(admin_client, conv):
    conv.phase_submission = True
    conv.phase_argument_mapping = True            # non-linear
    db.session.commit()
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phase/advance')
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_submission is True
    assert conv.phase_argument_mapping is True
    assert conv.phase_informed_voting is False


def test_move_to_argument_mapping_blocked_without_featured(admin_client, conv):
    """A machine-checked precondition (≥1 confirmed featured statement) is enforced
    server-side even when all checkboxes are ticked."""
    conv.phase_personal_results = True            # at featured selection
    db.session.commit()
    resp = _move(admin_client, conv)              # no featured statement exists
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_argument_mapping is False    # blocked
    assert conv.phase_personal_results is True


def test_move_to_informed_voting_runs_phase6_init(admin_client, conv):
    """Moving into Informed voting folds in Phase 6 init: creates the Polis
    conversation and seeds the confirmed featured statements, atomically."""
    conv.phase_argument_mapping = True
    db.session.commit()
    fs = _add_featured(conv)
    _move(admin_client, conv)
    db.session.refresh(conv)
    db.session.refresh(fs)
    assert conv.phase_informed_voting is True
    assert conv.phase_argument_mapping is False
    assert conv.phase6_polis_conversation_id == 'p6conv1234'
    assert fs.phase6_polis_statement_id == 42


def test_move_to_informed_voting_init_failure_rolls_back(admin_client, conv):
    """If Phase 6 seeding fails, the informed-voting flag is NOT set (atomic)."""
    conv.phase_argument_mapping = True
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6conv1234'), \
         patch('app.PolisServerClient.add_seed_return_id',
               side_effect=PolisServerError('seed failed')):
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                          data=_checks_for(conv))
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False     # rolled back
    assert conv.phase_argument_mapping is True     # prior flag preserved
    assert conv.phase6_polis_conversation_id is None


def test_move_to_public_results_auto_closes(admin_client, conv):
    """The final transition opens public results and permanently closes the
    conversation, starting the identity-reveal flow."""
    conv.phase_informed_voting = True
    db.session.commit()
    _move(admin_client, conv)
    db.session.refresh(conv)
    assert conv.phase_public_results is True
    assert conv.active is False
    assert conv.closed_at is not None


def test_move_on_closed_conversation_jumps_to_public_results(admin_client, conv):
    conv.phase_submission = True
    conv.active = False
    conv.closed_at = datetime.now(timezone.utc)
    db.session.commit()
    original_closed = conv.closed_at.replace(tzinfo=None)   # SQLite stores naive
    _move(admin_client, conv)
    db.session.refresh(conv)
    assert conv.phase_public_results is True
    assert conv.phase_submission is False
    assert conv.closed_at.replace(tzinfo=None) == original_closed   # not re-stamped


def test_move_vis_type_failure_flashes(admin_client, conv):
    with patch('app.PolisServerClient.set_vis_type',
               side_effect=PolisServerError('boom')):
        resp = admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                                 data=_checks_for(conv), follow_redirects=True)
    assert resp.status_code == 200
    assert b'results visibility in Polis failed' in resp.data
    db.session.refresh(conv)
    assert conv.phase_submission is True


def test_move_syncs_vis_type(admin_client, conv):
    """vis_type=1 entering a results stage, 0 otherwise."""
    _add_featured(conv)
    expectations = [0, 1, 0, 0, 1]   # submission, featured(personal), argument, informed, public
    for expected in expectations:
        with patch('app.PolisServerClient.set_vis_type') as m, \
             patch('app.PolisServerClient.create_conversation', return_value='p6conv1234'), \
             patch('app.PolisServerClient.add_seed_return_id', return_value=42):
            admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                              data=_checks_for(conv))
        m.assert_called_once_with(conv.polis_id, expected)
        db.session.refresh(conv)


def test_current_stage_index_and_linearity():
    c = Conversation(slug='x', polis_id='p', title='t', active=True,
                     access_policy='public')
    assert _current_stage_index(c) == 0
    assert _is_linear_phase_state(c) is True
    c.phase_argument_mapping = True
    assert _current_stage_index(c) == 3
    assert _is_linear_phase_state(c) is True
    c.phase_submission = True
    assert _is_linear_phase_state(c) is False
    assert _current_stage_index(c) == 3


def test_guided_box_renders_checklist(admin_client, conv):
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'phase-move-box' in resp.data
    assert b'phase-move-check' in resp.data          # checklist present
    assert b'Move on to Submission' in resp.data
    assert b'phase-move-submit' in resp.data
    # Submit ships enabled (no-JS can advance; route enforces server-side); JS
    # disables it until all ticked.
    assert b'submit.disabled' in resp.data           # JS gate present
    assert b'Confirm every item' in resp.data        # disabled-reason hint
    assert b'aria-current="step"' in resp.data       # a11y


def test_guided_box_shows_unmet_machine_check(admin_client, conv):
    """At Featured selection with no featured statement, the featured precondition
    shows as not met."""
    conv.phase_personal_results = True
    db.session.commit()
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'not met' in resp.data


def test_featured_check_shows_selected_count_and_recommendation(admin_client, conv):
    """The featured-statement precondition reports '(N selected, 15 recommended)'."""
    conv.phase_personal_results = True            # next transition → argument mapping
    db.session.commit()
    _add_featured(conv); _add_featured(conv, tid=2)   # 2 confirmed
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'2 selected, 15 recommended' in resp.data


def test_non_linear_state_suppresses_box(admin_client, conv):
    conv.phase_submission = True
    conv.phase_public_results = True
    db.session.commit()
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'custom state' in resp.data
    assert b'phase-move-box' not in resp.data
    assert b'phase/advance' not in resp.data


# ── Guided transition — review follow-ups (#158) ──────────────────────────────

def test_move_rejects_non_on_checkbox_value(admin_client, conv):
    """Only the literal 'on' value satisfies a precondition; '1'/'true' do not."""
    data = {k: '1' for k in _checks_for(conv)}
    resp = _move(admin_client, conv, data=data)
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_submission is False


def test_move_requires_every_checkbox(admin_client, conv):
    """Dropping ANY single precondition blocks — not just the first."""
    all_checks = _checks_for(conv)
    assert len(all_checks) > 1
    for drop in list(all_checks):
        data = {k: v for k, v in all_checks.items() if k != drop}
        resp = _move(admin_client, conv, data=data)
        assert resp.status_code == 302
        db.session.refresh(conv)
        assert conv.phase_submission is False, f'dropping {drop} should block'


def test_informed_voting_newcomers_has_no_machine_check():
    """U6 regression: the 'newcomers' precondition must not carry a machine check —
    its badge would otherwise render against an unrelated label."""
    iv = {p['id']: p for p in PHASE_TRANSITIONS['informed_voting']['preconditions']}
    assert iv['newcomers'].get('check') is None


def test_move_to_informed_voting_blocked_if_already_initialised(admin_client, conv):
    """The guided route refuses to re-init Phase 6 (precheck), without any Polis call."""
    conv.phase_argument_mapping = True
    conv.phase6_polis_conversation_id = 'pre-existing'
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.create_conversation') as cc, \
         patch('app.PolisServerClient.set_vis_type'):
        resp = admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                                 data=_checks_for(conv), follow_redirects=True)
    assert b'already initialised' in resp.data.lower()
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False
    cc.assert_not_called()


def test_move_informed_voting_empty_text_aborts(admin_client, conv):
    """A confirmed featured statement with no cached text aborts Phase 6 init before
    seeding; the phase flag is not set."""
    conv.phase_argument_mapping = True
    db.session.commit()
    _add_featured(conv, text='')
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6x') as cc, \
         patch('app.PolisServerClient.add_seed_return_id', return_value=1) as seed:
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                          data=_checks_for(conv))
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False
    assert conv.phase6_polis_conversation_id is None
    cc.assert_called_once()       # remote conversation was created…
    seed.assert_not_called()      # …but seeding never started (empty text aborts)


def test_move_commit_failure_rolls_back_and_logs_orphan(admin_client, conv, caplog):
    """If the commit loses a UNIQUE race after Phase 6 init, the transition rolls
    back and the orphaned Polis conversation id is logged for cleanup."""
    import logging
    from sqlalchemy.exc import IntegrityError
    conv.phase_argument_mapping = True
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6orphan99'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=42), \
         patch('app.db.session.commit', side_effect=IntegrityError('x', 'y', 'z')), \
         caplog.at_level(logging.ERROR):
        resp = admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                                 data=_checks_for(conv), follow_redirects=True)
    assert b'changed at the same time' in resp.data.lower()
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False     # rolled back
    assert 'p6orphan99' in caplog.text             # orphan logged


# ── Standalone Phase 6 init route (advanced/demo fallback) ────────────────────

def test_phase6_init_success(admin_client, conv):
    conv.phase_informed_voting = True
    db.session.commit()
    fs = _add_featured(conv)
    with patch('app.PolisServerClient.create_conversation', return_value='p6conv1234'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=7):
        resp = admin_client.post(f'/admin/conversations/{conv.id}/phase6/init')
    assert resp.status_code == 302
    db.session.refresh(conv)
    db.session.refresh(fs)
    assert conv.phase6_polis_conversation_id == 'p6conv1234'
    assert fs.phase6_polis_statement_id == 7


def test_phase6_init_requires_informed_voting_enabled(admin_client, conv):
    _add_featured(conv)
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phase6/init',
                             follow_redirects=True)
    assert b'enable the informed voting toggle first' in resp.data.lower()
    db.session.refresh(conv)
    assert conv.phase6_polis_conversation_id is None


def test_phase6_init_blocked_when_already_initialised(admin_client, conv):
    conv.phase_informed_voting = True
    conv.phase6_polis_conversation_id = 'existing123'
    db.session.commit()
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phase6/init',
                             follow_redirects=True)
    assert b'already initialised' in resp.data.lower()


def test_phase6_init_blocked_on_closed_conversation(admin_client, conv):
    conv.phase_informed_voting = True
    conv.active = False
    db.session.commit()
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phase6/init',
                             follow_redirects=True)
    assert b'closed or paused' in resp.data.lower()


def test_phase6_init_no_confirmed_featured(admin_client, conv):
    conv.phase_informed_voting = True
    db.session.commit()
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phase6/init',
                             follow_redirects=True)
    assert b'no confirmed featured statements' in resp.data.lower()


def test_phase6_init_accessible_to_moderator(client, conv, participant):
    """Unlike the guided advance, the standalone init allows conversation moderators."""
    conv.phase_informed_voting = True
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='moderator'))
    db.session.commit()
    _add_featured(conv)
    login(client, 'testuser')
    with patch('app.PolisServerClient.create_conversation', return_value='p6modok'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=9):
        resp = client.post(f'/admin/conversations/{conv.id}/phase6/init')
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase6_polis_conversation_id == 'p6modok'


def test_phase6_init_integrityerror_flashes(admin_client, conv):
    from sqlalchemy.exc import IntegrityError
    conv.phase_informed_voting = True
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.create_conversation', return_value='p6conv1234'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=7), \
         patch('app.db.session.commit', side_effect=IntegrityError('x', 'y', 'z')):
        resp = admin_client.post(f'/admin/conversations/{conv.id}/phase6/init',
                                 follow_redirects=True)
    assert b'already initialised by a concurrent request' in resp.data.lower()


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
