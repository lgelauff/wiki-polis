"""Tests for admin conversation management, roles, and phase toggles."""
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from db import AdminRole, ContentFlag, Conversation, ConversationInvite, Participant, db
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


def test_create_conversation_stores_selected_phase_route(admin_client):
    resp = admin_client.post('/admin/conversations/new', data={
        'slug': 'short-route',
        'polis_id': 'shr1234567',
        'title': 'Short Route',
        'access_policy': 'public',
        'phase_route': 'short_results',
    })
    assert resp.status_code == 302
    conv = Conversation.query.filter_by(slug='short-route').first()
    assert conv.phase_route == 'short_results'


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


def test_edit_conversation_missing_title_flashes(admin_client, conv):
    """Blank title flashes and redirects back (not a bare 400) — matches create (#153)."""
    resp = admin_client.post(f'/admin/conversations/{conv.id}/edit', data={
        'title': '   ',
        'access_policy': 'public',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Title is required' in resp.data
    db.session.refresh(conv)
    assert conv.title == 'Admin Test Conv'          # unchanged


def test_organizer_can_edit_conversation_settings(client, conv, participant):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='organizer'))
    db.session.commit()
    login(client, 'testuser')
    resp = client.post(f'/admin/conversations/{conv.id}/edit', data={
        'title': 'Organizer Updated',
        'access_policy': 'invite_only',
    })
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.title == 'Organizer Updated'
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


def test_advanced_phases_form_persists_end_to_end(admin_client, conv):
    """Render the console, submit exactly what the advanced form posts, and confirm
    the change persists AND the re-rendered advanced checkboxes reflect it."""
    conv.phase_submission = True
    db.session.commit()
    # The advanced form posts only the ticked boxes (here: argument_mapping + cleanup).
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phases',
                             data={'phase_argument_mapping': '1', 'phase_cleanup': '1'},
                             follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(conv)
    assert conv.phase_submission is False          # unticked → cleared
    assert conv.phase_argument_mapping is True     # ticked → set
    assert conv.phase_cleanup is True
    # The re-rendered advanced form reflects the saved state.
    page = admin_client.get(f'/admin/conversations/{conv.id}').data.decode()
    assert re.search(r'name="phase_argument_mapping"[^>]*checked', page)
    assert re.search(r'name="phase_cleanup"[^>]*checked', page)
    assert not re.search(r'name="phase_submission"[^>]*checked', page)


def test_phase_toggles_off(admin_client, conv):
    conv.phase_submission = True
    db.session.commit()
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phases', data={})
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_submission is False


# ── Guided phase transition (#140 + #156) ─────────────────────────────────────

from app import (PHASE_SEQUENCE, PHASE_TRANSITIONS, _current_stage_index,
                 _is_linear_phase_state, _advance_target_index, _sync_phase6_featured)
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
    """Phase control is organizer-or-above — a moderator cannot move phases."""
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='moderator'))
    db.session.commit()
    login(client, 'testuser')
    resp = client.post(f'/admin/conversations/{conv.id}/phase/advance',
                       data=_checks_for(conv))
    assert resp.status_code == 403
    db.session.refresh(conv)
    assert conv.phase_submission is False


def test_organizer_can_advance_phase(client, conv, participant):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='organizer'))
    db.session.commit()
    login(client, 'testuser')
    with patch('app.PolisServerClient.set_vis_type'):
        resp = client.post(f'/admin/conversations/{conv.id}/phase/advance',
                           data=_checks_for(conv))
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.phase_submission is True


def test_organizer_cannot_use_advanced_phase_toggles(client, conv, participant):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='organizer'))
    db.session.commit()
    login(client, 'testuser')
    resp = client.post(f'/admin/conversations/{conv.id}/phases',
                       data={'phase_submission': '1'})
    assert resp.status_code == 403
    db.session.refresh(conv)
    assert conv.phase_submission is False


def test_organizer_sees_guided_not_advanced_phase_controls(client, conv, participant):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='organizer'))
    db.session.commit()
    login(client, 'testuser')
    resp = client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'Organizer' in resp.data
    assert b'phase/advance' in resp.data
    assert f'/admin/conversations/{conv.id}/phases'.encode() not in resp.data


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


def test_moderator_sees_roster_readonly(client, conv, participant):
    """A moderator sees the moderator roster (read-only) but no manage controls
    or settings — the roster must not be hidden behind the admin-only block."""
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='moderator'))
    db.session.commit()
    login(client, 'testuser')
    resp = client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'testuser' in resp.data                  # roster lists the moderator
    # Anchor on rendered buttons: bare labels are shipped to every page's message island.
    assert b'>Add role</button>' not in resp.data    # cannot manage roles
    assert b'>Save settings</button>' not in resp.data  # no settings form
    assert b'roles/' not in resp.data                # no add/remove role actions


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
    conv.phase_cleanup = True                     # next move: cleanup → informed vote
    db.session.commit()
    fs = _add_featured(conv)
    _move(admin_client, conv)
    db.session.refresh(conv)
    db.session.refresh(fs)
    assert conv.phase_informed_voting is True
    assert conv.phase_cleanup is False
    assert conv.phase6_polis_conversation_id == 'p6conv1234'
    assert fs.phase6_polis_statement_id == 42


def test_move_to_informed_voting_init_failure_rolls_back(admin_client, conv):
    """If Phase 6 seeding fails, the informed-voting flag is NOT set (atomic)."""
    conv.phase_cleanup = True                     # next move: cleanup → informed vote
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
    assert conv.phase_cleanup is True              # prior flag preserved
    assert conv.phase6_polis_conversation_id is None


def test_cleanup_phase_sits_between_arguments_and_informed_vote(admin_client, conv):
    """#163: the passive Cleanup phase is inserted between Arguments and Informed vote."""
    keys = [s['key'] for s in PHASE_SEQUENCE]
    assert keys.index('cleanup') == keys.index('argument_mapping') + 1
    assert keys.index('cleanup') == keys.index('informed_voting') - 1


def test_move_arguments_to_cleanup_does_not_init_phase6(admin_client, conv):
    """Moving Arguments → Cleanup flips only the cleanup flag; Phase 6 init happens on
    the next move (Cleanup → Informed vote), not here."""
    conv.phase_argument_mapping = True
    db.session.commit()
    _add_featured(conv)
    _move(admin_client, conv)
    db.session.refresh(conv)
    assert conv.phase_cleanup is True
    assert conv.phase_argument_mapping is False
    assert conv.phase_informed_voting is False
    assert conv.phase6_polis_conversation_id is None   # not initialised yet


# ── Round 6 re-sync on re-entry (#175) ────────────────────────────────────────

def _featured(conv, *texts):
    """Add confirmed featured statements with the given texts; return them."""
    out = []
    for i, t in enumerate(texts, start=1):
        fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=i,
                               statement_text=t, confirmed_by_admin=True)
        db.session.add(fs); out.append(fs)
    db.session.commit()
    return out


def test_resync_abc_to_bcd_adds_d_hides_a_keeps_bc(admin_client, conv):
    """Featured was A,B,C at init; now B,C,D. Re-sync adds D, hides A, keeps B/C —
    votes on B/C/A are never touched (hide ≠ delete)."""
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    b, c, d = _featured(conv, 'B', 'C', 'D')      # current featured set
    round6 = ([], [{'tid': 1, 'txt': 'A'}, {'tid': 2, 'txt': 'B'}, {'tid': 3, 'txt': 'C'}], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate') as mod, \
         patch('app.PolisServerClient.add_seed_return_id', return_value=4) as add:
        ok, msg = _sync_phase6_featured(conv)
    assert ok
    add.assert_called_once_with('r6', 'D')        # D added
    mod.assert_called_once_with('r6', 1, -1)      # A hidden, votes preserved
    db.session.commit()
    assert (b.phase6_polis_statement_id, c.phase6_polis_statement_id) == (2, 3)  # adopted
    assert d.phase6_polis_statement_id == 4


def test_resync_restores_a_refeatured_statement(admin_client, conv):
    """A was removed (hidden in round 6) then re-featured → restore via moderate(+1)."""
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    (a,) = _featured(conv, 'A')
    round6 = ([], [], [{'tid': 9, 'txt': 'A'}])    # A currently hidden in round 6
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate') as mod, \
         patch('app.PolisServerClient.add_seed_return_id') as add:
        ok, msg = _sync_phase6_featured(conv)
    assert ok
    mod.assert_called_once_with('r6', 9, 1)        # restored
    add.assert_not_called()
    db.session.commit()
    assert a.phase6_polis_statement_id == 9


def test_resync_noop_when_unchanged(admin_client, conv):
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    _featured(conv, 'A', 'B')
    round6 = ([], [{'tid': 1, 'txt': 'A'}, {'tid': 2, 'txt': 'B'}], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate') as mod, \
         patch('app.PolisServerClient.add_seed_return_id') as add:
        ok, msg = _sync_phase6_featured(conv)
    assert ok
    mod.assert_not_called()
    add.assert_not_called()


def test_resync_stats_db_unconfigured_adds_new_only_and_warns(admin_client, conv):
    """Stats DB NOT configured → can't read round 6: seed featured statements with no
    local mapping (add side), warn that de-featured statements can't be hidden."""
    admin_client.application.config['POLIS_DATABASE_URL'] = ''   # genuinely unconfigured
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    a, b = _featured(conv, 'A', 'B')
    b.phase6_polis_statement_id = 2               # already mapped; A is not
    db.session.commit()
    with patch('app.PolisServerClient.get_statements', return_value=None), \
         patch('app.PolisServerClient.moderate') as mod, \
         patch('app.PolisServerClient.add_seed_return_id', return_value=7) as add:
        ok, msg = _sync_phase6_featured(conv)
    assert ok
    add.assert_called_once_with('r6', 'A')        # only the unmapped one
    mod.assert_not_called()                        # can't hide without reading round 6
    assert 'check manually' in msg
    db.session.commit()
    assert a.phase6_polis_statement_id == 7


def test_resync_stats_db_read_failure_aborts(admin_client, conv):
    """Stats DB IS configured but the read fails → do NOT guess (double-seed risk):
    return failure so the caller rolls back. Nothing is seeded."""
    admin_client.application.config['POLIS_DATABASE_URL'] = 'postgresql://x/y'  # configured
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    _featured(conv, 'A')
    with patch('app.PolisServerClient.get_statements', return_value=None), \
         patch('app.PolisServerClient.add_seed_return_id') as add, \
         patch('app.PolisServerClient.moderate') as mod:
        ok, msg = _sync_phase6_featured(conv)
    assert ok is False                            # caller will roll back
    add.assert_not_called()                        # no blind seeding
    mod.assert_not_called()
    assert 'try again' in msg


def test_resync_abc_to_bcd_reports_counts(admin_client, conv):
    """The summary message reports the add/restore/hide counts."""
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    _featured(conv, 'B', 'C', 'D')
    round6 = ([], [{'tid': 1, 'txt': 'A'}, {'tid': 2, 'txt': 'B'}, {'tid': 3, 'txt': 'C'}], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=4):
        ok, msg = _sync_phase6_featured(conv)
    assert ok
    assert '1 added' in msg and '1 hidden' in msg


def test_resync_is_idempotent(admin_client, conv):
    """Running the sync twice on an unchanged round 6 makes no second-round calls."""
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    _featured(conv, 'A', 'B')
    round6 = ([], [{'tid': 1, 'txt': 'A'}, {'tid': 2, 'txt': 'B'}], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate') as mod, \
         patch('app.PolisServerClient.add_seed_return_id') as add:
        _sync_phase6_featured(conv); db.session.commit()
        _sync_phase6_featured(conv); db.session.commit()
    add.assert_not_called()
    mod.assert_not_called()


def test_resync_empty_featured_set_hides_everything(admin_client, conv):
    """Re-entry with zero confirmed featured statements hides every live round-6
    statement (nothing added)."""
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()                            # no featured statements
    round6 = ([], [{'tid': 1, 'txt': 'A'}, {'tid': 2, 'txt': 'B'}], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate') as mod, \
         patch('app.PolisServerClient.add_seed_return_id') as add:
        ok, msg = _sync_phase6_featured(conv)
    assert ok
    add.assert_not_called()
    assert sorted(c.args[1] for c in mod.call_args_list) == [1, 2]   # both hidden
    assert all(c.args[2] == -1 for c in mod.call_args_list)


def test_resync_duplicate_featured_text_skips_one_and_warns(admin_client, conv, caplog):
    """Two confirmed featured statements with identical text collapse under the text
    key: one is mapped, the other left unmapped, and a warning is logged (a degenerate
    input — surfaced, not silently corrupting the round)."""
    import logging
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    f1, f2 = _featured(conv, 'Same', 'Same')        # duplicate text
    round6 = ([], [{'tid': 1, 'txt': 'Same'}], [])
    with caplog.at_level(logging.WARNING), \
         patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate') as mod, \
         patch('app.PolisServerClient.add_seed_return_id') as add:
        ok, msg = _sync_phase6_featured(conv); db.session.commit()
    assert ok
    add.assert_not_called(); mod.assert_not_called()
    mapped = [fs.phase6_polis_statement_id for fs in (f1, f2)]
    assert mapped.count(1) == 1 and mapped.count(None) == 1   # exactly one mapped
    assert 'duplicates' in caplog.text


def test_reentry_persists_seeded_tid_through_the_route(admin_client, conv):
    """End-to-end: a featured statement seeded during the route's re-sync has its
    phase6_polis_statement_id committed and surviving a fresh DB read."""
    conv.phase_cleanup = True
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    _featured(conv, 'NewOne')                      # not yet in round 6 → must be seeded
    round6 = ([], [], [])                          # round 6 currently empty
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=77), \
         patch('app.PolisServerClient.create_conversation'):
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                          data=_checks_for(conv))
    db.session.expire_all()                        # force a fresh read from the DB
    fs = FeaturedStatement.query.filter_by(conversation_id=conv.id).first()
    assert fs.phase6_polis_statement_id == 77      # the route committed the sync


def test_reentry_resync_failure_rolls_back(admin_client, conv):
    """If the re-sync hits a Polis error, the route rolls back: the phase flag is NOT
    set and no featured mapping is persisted."""
    conv.phase_cleanup = True
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    _featured(conv, 'A')                           # de-featured set is empty; A must be added
    round6 = ([], [], [])
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.add_seed_return_id',
               side_effect=PolisServerError('boom')), \
         patch('app.PolisServerClient.create_conversation'):
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                          data=_checks_for(conv))
    db.session.expire_all()
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False     # not advanced
    fs = FeaturedStatement.query.filter_by(conversation_id=conv.id).first()
    assert fs.phase6_polis_statement_id is None     # no partial mapping persisted


def test_reentry_resyncs_instead_of_reinitialising(admin_client, conv):
    """The guided Cleanup→Informed-vote move re-syncs an already-initialised round 6
    rather than creating a second Polis conversation."""
    conv.phase_cleanup = True
    conv.phase6_polis_conversation_id = 'r6'       # already initialised
    db.session.commit()
    _featured(conv, 'A')
    round6 = ([], [{'tid': 1, 'txt': 'A'}], [])
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id'), \
         patch('app.PolisServerClient.create_conversation') as create:
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                          data=_checks_for(conv))
    create.assert_not_called()                     # no re-init
    db.session.refresh(conv)
    assert conv.phase_informed_voting is True


# ── Auto-resync on featured-set edits during a live Informed vote round ───────
# An admin adding/removing a featured statement while round 6 is already running
# should not depend on someone re-clicking "Move on" — the round must reflect the
# featured set immediately, since participants are voting on it right now.

def _live_phase6_conv(conv):
    conv.phase_informed_voting = True
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()


def test_featured_confirm_resyncs_a_live_informed_vote_round(admin_client, conv):
    _live_phase6_conv(conv)
    round6 = ([], [], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=99) as add, \
         patch('app._fetch_statement_text', return_value='New one'):
        admin_client.post(f'/admin/conversations/{conv.id}/featured/confirm',
                          data={'tid': '5'})
    add.assert_called_once()
    fs = FeaturedStatement.query.filter_by(conversation_id=conv.id, polis_statement_id=5).first()
    assert fs.phase6_polis_statement_id == 99      # seeded into the live round immediately


def test_featured_add_resyncs_a_live_informed_vote_round(admin_client, conv):
    _live_phase6_conv(conv)
    round6 = ([], [], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=98) as add, \
         patch('app._fetch_statement_text', return_value='Admin-typed one'):
        admin_client.post(f'/admin/conversations/{conv.id}/featured/add',
                          data={'tid': '50'})
    add.assert_called_once()
    fs = FeaturedStatement.query.filter_by(conversation_id=conv.id, polis_statement_id=50).first()
    assert fs.phase6_polis_statement_id == 98


def test_featured_remove_resyncs_a_live_informed_vote_round(admin_client, conv):
    _live_phase6_conv(conv)
    fs = _featured(conv, 'Going away')[0]
    fs.phase6_polis_statement_id = 7
    db.session.commit()
    round6 = ([], [{'tid': 7, 'txt': 'Going away'}], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate') as mod, \
         patch('app.PolisServerClient.add_seed_return_id'):
        admin_client.post(f'/admin/conversations/{conv.id}/featured/{fs.id}/remove')
    mod.assert_called_once_with('r6', 7, -1)       # hidden in the live round, not just deleted locally
    assert FeaturedStatement.query.filter_by(id=fs.id).first() is None


def test_featured_confirm_skips_resync_before_phase6_init(admin_client, conv):
    """Confirming a featured statement before round 6 exists must not touch Polis —
    _sync_phase6_featured assumes an already-initialised round."""
    with patch('app._fetch_statement_text', return_value='Pre-init statement'), \
         patch('app.PolisServerClient.get_statements') as get_stmts, \
         patch('app.PolisServerClient.add_seed_return_id') as add:
        admin_client.post(f'/admin/conversations/{conv.id}/featured/confirm',
                          data={'tid': '1'})
    get_stmts.assert_not_called()
    add.assert_not_called()
    fs = FeaturedStatement.query.filter_by(conversation_id=conv.id, polis_statement_id=1).first()
    assert fs is not None and fs.confirmed_by_admin is True


def test_featured_add_resync_failure_rolls_back_the_add(admin_client, conv):
    """If the live-round resync fails, the featured statement itself must not be
    persisted either — otherwise the admin sees it 'confirmed' but never voteable."""
    _live_phase6_conv(conv)
    with patch('app.PolisServerClient.get_statements', return_value=None), \
         patch('app.PolisServerClient.add_seed_return_id') as add, \
         patch('app._fetch_statement_text', return_value='Will fail'):
        admin_client.application.config['POLIS_DATABASE_URL'] = 'postgresql://x/y'
        admin_client.post(f'/admin/conversations/{conv.id}/featured/add',
                          data={'tid': '51'})
    add.assert_not_called()
    assert FeaturedStatement.query.filter_by(
        conversation_id=conv.id, polis_statement_id=51).first() is None
    assert conv.phase6_polis_conversation_id == 'r6'   # unchanged


def test_move_to_public_results_enters_cleanup_window(admin_client, conv):
    """The final guided transition ends informed voting but does not stamp
    closed_at; publication is a separate cleanup-window action."""
    conv.phase_informed_voting = True
    db.session.commit()
    _move(admin_client, conv)
    db.session.refresh(conv)
    assert conv.phase_public_results is True
    assert conv.phase_informed_voting is False
    assert conv.active is True
    assert conv.closed_at is None


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
    # explore, featured(personal), arguments, cleanup, informed, report
    expectations = [0, 1, 0, 0, 0, 1]
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
    assert b'Move on to Explore' in resp.data        # renamed: Submission → Explore
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


def test_pause_control_in_phases_block_not_status(admin_client, conv):
    """Pause/Resume lives once, in the phase hero (directly under the phase bar)."""
    conv.phase_personal_results = True            # a live, mid-flow phase
    db.session.commit()
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'phase-pause-row' in resp.data
    assert resp.data.count(b'/pause"') == 1                       # one pause form, not duplicated
    assert b'temporarily disables voting without starting' in resp.data   # active copy
    assert b'btn-pause' in resp.data
    # The pause row sits inside the phase hero, before the management grid.
    assert resp.data.index(b'phase-pause-row') < resp.data.index(b'Content &amp; access')


def test_pause_control_paused_state_copy(admin_client, conv):
    conv.phase_personal_results = True
    conv.paused = True
    db.session.commit()
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'identity-reveal clock has' in resp.data       # paused safety copy
    assert b'btn-approve' in resp.data                     # Resume styling
    # Strip the client message island (window.wpMessages ships every UI string to
    # every page) so this checks the visible copy, not the shipped dictionary.
    import re as _re
    body = _re.sub(rb'window\.wpMessages\s*=\s*\{.*?\};', b'', resp.data, flags=_re.S)
    assert b'temporarily disables voting without starting' not in body


def test_featured_check_shows_selected_count_and_recommendation(admin_client, conv):
    """The featured-statement precondition reports '(N selected, 15 recommended)'."""
    conv.phase_personal_results = True            # next transition → argument mapping
    db.session.commit()
    _add_featured(conv); _add_featured(conv, tid=2)   # 2 confirmed
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'2 selected, 15 recommended' in resp.data


def test_recommendation_override_updates_featured_guidance(admin_client, conv):
    conv.phase_personal_results = True
    db.session.commit()
    _add_featured(conv)
    admin_client.post(f'/admin/conversations/{conv.id}/recommendations', data={
        'tier': 'complex',
        'seed_statements': '11',
        'featured_statements': '21',
        'arguments_per_featured': '4',
        'votes_per_statement': '60',
    })
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'1 selected, 21 recommended' in resp.data


def test_featured_check_zero_confirmed_suppresses_count(admin_client, conv):
    """With zero confirmed featured the row shows "not met yet" and suppresses the
    redundant "(0 selected, ...)" note - _check_confirmed_featured returns note=None."""
    conv.phase_personal_results = True
    db.session.commit()
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'not met yet' in resp.data
    assert b'selected, 15 recommended' not in resp.data


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


@pytest.mark.parametrize('bad_value', ['true', ''])
def test_move_rejects_non_on_checkbox_variants(admin_client, conv, bad_value):
    """'true' and '' are not accepted — only the literal 'on' passes."""
    data = {k: bad_value for k in _checks_for(conv)}
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


def test_move_to_informed_voting_proceeds_if_already_initialised(admin_client, conv):
    """If Phase 6 is already initialised, moving to Informed vote PROCEEDS by re-syncing
    round 6 (not re-initialising) — re-init would fail on the UNIQUE constraint."""
    conv.phase_cleanup = True                     # next move: cleanup → informed vote
    conv.phase6_polis_conversation_id = 'pre-existing'
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.create_conversation') as cc, \
         patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.get_statements', return_value=([], [], [])), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=99):
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                          data=_checks_for(conv))
    db.session.refresh(conv)
    assert conv.phase_informed_voting is True                       # advanced
    assert conv.phase_cleanup is False
    assert conv.phase6_polis_conversation_id == 'pre-existing'      # unchanged
    cc.assert_not_called()                                          # no re-init


def test_move_to_informed_voting_seeds_round5_featured_set(admin_client, conv):
    """Moving to Informed vote seeds round 6 with exactly the round-5 CONFIRMED featured
    statements — unconfirmed ones are excluded, so round 6 reflects round 5."""
    conv.phase_cleanup = True
    db.session.commit()
    fs1 = _add_featured(conv, tid=1, text='Featured A')
    fs2 = _add_featured(conv, tid=2, text='Featured B')
    unconf = FeaturedStatement(conversation_id=conv.id, polis_statement_id=3,
                               statement_text='Not confirmed', confirmed_by_admin=False)
    db.session.add(unconf); db.session.commit()

    seeded = {}
    def fake_seed(p6id, text):
        seeded[text] = 100 + len(seeded)
        return seeded[text]
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6round'), \
         patch('app.PolisServerClient.add_seed_return_id', side_effect=fake_seed):
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance', data=_checks_for(conv))

    db.session.refresh(conv); db.session.refresh(fs1)
    db.session.refresh(fs2); db.session.refresh(unconf)
    assert conv.phase6_polis_conversation_id == 'p6round'
    assert set(seeded) == {'Featured A', 'Featured B'}     # exactly the confirmed set
    assert fs1.phase6_polis_statement_id is not None
    assert fs2.phase6_polis_statement_id is not None
    assert unconf.phase6_polis_statement_id is None        # unconfirmed not seeded


def test_move_informed_voting_empty_text_aborts(admin_client, conv):
    """A confirmed featured statement with no cached text aborts Phase 6 init before
    seeding; the phase flag is not set."""
    conv.phase_cleanup = True                     # next move: cleanup → informed vote
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


def test_move_informed_voting_none_text_aborts(admin_client, conv):
    """A statement_text of None (not '') aborts Phase 6 init — same path as empty string."""
    conv.phase_cleanup = True
    db.session.commit()
    _add_featured(conv, text=None)
    with patch('app.PolisServerClient.create_conversation', return_value='p6y') as cc, \
         patch('app.PolisServerClient.add_seed_return_id', return_value=1) as seed:
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                          data=_checks_for(conv))
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False
    assert conv.phase6_polis_conversation_id is None
    cc.assert_called_once()
    seed.assert_not_called()


def test_move_polis_create_error_leaves_flags_untouched(admin_client, conv):
    """If create_conversation raises, the phase flag must not be mutated and
    set_vis_type must never be reached — the Polis I/O runs before the flag write."""
    from app import PolisServerError
    conv.phase_cleanup = True
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.set_vis_type') as vis, \
         patch('app.PolisServerClient.create_conversation',
               side_effect=PolisServerError('network error')):
        admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                          data=_checks_for(conv))
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False   # flag not set
    assert conv.phase_cleanup is True            # current flag not cleared
    vis.assert_not_called()                      # set_vis_type never reached


def test_move_commit_failure_rolls_back_and_logs_orphan(admin_client, conv, caplog):
    """If the commit loses a UNIQUE race after Phase 6 init, the transition rolls
    back and the orphaned Polis conversation id is logged for cleanup."""
    import logging
    from sqlalchemy.exc import IntegrityError
    conv.phase_cleanup = True                     # next move: cleanup → informed vote
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


def test_move_commit_db_error_rolls_back_and_logs_orphan(admin_client, conv, caplog):
    """A non-IntegrityError commit failure (deadlock/timeout) after Phase 6 init must
    NOT 500 with the orphan unlogged: it rolls back, logs the orphaned Polis
    conversation id, and warns the organizer not to blind-retry."""
    import logging
    from sqlalchemy.exc import OperationalError
    conv.phase_cleanup = True                     # next move: cleanup → informed vote
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6orphanOE'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=42), \
         patch('app.db.session.commit',
               side_effect=OperationalError('stmt', {}, Exception('deadlock'))), \
         caplog.at_level(logging.ERROR):
        resp = admin_client.post(f'/admin/conversations/{conv.id}/phase/advance',
                                 data=_checks_for(conv), follow_redirects=True)
    assert resp.status_code == 200                 # graceful, not a 500
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False     # rolled back
    assert conv.phase6_polis_conversation_id is None
    assert 'p6orphanOE' in caplog.text             # orphan logged for cleanup
    assert b'site admin' in resp.data.lower()      # warned against blind retry


def test_unmet_machine_check_renders_gating_hook(admin_client, conv):
    """An unmet machine-checked precondition renders the .phase-check-unmet marker the
    JS uses to keep 'Move on' disabled (so it can't enable-then-server-bounce)."""
    conv.phase_personal_results = True             # → argument mapping next, machine-checked
    db.session.commit()                            # no featured statement ⇒ unmet
    resp = admin_client.get(f'/admin/conversations/{conv.id}')
    assert resp.status_code == 200
    assert b'phase-check-unmet' in resp.data


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


def test_phase6_init_blocked_on_paused_conversation(admin_client, conv):
    """An active-but-PAUSED conversation must not initialise Phase 6 — and the guard
    must fire before any Polis call (no orphan)."""
    conv.phase_informed_voting = True
    conv.paused = True                             # active stays True
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.create_conversation') as cc:
        resp = admin_client.post(f'/admin/conversations/{conv.id}/phase6/init',
                                 follow_redirects=True)
    assert b'closed or paused' in resp.data.lower()
    cc.assert_not_called()                         # guard fired before touching Polis
    db.session.refresh(conv)
    assert conv.phase6_polis_conversation_id is None


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


def test_phase6_init_sqlalchemy_error_flashes_and_logs_orphan(admin_client, conv, caplog):
    """A non-integrity DB error (deadlock/timeout) after Polis I/O must not 500:
    it rolls back, logs the orphaned Polis conversation id, and shows an error flash."""
    import logging
    from sqlalchemy.exc import OperationalError
    conv.phase_informed_voting = True
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.create_conversation', return_value='p6orphanSA'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=7), \
         patch('app.db.session.commit',
               side_effect=OperationalError('stmt', {}, Exception('deadlock'))), \
         caplog.at_level(logging.ERROR):
        resp = admin_client.post(f'/admin/conversations/{conv.id}/phase6/init',
                                 follow_redirects=True)
    assert resp.status_code == 200
    assert b'database error' in resp.data.lower()
    assert 'p6orphanSA' in caplog.text
    db.session.refresh(conv)
    assert conv.phase6_polis_conversation_id is None   # rolled back


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
    assert conv.report_filter_snapshot == {'excluded_tids': [], 'excluded_pids': []}


def test_publish_final_report_requires_cleanup_checklist(admin_client, conv):
    conv.phase_public_results = True
    conv.phase6_polis_conversation_id = 'p6conv1234'
    db.session.commit()

    resp = admin_client.post(f'/admin/conversations/{conv.id}/close',
                             data={'cleanup_reviewed_results': 'on'},
                             follow_redirects=True)
    assert resp.status_code == 200
    assert b'Complete every cleanup checklist' in resp.data
    db.session.refresh(conv)
    assert conv.active is True
    assert conv.closed_at is None


def test_publish_final_report_snapshots_phase6_filter(admin_client, conv):
    conv.phase_public_results = True
    conv.phase6_polis_conversation_id = 'p6conv1234'
    db.session.commit()
    data = {
        'cleanup_reviewed_results': 'on',
        'cleanup_moderated_flagged': 'on',
        'cleanup_reviewed_exclusions': 'on',
        'cleanup_report_intro': 'on',
    }
    with patch('app.PolisServerClient.get_statements',
               return_value=([], [], [{'tid': 42, 'txt': 'hidden'}])):
        resp = admin_client.post(f'/admin/conversations/{conv.id}/close', data=data)
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.active is False
    assert conv.closed_at is not None
    assert conv.report_filter_snapshot == {'excluded_tids': [42], 'excluded_pids': []}


def test_schedule_active_to_passive_transition(admin_client, conv):
    conv.phase_submission = True
    db.session.commit()
    when = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    resp = admin_client.post(f'/admin/conversations/{conv.id}/phase/schedule',
                             data={'scheduled_at': when})
    assert resp.status_code == 302
    db.session.refresh(conv)
    assert conv.scheduled_transition_target == 'featured_selection'
    assert conv.scheduled_transition_at is not None
    assert conv.scheduled_transition_frozen is False


def test_due_schedule_fires_and_clears(app, admin_client, conv):
    import app as app_module
    conv.phase_submission = True
    conv.scheduled_transition_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    conv.scheduled_transition_target = 'featured_selection'
    db.session.commit()

    with patch('app.PolisServerClient.set_vis_type', return_value=True):
        result = app_module._process_due_scheduled_transitions()

    assert result['fired'] == 1
    db.session.refresh(conv)
    assert conv.phase_submission is False
    assert conv.phase_personal_results is True
    assert conv.scheduled_transition_at is None


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


def test_grant_organizer_role(admin_client, admin_participant, conv, participant):
    resp = admin_client.post('/admin/roles/add', data={
        'participant_id': participant.id,
        'conversation_id': conv.id,
        'role': 'organizer',
        'redirect_to': f'/admin/conversations/{conv.id}',
    })
    assert resp.status_code == 302
    role = AdminRole.query.filter_by(
        participant_id=participant.id,
        conversation_id=conv.id,
        role='organizer',
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
    # Anchor on the rendered button, not the bare label: every UI string (incl.
    # "Add role") is shipped to the client message island on every page.
    assert b'>Add role</button>' not in resp.data
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


def test_participants_page_shows_engagement_metrics(app, admin_client, conv, participant):
    from db import Argument, ArgumentVote, Participation

    app.config['POLIS_DATABASE_URL'] = 'postgres://stats.example/db'
    other = Participant(mw_user_id=44444, mw_username='otheruser', xid='u' * 64)
    db.session.add(other)
    db.session.flush()
    part = Participation(
        participant_id=participant.id,
        conversation_id=conv.id,
        pseudonym='test-lion',
        last_engagement=datetime(2026, 6, 23, 12, 30, tzinfo=timezone.utc),
    )
    other_part = Participation(
        participant_id=other.id,
        conversation_id=conv.id,
        pseudonym='other-lion',
    )
    db.session.add_all([part, other_part])
    db.session.flush()
    fs = FeaturedStatement(
        conversation_id=conv.id,
        polis_statement_id=7,
        statement_text='Featured',
        confirmed_by_admin=True,
    )
    db.session.add(fs)
    db.session.flush()
    arg = Argument(featured_statement_id=fs.id, proposer_pseudonym='test-lion',
                   body='Useful because...', side='pro')
    db.session.add(arg)
    db.session.flush()
    db.session.add(ArgumentVote(argument_id=arg.id, participant_id=participant.id))
    db.session.commit()

    server = MagicMock()
    server.get_statement_progress_bulk.return_value = {
        conv.polis_id: {'total': 5, 'voted': 3, 'remaining': 2},
    }
    with patch('app._polis_server_client', return_value=server):
        resp = admin_client.get(f'/admin/conversations/{conv.id}/participants')

    assert resp.status_code == 200
    page = resp.data.decode()
    assert 'testuser' in page
    assert '3 / 5' in page
    assert re.search(r'<td>\s*2\s*</td>', page)
    assert re.search(r'<td>\s*1\s*</td>', page)
    assert '2026-06-23 12:30' in page


def test_admin_can_ban_and_unban_participant(admin_client, conv, participant):
    from db import ConversationBan, Participation

    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conv.id,
        pseudonym='ban-lion',
    ))
    db.session.commit()

    ban_resp = admin_client.post(
        f'/admin/conversations/{conv.id}/participants/{participant.id}/ban',
        data={'summary': '<b>spam</b>'},
        follow_redirects=True,
    )
    ban = ConversationBan.query.filter_by(
        conversation_id=conv.id,
        participant_id=participant.id,
        lifted_at=None,
    ).first()
    assert ban_resp.status_code == 200
    assert ban is not None
    assert ban.summary == 'spam'
    assert b'Banned' in ban_resp.data

    unban_resp = admin_client.post(
        f'/admin/conversations/{conv.id}/participants/{participant.id}/unban',
        data={'summary': 'resolved'},
        follow_redirects=True,
    )
    db.session.refresh(ban)
    assert unban_resp.status_code == 200
    assert ban.lifted_at is not None
    assert ban.lift_summary == 'resolved'


def test_public_ban_log_uses_pseudonym_and_hides_reason(client, admin_client,
                                                        conv, participant):
    from db import Participation

    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conv.id,
        pseudonym='public-lion',
    ))
    db.session.commit()

    admin_client.post(
        f'/admin/conversations/{conv.id}/participants/{participant.id}/ban',
        data={'summary': 'private reason'},
    )

    resp = client.get(f'/c/{conv.slug}/moderation-log')
    assert resp.status_code == 200
    page = resp.data.decode()
    assert 'Banned' in page
    assert 'public-lion' in page
    assert 'private reason' not in page
    assert participant.mw_username not in page


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
    assert admin_client.get(f'/admin/conversations/{conv.id}/participants').status_code == 200
    assert admin_client.get(f'/admin/conversations/{conv.id}/flags').status_code == 200

    # Statements page pulls from Polis; stub both clients so it renders offline.
    from unittest.mock import MagicMock
    server = MagicMock()
    server.get_statements.return_value = ([], [], [])
    with patch('app._polis_server_client', return_value=server), \
         patch('app.PolisParticipantClient') as ppc:
        ppc.return_value.get_settings.return_value = {}
        resp = admin_client.get(f'/admin/conversations/{conv.id}/statements')
    assert resp.status_code == 200


def test_admin_mode_header_and_participant_manage_shortcut(admin_client, conv, admin_participant):
    from db import Participation

    db.session.add(Participation(
        participant_id=admin_participant.id,
        conversation_id=conv.id,
        pseudonym='admin-mode',
    ))
    db.session.commit()

    admin_page = admin_client.get(f'/admin/conversations/{conv.id}').data.decode()
    assert 'site-header--admin' in admin_page
    assert '<span class="header-mode-badge">Admin</span>' in admin_page
    assert 'aria-label="Admin breadcrumb"' in admin_page
    assert 'View as participant' in admin_page

    participant_page = admin_client.get(f'/c/{conv.slug}').data.decode()
    assert 'site-header--participant' in participant_page
    assert 'header-mode-badge' not in participant_page
    assert f'href="/admin/conversations/{conv.id}">Manage</a>' in participant_page


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


def test_delete_conversation_button_disabled_without_vote_count(admin_client, conv):
    server = MagicMock()
    server.get_polis_stats.return_value = None
    server.get_valid_vote_count.return_value = None

    with patch('app._polis_server_client', return_value=server):
        page = admin_client.get(f'/admin/conversations/{conv.id}').data.decode()

    assert 'Delete empty consultation' in page
    assert 'Polis vote data could not be verified' in page
    assert 'disabled aria-disabled="true"' in page


def test_delete_conversation_blocked_when_valid_votes_exist(admin_client, conv):
    server = MagicMock()
    server.get_valid_vote_count.return_value = 2

    with patch('app._polis_server_client', return_value=server):
        resp = admin_client.post(
            f'/admin/conversations/{conv.id}/delete',
            follow_redirects=True,
        )

    assert resp.status_code == 200
    assert db.session.get(Conversation, conv.id) is not None
    server.close_and_hide_conversation.assert_not_called()
    assert b'2 valid votes' in resp.data


def test_delete_conversation_with_zero_valid_votes(admin_client, conv):
    server = MagicMock()
    server.get_valid_vote_count.return_value = 0

    with patch('app._polis_server_client', return_value=server):
        resp = admin_client.post(f'/admin/conversations/{conv.id}/delete')

    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/admin')
    assert db.session.get(Conversation, conv.id) is None
    server.close_and_hide_conversation.assert_called_once_with('adm1234567')


def test_admin_flag_queue_resolves_statement_flag(admin_client, conv, participant):
    flag = ContentFlag(
        conversation_id=conv.id,
        participant_id=participant.id,
        content_type='statement',
        statement_tid=7,
        category='privacy',
        detail='Names a private person.',
        status='open',
    )
    db.session.add(flag)
    db.session.commit()

    with patch('app._statement_text_map', return_value={7: 'Statement text'}):
        page = admin_client.get(f'/admin/conversations/{conv.id}/flags').data.decode()
    assert 'Statement text' in page
    assert 'Privacy violation' in page

    resp = admin_client.post(
        f'/admin/conversations/{conv.id}/flags/{flag.id}/resolve',
        data={'resolution_note': 'handled'},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(flag)
    assert flag.status == 'resolved'
    assert flag.resolution_note == 'handled'
