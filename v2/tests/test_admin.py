"""Tests for admin conversation management, roles, and phase toggles.

Ported from the deleted Jinja admin console to the /api/v1 admin surface. Tests
whose assertion is already made — usually more strictly — by one of the
tests/test_admin_*_api.py contract suites were deleted with a comment naming the
covering test, so this file holds only assertions those suites do not make.

Transport contract change throughout: the old form posts redirected 302 with a
flash; the API returns JSON with a typed error code
({"error": {"code", "message", "details"}}) and a 400/403/409/502/503 status.
"""
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from db import AdminRole, ContentFlag, Conversation, ConversationInvite, db
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


def _lifecycle(client, conv):
    """The admin console read model — replaces GET /admin/conversations/<id> HTML."""
    response = client.get(f'/api/v1/admin/conversations/{conv.id}')
    assert response.status_code == 200
    return response.get_json()['data']


def _precondition_ids(client, conv):
    """Every readiness-check id for the conversation's next guided transition.

    Replaces the old form's precondition checkboxes: the client now echoes back
    the ids the server advertised in phase.transition.preconditions.
    """
    transition = _lifecycle(client, conv)['phase']['transition']
    return [] if transition is None else [row['id'] for row in transition['preconditions']]


def _creation_body(**overrides):
    body = {
        'slug': 'new-conv', 'title': 'New Conversation', 'introHtml': '',
        'outroHtml': '', 'accessPolicy': 'public', 'phaseRoute': 'default_7',
        'eligibilityEventId': '', 'eligibilityLabel': '', 'polisId': None,
    }
    body.update(overrides)
    return body


def _settings_body(conv, **overrides):
    body = {
        'title': conv.title, 'introHtml': '', 'outroHtml': '',
        'accessPolicy': conv.access_policy, 'eligibilityEventId': '',
        'eligibilityLabel': '', 'recommendationTier': 'medium',
    }
    body.update(overrides)
    return body


# ── Access control ────────────────────────────────────────────────────────────
# DELETED test_admin_index_requires_admin — GET /admin is now the React shell,
# which answers 200 to anyone; the authorization assertion moved to
# test_admin_catalog_api.py::test_admin_catalog_requires_global_admin.
# DELETED test_admin_index_accessible_to_global_admin — asserted only that the
# SPA shell rendered (vacuously true for any caller, authenticated or not). The
# admin read is covered by
# test_admin_catalog_api.py::test_admin_catalog_is_privacy_safe_and_spa_linked.


# ── Conversation CRUD ─────────────────────────────────────────────────────────

def test_create_conversation(app, admin_client):
    """The managed path stores the polis id the upstream create returned.

    test_admin_catalog_api.py::test_managed_creation_keeps_polis_strict_and_hides_upstream_identifier
    asserts the upstream call and that the id does not leak; this asserts the row
    it produced.
    """
    app.config.update({
        'POLIS_SERVER_URL': 'http://polis.test',
        'POLIS_ADMIN_EMAIL': 'admin@example.org',
        'POLIS_ADMIN_PASSWORD': 'test-password',
    })
    with patch('app.PolisServerClient.create_conversation',
               return_value='newpolis12'):
        resp = admin_client.post('/api/v1/admin/conversations',
                                 json=_creation_body())
    assert resp.status_code == 201
    conv = Conversation.query.filter_by(slug='new-conv').first()
    assert conv is not None
    assert conv.title == 'New Conversation'
    assert conv.polis_id == 'newpolis12'
    assert conv.active is True


def test_create_conversation_stores_selected_phase_route(admin_client):
    resp = admin_client.post('/api/v1/admin/conversations', json=_creation_body(
        slug='short-route', polisId='shr1234567', title='Short Route',
        phaseRoute='short_results',
    ))
    assert resp.status_code == 201
    conv = Conversation.query.filter_by(slug='short-route').first()
    assert conv.phase_route == 'short_results'


def test_create_conversation_invalid_slug_rejected(admin_client):
    """Contract change: the flashed 'lowercase letters' message is now a 400 with
    a typed code (bad_request), raised before any row is written."""
    resp = admin_client.post('/api/v1/admin/conversations', json=_creation_body(
        slug='INVALID SLUG!', polisId='abc1234567', title='Test',
    ))
    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'bad_request'
    assert Conversation.query.filter_by(slug='INVALID SLUG!').first() is None


def test_create_conversation_polis_failure_writes_nothing(app, admin_client):
    """Polis server error on creation → 502 upstream_unavailable, no conv written."""
    app.config.update({
        'POLIS_SERVER_URL': 'http://polis.test',
        'POLIS_ADMIN_EMAIL': 'admin@example.org',
        'POLIS_ADMIN_PASSWORD': 'test-password',
    })
    with patch('app.PolisServerClient.create_conversation',
               side_effect=PolisServerError('test error')):
        resp = admin_client.post('/api/v1/admin/conversations',
                                 json=_creation_body(slug='should-not-exist'))
    assert resp.status_code == 502
    assert resp.get_json()['error']['code'] == 'upstream_unavailable'
    assert Conversation.query.filter_by(slug='should-not-exist').first() is None


# DELETED test_single_seed_surfaces_safe_polis_configuration_error — covered by
# test_admin_statements_api.py::test_single_seed_surfaces_safe_upstream_failure.
# DELETED test_edit_conversation — covered by
# test_admin_settings_api.py::test_organizer_replaces_settings_idempotently.
# DELETED test_organizer_can_edit_conversation_settings — same covering test
# (it drives the settings PUT as a conversation organizer).


def test_edit_conversation_can_switch_to_and_from_demo(admin_client, conv):
    # #293: demo is a genuine (recording) demonstration mode, so an existing
    # conversation may be switched to demo and back (was blocked pre-#293).
    resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/settings',
                            json=_settings_body(conv, accessPolicy='demo'))
    assert resp.status_code == 200
    db.session.refresh(conv)
    assert conv.access_policy == 'demo'

    resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/settings',
                            json=_settings_body(conv, accessPolicy='public'))
    assert resp.status_code == 200
    db.session.refresh(conv)
    assert conv.access_policy == 'public'


def test_edit_conversation_blank_title_rejected(admin_client, conv):
    """A whitespace-only title is a field error and leaves the row untouched
    (contract change: was a flash + redirect, now 400 validation_failed)."""
    resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/settings',
                            json=_settings_body(conv, title='   '))
    assert resp.status_code == 400
    error = resp.get_json()['error']
    assert error['code'] == 'validation_failed'
    assert 'title' in error['details']['fields']
    db.session.refresh(conv)
    assert conv.title == 'Admin Test Conv'          # unchanged


# ── Phase toggles ─────────────────────────────────────────────────────────────
# DELETED test_phase_toggles_on — the desired-state replacement of the advanced
# phase set is covered by
# test_admin_lifecycle_api.py::test_advanced_phase_api_replaces_route_keys_and_is_idempotent.

def test_advanced_phases_persist_and_are_read_back(admin_client, conv):
    """Submit exactly what the advanced control posts, and confirm the change
    persists AND the re-read lifecycle reflects it (the payload counterpart of
    the old 'checked' attributes on the re-rendered checkboxes)."""
    conv.phase_submission = True
    db.session.commit()
    resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phases',
                            json={'activeKeys': ['argument_mapping', 'cleanup']})
    assert resp.status_code == 200
    db.session.refresh(conv)
    assert conv.phase_submission is False          # dropped key → cleared
    assert conv.phase_argument_mapping is True     # sent key → set
    assert conv.phase_cleanup is True
    assert _lifecycle(admin_client, conv)['phase']['activeKeys'] == [
        'argument_mapping', 'cleanup',
    ]


def test_phase_toggles_off(admin_client, conv):
    conv.phase_submission = True
    db.session.commit()
    resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phases',
                            json={'activeKeys': []})
    assert resp.status_code == 200
    db.session.refresh(conv)
    assert conv.phase_submission is False


# ── Guided phase transition (#140 + #156) ─────────────────────────────────────

from app import (PHASE_SEQUENCE, PHASE_TRANSITIONS, _current_stage_index,
                 _is_linear_phase_state, _advance_target_index, _sync_phase6_featured)
from db import FeaturedStatement


def _add_featured(conv, tid=1, text='A featured statement'):
    fs = FeaturedStatement(conversation_id=conv.id, polis_statement_id=tid,
                           statement_text=text, confirmed_by_admin=True)
    db.session.add(fs)
    db.session.commit()
    return fs


def _move(client, conv, ids=None):
    """PUT the guided transition with all readiness checks confirmed, Polis stubbed."""
    payload = _precondition_ids(client, conv) if ids is None else ids
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6conv1234'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=42):
        return client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                          json={'confirmedPreconditionIds': payload})


# DELETED test_move_from_preparation_opens_submission — covered by
# test_admin_lifecycle_api.py::test_phase_advance_api_returns_receipt_and_refreshed_lifecycle.
# DELETED test_move_blocked_without_all_checks — subsumed by
# test_move_requires_every_readiness_check below (drops each id in turn) and by
# test_admin_lifecycle_api.py::test_phase_advance_api_reports_missing_and_machine_blocked_checks.

def test_move_is_exclusive_through_full_sequence(admin_client, conv):
    """Each move turns the next flag on and the prior off — one active stage."""
    _add_featured(conv)                            # needed for the machine-checked stages
    flags = [s['flag'] for s in PHASE_SEQUENCE]
    for i in range(1, len(PHASE_SEQUENCE)):
        assert _move(admin_client, conv).status_code == 200
        db.session.refresh(conv)
        on = [f for f in flags if f and getattr(conv, f)]
        assert on == [flags[i]], f'stage {i}: expected only {flags[i]} on, got {on}'


def test_move_at_final_stage_is_rejected(admin_client, conv):
    """Contract change: the old no-op redirect is now an explicit 409 final_phase."""
    conv.phase_public_results = True
    db.session.commit()
    resp = _move(admin_client, conv)
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'final_phase'
    db.session.refresh(conv)
    assert conv.phase_public_results is True
    assert _current_stage_index(conv) == len(PHASE_SEQUENCE) - 1


# DELETED test_report_phase_distinguishes_pending_publication_from_published —
# the markup it read has a payload counterpart (conversation.publication
# pending/published plus capabilities.publish) asserted by
# test_admin_lifecycle_api.py::test_lifecycle_contract_separates_phase_from_publication.


def test_move_forbidden_for_regular_participant(auth_client, conv):
    resp = auth_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                           json={'confirmedPreconditionIds': []})
    assert resp.status_code == 403
    db.session.refresh(conv)
    assert conv.phase_submission is False


# DELETED test_move_forbidden_for_moderator — covered by
# test_admin_lifecycle_api.py::test_phase_advance_api_requires_organizer.


def test_organizer_can_advance_phase(client, conv, participant):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='organizer'))
    db.session.commit()
    login(client, 'testuser')
    assert _move(client, conv).status_code == 200
    db.session.refresh(conv)
    assert conv.phase_submission is True


def test_organizer_cannot_use_advanced_phase_toggles(client, conv, participant):
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='organizer'))
    db.session.commit()
    login(client, 'testuser')
    resp = client.put(f'/api/v1/admin/conversations/{conv.id}/phases',
                      json={'activeKeys': ['submission']})
    assert resp.status_code == 403
    db.session.refresh(conv)
    assert conv.phase_submission is False


def test_organizer_gets_guided_but_not_advanced_phase_capabilities(
    client, conv, participant,
):
    """Payload counterpart of the old 'organizer sees the guided box but no
    advanced-toggle form' markup assertion."""
    db.session.add(AdminRole(participant_id=participant.id,
                             conversation_id=conv.id, role='organizer'))
    db.session.commit()
    login(client, 'testuser')
    data = _lifecycle(client, conv)
    assert data['operator']['roleLabel'] == 'Organizer'
    assert data['capabilities']['advancePhase'] is True
    assert data['capabilities']['useAdvancedPhases'] is False
    assert data['phase']['transition'] is not None


# DELETED test_moderator_sees_readonly_stepper — the markup counterpart (every
# write capability False for a scoped moderator) is asserted by
# test_admin_lifecycle_api.py::test_scoped_moderator_lifecycle_capabilities_are_read_only.
# DELETED test_moderator_sees_roster_readonly — covered by
# test_admin_roles_api.py::test_scoped_moderator_sees_assignments_but_not_candidate_directory
# (roster visible, manageRoles False) and
# test_admin_settings_api.py::test_moderator_can_read_but_not_change_settings.


def test_move_from_non_linear_state_rejected(admin_client, conv):
    conv.phase_submission = True
    conv.phase_argument_mapping = True            # non-linear
    db.session.commit()
    resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                            json={'confirmedPreconditionIds': []})
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'nonlinear_phase_state'
    db.session.refresh(conv)
    assert conv.phase_submission is True
    assert conv.phase_argument_mapping is True
    assert conv.phase_informed_voting is False


# DELETED test_move_to_argument_mapping_blocked_without_featured — the same
# scenario (at featured selection, no confirmed featured, every check confirmed →
# readiness_blocked) is asserted by
# test_admin_lifecycle_api.py::test_phase_advance_api_reports_missing_and_machine_blocked_checks.


def test_move_to_informed_voting_runs_phase6_init(admin_client, conv):
    """Moving into Informed voting folds in Phase 6 init: creates the Polis
    conversation and seeds the confirmed featured statements, atomically."""
    conv.phase_cleanup = True                     # next move: cleanup → informed vote
    db.session.commit()
    fs = _add_featured(conv)
    assert _move(admin_client, conv).status_code == 200
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
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6conv1234'), \
         patch('app.PolisServerClient.add_seed_return_id',
               side_effect=PolisServerError('seed failed')):
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 502                 # the request really routed…
    assert resp.get_json()['error']['code'] == 'phase_preparation_failed'
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False     # …and rolled back
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
    assert _move(admin_client, conv).status_code == 200
    db.session.refresh(conv)
    assert conv.phase_cleanup is True
    assert conv.phase_argument_mapping is False
    assert conv.phase_informed_voting is False
    assert conv.phase6_polis_conversation_id is None   # not initialised yet


# ── Round 6 re-sync on re-entry (#175) ────────────────────────────────────────
# _sync_phase6_featured is a service-layer function with no HTTP surface of its
# own; these tests were already transport-free and are unchanged.

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
    """End-to-end: a featured statement seeded during the endpoint's re-sync has its
    phase6_polis_statement_id committed and surviving a fresh DB read."""
    conv.phase_cleanup = True
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    _featured(conv, 'NewOne')                      # not yet in round 6 → must be seeded
    round6 = ([], [], [])                          # round 6 currently empty
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=77), \
         patch('app.PolisServerClient.create_conversation'):
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 200
    db.session.expire_all()                        # force a fresh read from the DB
    fs = FeaturedStatement.query.filter_by(conversation_id=conv.id).first()
    assert fs.phase6_polis_statement_id == 77      # the endpoint committed the sync


def test_reentry_resync_failure_rolls_back(admin_client, conv):
    """If the re-sync hits a Polis error, the endpoint rolls back: the phase flag is
    NOT set and no featured mapping is persisted."""
    conv.phase_cleanup = True
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()
    _featured(conv, 'A')                           # de-featured set is empty; A must be added
    round6 = ([], [], [])
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.add_seed_return_id',
               side_effect=PolisServerError('boom')), \
         patch('app.PolisServerClient.create_conversation'):
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 502                 # the request really routed…
    assert resp.get_json()['error']['code'] == 'phase_preparation_failed'
    db.session.expire_all()
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False     # …and did not advance
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
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id'), \
         patch('app.PolisServerClient.create_conversation') as create:
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 200
    create.assert_not_called()                     # no re-init
    db.session.refresh(conv)
    assert conv.phase_informed_voting is True


# ── Auto-resync on featured-set edits during a live Informed vote round ───────
# An admin adding/removing a featured statement while round 6 is already running
# should not depend on someone re-triggering "Move on" — the round must reflect the
# featured set immediately, since participants are voting on it right now.
# The old /featured/confirm and /featured/add forms are now one desired-state
# endpoint distinguished by {"source": "system" | "manual"}.

def _live_phase6_conv(conv):
    conv.phase_informed_voting = True
    conv.phase6_polis_conversation_id = 'r6'
    db.session.commit()


def test_featured_system_select_resyncs_a_live_informed_vote_round(admin_client, conv):
    _live_phase6_conv(conv)
    round6 = ([], [], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=99) as add, \
         patch('app._statement_text_map', return_value={5: 'New one'}):
        resp = admin_client.put(
            f'/api/v1/admin/conversations/{conv.id}/featured-statements/5',
            json={'source': 'system'})
    assert resp.status_code == 200
    add.assert_called_once()
    fs = FeaturedStatement.query.filter_by(conversation_id=conv.id, polis_statement_id=5).first()
    assert fs.phase6_polis_statement_id == 99      # seeded into the live round immediately


def test_featured_manual_select_resyncs_a_live_informed_vote_round(admin_client, conv):
    _live_phase6_conv(conv)
    round6 = ([], [], [])
    with patch('app.PolisServerClient.get_statements', return_value=round6), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=98) as add, \
         patch('app._statement_text_map', return_value={50: 'Admin-typed one'}):
        resp = admin_client.put(
            f'/api/v1/admin/conversations/{conv.id}/featured-statements/50',
            json={'source': 'manual'})
    assert resp.status_code == 200
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
        resp = admin_client.delete(
            f'/api/v1/admin/conversations/{conv.id}/featured-selections/{fs.id}')
    assert resp.status_code == 200
    mod.assert_called_once_with('r6', 7, -1)       # hidden in the live round, not just deleted locally
    assert FeaturedStatement.query.filter_by(id=fs.id).first() is None


def test_featured_select_skips_resync_before_phase6_init(admin_client, conv):
    """Selecting a featured statement before round 6 exists must not touch Polis —
    _sync_phase6_featured assumes an already-initialised round."""
    with patch('app._statement_text_map', return_value={1: 'Pre-init statement'}), \
         patch('app.PolisServerClient.get_statements') as get_stmts, \
         patch('app.PolisServerClient.add_seed_return_id') as add:
        resp = admin_client.put(
            f'/api/v1/admin/conversations/{conv.id}/featured-statements/1',
            json={'source': 'system'})
    assert resp.status_code == 200
    get_stmts.assert_not_called()
    add.assert_not_called()
    fs = FeaturedStatement.query.filter_by(conversation_id=conv.id, polis_statement_id=1).first()
    assert fs is not None and fs.confirmed_by_admin is True


def test_featured_select_resync_failure_rolls_back_the_selection(admin_client, conv):
    """If the live-round resync fails, the featured statement itself must not be
    persisted either — otherwise the admin sees it 'confirmed' but never voteable.

    test_admin_featured_api.py::test_select_rejects_unknown_statement_and_rolls_back_failed_live_sync
    asserts the same rollback with _sync_phase6_featured stubbed out; this drives
    the real sync (a stats-DB read that fails while the DB IS configured).
    """
    _live_phase6_conv(conv)
    admin_client.application.config['POLIS_DATABASE_URL'] = 'postgresql://x/y'
    with patch('app.PolisServerClient.get_statements', return_value=None), \
         patch('app.PolisServerClient.add_seed_return_id') as add, \
         patch('app._statement_text_map', return_value={51: 'Will fail'}):
        resp = admin_client.put(
            f'/api/v1/admin/conversations/{conv.id}/featured-statements/51',
            json={'source': 'manual'})
    assert resp.status_code == 502                 # the request really routed…
    assert resp.get_json()['error']['code'] == 'round_sync_failed'
    add.assert_not_called()
    assert FeaturedStatement.query.filter_by(
        conversation_id=conv.id, polis_statement_id=51).first() is None
    db.session.refresh(conv)
    assert conv.phase6_polis_conversation_id == 'r6'   # unchanged


def test_move_to_public_results_enters_cleanup_window(admin_client, conv):
    """The final guided transition ends informed voting but does not stamp
    closed_at; publication is a separate cleanup-window action."""
    conv.phase_informed_voting = True
    db.session.commit()
    assert _move(admin_client, conv).status_code == 200
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
    resp = _move(admin_client, conv)
    assert resp.status_code == 200
    assert resp.get_json()['data']['transition']['targetKey'] == 'public_results'
    db.session.refresh(conv)
    assert conv.phase_public_results is True
    assert conv.phase_submission is False
    assert conv.closed_at.replace(tzinfo=None) == original_closed   # not re-stamped


# DELETED test_move_vis_type_failure_flashes — covered by
# test_admin_lifecycle_api.py::test_phase_advance_api_reports_a_failed_polis_visibility_sync.


def test_move_syncs_vis_type(admin_client, conv):
    """vis_type=1 entering a results stage, 0 otherwise."""
    _add_featured(conv)
    # explore, featured(personal), arguments, cleanup, informed, report
    expectations = [0, 1, 0, 0, 0, 1]
    for expected in expectations:
        ids = _precondition_ids(admin_client, conv)
        with patch('app.PolisServerClient.set_vis_type') as m, \
             patch('app.PolisServerClient.create_conversation', return_value='p6conv1234'), \
             patch('app.PolisServerClient.add_seed_return_id', return_value=42):
            resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                    json={'confirmedPreconditionIds': ids})
        assert resp.status_code == 200
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


# DELETED test_guided_box_renders_checklist — pure markup; its payload
# counterpart (source/target labels, the six preconditions and their shape) is
# asserted by
# test_admin_lifecycle_api.py::test_lifecycle_contract_exposes_server_evaluated_transition.
# DELETED test_unmet_machine_check_renders_gating_hook — the .phase-check-unmet
# CSS hook is markup; its payload counterpart (met is False) is asserted by
# test_guided_transition_reports_an_unmet_machine_check below.


def test_guided_transition_reports_an_unmet_machine_check(admin_client, conv):
    """At Featured selection with no featured statement, the featured precondition
    is reported not met (and carries no count note)."""
    conv.phase_personal_results = True
    db.session.commit()
    transition = _lifecycle(admin_client, conv)['phase']['transition']
    featured = next(row for row in transition['preconditions']
                    if row['id'] == 'all_featured')
    assert featured['met'] is False


# DELETED test_pause_control_in_phases_block_not_status — asserted the position of
# the pause form within the rendered page (one pause form, before the management
# grid). Layout is the SPA's concern now and has no payload counterpart; the
# pause capability itself is asserted in the lifecycle capability tests.


def test_pause_state_is_reflected_in_the_lifecycle_status(admin_client, conv):
    """Payload counterpart of the old paused/active pause-row copy."""
    conv.phase_personal_results = True
    db.session.commit()
    assert _lifecycle(admin_client, conv)['conversation']['status'] == 'active'
    assert admin_client.put(f'/api/v1/admin/conversations/{conv.id}/pause',
                            json={'paused': True}).status_code == 200
    data = _lifecycle(admin_client, conv)
    assert data['conversation']['status'] == 'paused'
    assert data['capabilities']['pause'] is True


def test_featured_check_reports_selected_count_and_recommendation(admin_client, conv):
    """The featured-statement precondition reports 'N selected, 15 recommended'."""
    conv.phase_personal_results = True            # next transition → argument mapping
    db.session.commit()
    _add_featured(conv); _add_featured(conv, tid=2)   # 2 confirmed
    transition = _lifecycle(admin_client, conv)['phase']['transition']
    assert transition['preconditions'][0]['note'] == '2 selected, 15 recommended'


def test_recommendation_tier_owns_featured_guidance(admin_client, conv):
    conv.phase_personal_results = True
    db.session.commit()
    _add_featured(conv)
    resp = admin_client.put(
        f'/api/v1/admin/conversations/{conv.id}/recommendation-tier',
        json={'tier': 'complex'})
    assert resp.status_code == 200
    transition = _lifecycle(admin_client, conv)['phase']['transition']
    assert transition['preconditions'][0]['note'] == '1 selected, 24 recommended'
    db.session.refresh(conv)
    # Guidance belongs to the tool: only the tier is stored (#278).
    assert conv.recommended_quantities == {'tier': 'complex'}


def test_legacy_recommendation_overrides_are_ignored(admin_client, conv):
    conv.phase_personal_results = True
    conv.recommended_quantities = {
        'tier': 'simple',
        'featured_statements': 999,
    }
    db.session.commit()
    _add_featured(conv)

    transition = _lifecycle(admin_client, conv)['phase']['transition']

    assert transition['preconditions'][0]['note'] == '1 selected, 8 recommended'


def test_organizer_can_select_recommendation_tier(client, conv, participant):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=conv.id,
        role='organizer',
    ))
    db.session.commit()
    login(client, 'testuser')

    response = client.put(
        f'/api/v1/admin/conversations/{conv.id}/recommendation-tier',
        json={'tier': 'simple'},
    )

    assert response.status_code == 200
    db.session.refresh(conv)
    assert conv.recommended_quantities == {'tier': 'simple'}


def test_featured_check_zero_confirmed_suppresses_count(admin_client, conv):
    """With zero confirmed featured the precondition is unmet and suppresses the
    redundant '0 selected, ...' note - _check_confirmed_featured returns note=None."""
    conv.phase_personal_results = True
    db.session.commit()
    transition = _lifecycle(admin_client, conv)['phase']['transition']
    assert transition['preconditions'][0]['met'] is False
    assert transition['preconditions'][0]['note'] is None


def test_non_linear_state_offers_no_guided_transition(admin_client, conv):
    """Payload counterpart of the old 'custom state' box suppression."""
    conv.phase_submission = True
    conv.phase_public_results = True
    db.session.commit()
    phase = _lifecycle(admin_client, conv)['phase']
    assert phase['linear'] is False
    assert phase['transition'] is None
    # Both stage flags are reported active (plus the inferred cleanup_window).
    assert {'public_results', 'submission'} <= set(phase['activeKeys'])


# ── Guided transition — review follow-ups (#158) ──────────────────────────────
# DELETED test_move_rejects_non_on_checkbox_value and
# test_move_rejects_non_on_checkbox_variants — both asserted that only the literal
# form value 'on' satisfies a checkbox. HTML checkbox encoding is gone: the JSON
# contract is a list of precondition ids, and the shape is validated by the
# adapter (confirmedPreconditionIds must be a list of unique non-empty strings).

def test_move_requires_every_readiness_check(admin_client, conv):
    """Dropping ANY single precondition blocks — not just the first — and the 409
    names the ids that are still unconfirmed."""
    all_checks = _precondition_ids(admin_client, conv)
    assert len(all_checks) > 1
    for drop in list(all_checks):
        ids = [i for i in all_checks if i != drop]
        resp = _move(admin_client, conv, ids=ids)
        assert resp.status_code == 409, f'dropping {drop} should block'
        error = resp.get_json()['error']
        assert error['code'] == 'readiness_unconfirmed'
        assert drop in error['details']['preconditionIds']
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
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.create_conversation') as cc, \
         patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.get_statements', return_value=([], [], [])), \
         patch('app.PolisServerClient.moderate'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=99):
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 200
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

    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6round'), \
         patch('app.PolisServerClient.add_seed_return_id', side_effect=fake_seed):
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})

    assert resp.status_code == 200
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
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6x') as cc, \
         patch('app.PolisServerClient.add_seed_return_id', return_value=1) as seed:
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 502
    assert resp.get_json()['error']['code'] == 'phase_preparation_failed'
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
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.create_conversation', return_value='p6y') as cc, \
         patch('app.PolisServerClient.add_seed_return_id', return_value=1) as seed:
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 502
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False
    assert conv.phase6_polis_conversation_id is None
    cc.assert_called_once()
    seed.assert_not_called()


def test_move_polis_create_error_leaves_flags_untouched(admin_client, conv):
    """If create_conversation raises, the phase flag must not be mutated and
    set_vis_type must never be reached — the Polis I/O runs before the flag write."""
    conv.phase_cleanup = True
    db.session.commit()
    _add_featured(conv)
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.set_vis_type') as vis, \
         patch('app.PolisServerClient.create_conversation',
               side_effect=PolisServerError('network error')):
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 502                # the request really routed…
    assert resp.get_json()['error']['code'] == 'phase_preparation_failed'
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False   # flag not set
    assert conv.phase_cleanup is True            # current flag not cleared
    vis.assert_not_called()                      # set_vis_type never reached


def test_move_commit_failure_rolls_back_and_logs_orphan(admin_client, conv, caplog):
    """If the commit loses a UNIQUE race after Phase 6 init, the transition rolls
    back and the orphaned Polis conversation id is logged for cleanup (contract
    change: the flash is now a 409 transition_conflict)."""
    from sqlalchemy.exc import IntegrityError
    conv.phase_cleanup = True                     # next move: cleanup → informed vote
    db.session.commit()
    _add_featured(conv)
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6orphan99'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=42), \
         patch('app.db.session.commit', side_effect=IntegrityError('x', 'y', 'z')), \
         caplog.at_level(logging.ERROR):
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'transition_conflict'
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False     # rolled back
    assert 'p6orphan99' in caplog.text             # orphan logged
    assert 'p6orphan99' not in resp.text           # …but never shown to the operator


def test_move_commit_db_error_rolls_back_and_logs_orphan(admin_client, conv, caplog):
    """A non-IntegrityError commit failure (deadlock/timeout) after Phase 6 init must
    NOT 500 with the orphan unlogged: it rolls back, logs the orphaned Polis
    conversation id, and tells the operator not to blind-retry."""
    from sqlalchemy.exc import OperationalError
    conv.phase_cleanup = True                     # next move: cleanup → informed vote
    db.session.commit()
    _add_featured(conv)
    ids = _precondition_ids(admin_client, conv)
    with patch('app.PolisServerClient.set_vis_type'), \
         patch('app.PolisServerClient.create_conversation', return_value='p6orphanOE'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=42), \
         patch('app.db.session.commit',
               side_effect=OperationalError('stmt', {}, Exception('deadlock'))), \
         caplog.at_level(logging.ERROR):
        resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phase',
                                json={'confirmedPreconditionIds': ids})
    assert resp.status_code == 409                 # graceful, not a 500
    assert resp.get_json()['error']['code'] == 'command_outcome_unknown'
    assert 'Do not retry' in resp.get_json()['error']['message']
    db.session.refresh(conv)
    assert conv.phase_informed_voting is False     # rolled back
    assert conv.phase6_polis_conversation_id is None
    assert 'p6orphanOE' in caplog.text             # orphan logged for cleanup
    assert 'p6orphanOE' not in resp.text


# ── Standalone Phase 6 init route (advanced/demo fallback) ────────────────────
# DELETED test_phase6_init_success — covered by
# test_admin_lifecycle_api.py::test_phase6_initialization_api_returns_refreshed_lifecycle.
# DELETED test_phase6_init_requires_informed_voting_enabled — covered by
# test_admin_lifecycle_api.py::test_phase6_initialization_api_reports_state_and_unknown_outcome
# (phase_disabled).

def test_phase6_init_blocked_when_already_initialised(admin_client, conv):
    conv.phase_informed_voting = True
    conv.phase6_polis_conversation_id = 'existing123'
    db.session.commit()
    resp = admin_client.post(
        f'/api/v1/admin/conversations/{conv.id}/phase6-initialization')
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'already_initialized'


def test_phase6_init_blocked_on_closed_conversation(admin_client, conv):
    conv.phase_informed_voting = True
    conv.active = False
    db.session.commit()
    resp = admin_client.post(
        f'/api/v1/admin/conversations/{conv.id}/phase6-initialization')
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'conversation_inactive'


def test_phase6_init_blocked_on_paused_conversation(admin_client, conv):
    """An active-but-PAUSED conversation must not initialise Phase 6 — and the guard
    must fire before any Polis call (no orphan)."""
    conv.phase_informed_voting = True
    conv.paused = True                             # active stays True
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.create_conversation') as cc:
        resp = admin_client.post(
            f'/api/v1/admin/conversations/{conv.id}/phase6-initialization')
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'conversation_inactive'
    cc.assert_not_called()                         # guard fired before touching Polis
    db.session.refresh(conv)
    assert conv.phase6_polis_conversation_id is None


def test_phase6_init_no_confirmed_featured(admin_client, conv):
    """Nothing to seed → 502 phase_preparation_failed, raised before Polis is touched."""
    conv.phase_informed_voting = True
    db.session.commit()
    with patch('app.PolisServerClient.create_conversation') as cc:
        resp = admin_client.post(
            f'/api/v1/admin/conversations/{conv.id}/phase6-initialization')
    assert resp.status_code == 502
    assert resp.get_json()['error']['code'] == 'phase_preparation_failed'
    cc.assert_not_called()
    db.session.refresh(conv)
    assert conv.phase6_polis_conversation_id is None


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
        resp = client.post(
            f'/api/v1/admin/conversations/{conv.id}/phase6-initialization')
    assert resp.status_code == 201
    db.session.refresh(conv)
    assert conv.phase6_polis_conversation_id == 'p6modok'


def test_phase6_init_integrityerror_reports_conflict(admin_client, conv):
    from sqlalchemy.exc import IntegrityError
    conv.phase_informed_voting = True
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.create_conversation', return_value='p6conv1234'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=7), \
         patch('app.db.session.commit', side_effect=IntegrityError('x', 'y', 'z')):
        resp = admin_client.post(
            f'/api/v1/admin/conversations/{conv.id}/phase6-initialization')
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'initialization_conflict'


def test_phase6_init_sqlalchemy_error_rolls_back_and_logs_orphan(
    admin_client, conv, caplog,
):
    """A non-integrity DB error (deadlock/timeout) after Polis I/O must not 500:
    it rolls back, logs the orphaned Polis conversation id, and returns a typed
    409 command_outcome_unknown without leaking the id."""
    from sqlalchemy.exc import OperationalError
    conv.phase_informed_voting = True
    db.session.commit()
    _add_featured(conv)
    with patch('app.PolisServerClient.create_conversation', return_value='p6orphanSA'), \
         patch('app.PolisServerClient.add_seed_return_id', return_value=7), \
         patch('app.db.session.commit',
               side_effect=OperationalError('stmt', {}, Exception('deadlock'))), \
         caplog.at_level(logging.ERROR):
        resp = admin_client.post(
            f'/api/v1/admin/conversations/{conv.id}/phase6-initialization')
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'command_outcome_unknown'
    assert 'p6orphanSA' in caplog.text
    assert 'p6orphanSA' not in resp.text
    db.session.refresh(conv)
    assert conv.phase6_polis_conversation_id is None   # rolled back


# ── Pause / publication ───────────────────────────────────────────────────────
# DELETED test_pause_conversation and test_unpause_conversation — covered by
# test_admin_lifecycle_api.py::test_pause_api_is_desired_state_and_idempotent.
# DELETED test_close_conversation_sets_closed_at and
# test_publish_final_report_requires_cleanup_checklist — covered by
# test_admin_lifecycle_api.py::test_publication_api_freezes_report_and_returns_published_lifecycle
# and ::test_publication_api_enforces_cleanup_and_readiness. The report-filter
# snapshot they also asserted is kept below with a non-empty exclusion set.
# DELETED test_schedule_active_to_passive_transition — covered by
# test_admin_lifecycle_api.py::test_schedule_api_converges_and_cancels.

def test_publish_final_report_snapshots_phase6_filter(admin_client, conv):
    conv.phase_public_results = True
    conv.phase6_polis_conversation_id = 'p6conv1234'
    conv.paused = True
    db.session.commit()
    confirmed = [
        'cleanup_reviewed_results', 'cleanup_moderated_flagged',
        'cleanup_reviewed_exclusions', 'cleanup_report_intro',
    ]
    with patch('app.PolisServerClient.get_statements',
               return_value=([], [], [{'tid': 42, 'txt': 'hidden'}])):
        resp = admin_client.post(
            f'/api/v1/admin/conversations/{conv.id}/publication',
            json={'confirmedPreconditionIds': confirmed})
    assert resp.status_code == 201
    db.session.refresh(conv)
    assert conv.active is False
    assert conv.paused is False
    assert conv.closed_at is not None
    assert conv.report_filter_snapshot == {'excluded_tids': [42], 'excluded_pids': []}


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


def test_publish_already_published_rejected(admin_client, conv):
    """Contract change: the old bare 400 is now a typed 409 conversation_closed."""
    conv.active = False
    conv.closed_at = datetime.now(timezone.utc)
    db.session.commit()
    resp = admin_client.post(f'/api/v1/admin/conversations/{conv.id}/publication',
                             json={'confirmedPreconditionIds': []})
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'conversation_closed'


def test_pause_closed_conversation_rejected(admin_client, conv):
    conv.active = False
    conv.closed_at = datetime.now(timezone.utc)
    db.session.commit()
    resp = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/pause',
                            json={'paused': True})
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'conversation_closed'
    db.session.refresh(conv)
    assert conv.paused is False


# ── Roles ─────────────────────────────────────────────────────────────────────
# The add/remove role forms became one desired-state PUT
# (/roles/<participant_id> with {"roles": [...]}). Every assertion this file made
# is covered by test_admin_roles_api.py:
#   DELETED test_grant_moderator_role, test_grant_organizer_role, test_remove_role
#     → ::test_role_set_replacement_is_idempotent_and_audits_deltas
#   DELETED test_grant_invalid_role_rejected
#     → ::test_role_replacement_validates_unique_known_roles
#   DELETED test_scoped_moderator_cannot_see_global_role_controls (markup; the
#     payload counterpart is manageRoles False with an empty candidate directory)
#     → ::test_scoped_moderator_sees_assignments_but_not_candidate_directory


# ── Invites ───────────────────────────────────────────────────────────────────
# DELETED test_add_invite and test_add_invite_reports_existing_and_duplicate_input
#   → test_admin_invites_api.py::test_bulk_invitation_put_converges_duplicates_and_returns_roster
# DELETED test_add_invite_reports_batch_save_failure
#   → test_admin_invites_api.py::test_bulk_invitation_put_has_structured_validation_and_save_errors
# DELETED test_remove_invite
#   → test_admin_invites_api.py::test_delete_invitation_is_scoped_and_returns_refreshed_roster

def test_add_invite_keeps_non_conflicting_rows_when_one_insert_loses_race(
        admin_client, conv, monkeypatch):
    """A unique race for X must not roll back unrelated Y/Z additions (#242).

    The invites API test asserts concurrentConflicts == 0 on the happy path; this
    is the only test that drives the conflict arm.
    """
    db.session.add(ConversationInvite(conversation_id=conv.id, mw_username='X'))
    db.session.commit()
    original_scalars = db.session.scalars
    first_read = True

    def stale_existing_snapshot(*args, **kwargs):
        nonlocal first_read
        if first_read:
            first_read = False
            return iter(())  # X was inserted after the command's conceptual snapshot.
        return original_scalars(*args, **kwargs)

    monkeypatch.setattr(db.session, 'scalars', stale_existing_snapshot)
    resp = admin_client.put(
        f'/api/v1/admin/conversations/{conv.id}/invitations',
        json={'usernames': ['X', 'Y', 'Z']},
    )

    assert resp.status_code == 200
    assert resp.get_json()['data']['outcome'] == {
        'added': 2,
        'alreadyPresent': 0,
        'concurrentConflicts': 1,
        'duplicateInputs': 0,
    }
    assert {row.mw_username for row in ConversationInvite.query.all()} == {'X', 'Y', 'Z'}


# ── Participants ──────────────────────────────────────────────────────────────
# DELETED test_participants_page_shows_engagement_metrics — covered by
# test_admin_participants_api.py::test_admin_roster_api_uses_shared_scoped_engagement_projection.
# DELETED test_admin_can_ban_and_unban_participant — covered by
# test_admin_participants_api.py::test_admin_access_command_is_idempotent_and_audits_only_changes.
# DELETED test_public_ban_log_uses_pseudonym_and_hides_reason — the public log is
# no longer a Jinja page; covered by
# test_public_output_api.py::test_public_moderation_log_excludes_ids_and_private_notes.

def test_participants_progress_uses_conversation_scoped_polis_subject(
    app, admin_client, conv, participant,
):
    """The roster must derive the Polis subject per conversation and ask upstream
    for exactly those subjects (the API roster test stubs both without asserting
    the call arguments)."""
    from db import Participation

    app.config['POLIS_DATABASE_URL'] = 'postgres://stats.example/db'
    app.config['PARTICIAPI_SUB_SECRET'] = 'subject-secret'
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conv.id,
        pseudonym='scoped-lion',
    ))
    db.session.commit()
    server = MagicMock()
    server.get_statement_progress_for_participants.return_value = {
        'scoped-subject': {'total': 5, 'voted': 3, 'remaining': 2},
    }

    with (
        patch('app._polis_server_client', return_value=server),
        patch('app._conversation_subject', return_value='scoped-subject') as subject,
    ):
        response = admin_client.get(
            f'/api/v1/admin/conversations/{conv.id}/participants',
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['participants'][0]['statementProgress'] == {
        'total': 5, 'voted': 3, 'remaining': 2,
    }
    subject.assert_called_once_with(participant.xid, conv)
    server.get_statement_progress_for_participants.assert_called_once_with(
        conv.polis_id, ['scoped-subject'],
    )


# ── Console read model ────────────────────────────────────────────────────────
# DELETED test_admin_template_pages_render — the five GETs it made now return the
# React shell (an unconditional 200 for any caller), so it proved nothing. Each
# admin read it was guarding has a contract test of its own:
#   lifecycle    → test_admin_lifecycle_api.py::test_lifecycle_contract_exposes_server_evaluated_transition
#   invitations  → test_admin_invites_api.py::test_admin_invitation_roster_reports_policy_and_sorted_usernames
#   participants → test_admin_participants_api.py::test_admin_roster_api_uses_shared_scoped_engagement_projection
#   flags        → test_admin_moderation_api.py::test_admin_flag_queue_exposes_targets_without_reporter_identity
#   statements   → test_admin_statements_api.py::test_statement_workspace_is_typed_and_privacy_safe
# DELETED test_admin_mode_header_and_participant_manage_shortcut — page chrome
# (admin header badge, breadcrumb, "View as participant") is rendered by the SPA
# from the lifecycle links, which are asserted in
# test_admin_lifecycle_api.py::test_lifecycle_contract_separates_phase_from_publication.

def test_phases_toggle_mirrors_results_into_polis_vis_type(admin_client, conv):
    """Enabling a results phase must flip Polis `vis_type` on (1); turning both results
    phases off flips it back to 0 — otherwise GET /results/ stays empty regardless of votes."""
    # Public results on → vis_type = 1
    with patch('app.PolisServerClient.set_vis_type') as m:
        r = admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phases',
                             json={'activeKeys': ['public_results']})
    assert r.status_code == 200
    m.assert_called_once_with('adm1234567', 1)

    # Personal results ALONE also enables it → vis_type = 1 (guards the `or` arm)
    with patch('app.PolisServerClient.set_vis_type') as m:
        admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phases',
                         json={'activeKeys': ['featured_selection']})
    m.assert_called_once_with('adm1234567', 1)

    # No results phase on → vis_type = 0
    with patch('app.PolisServerClient.set_vis_type') as m:
        admin_client.put(f'/api/v1/admin/conversations/{conv.id}/phases',
                         json={'activeKeys': ['submission']})
    m.assert_called_once_with('adm1234567', 0)


def test_termination_reports_unverifiable_vote_count(admin_client, conv):
    """Payload counterpart of the old disabled 'Delete empty consultation' button:
    an unreadable vote count is its own deletion state, not a zero."""
    server = MagicMock()
    server.get_polis_stats.return_value = None
    server.get_valid_vote_count.return_value = None

    with patch('app._polis_server_client', return_value=server):
        resp = admin_client.get(
            f'/api/v1/admin/conversations/{conv.id}/termination')

    assert resp.status_code == 200
    assert resp.get_json()['data']['deletion'] == {
        'state': 'unavailable',
        'validVoteCount': None,
        'reason': 'Voting data could not be verified.',
    }


# DELETED test_delete_conversation_blocked_when_valid_votes_exist — covered by
# test_admin_termination_api.py::test_delete_api_blocks_votes_and_verification_failure.
# DELETED test_delete_conversation_with_zero_valid_votes — covered by
# test_admin_termination_api.py::test_delete_api_rechecks_then_hides_and_deletes_empty_conversation.
# DELETED test_admin_flag_queue_resolves_statement_flag — covered by
# test_admin_moderation_api.py::test_admin_flag_queue_exposes_targets_without_reporter_identity
# (target text + category label) and ::test_admin_flag_resolution_is_idempotent_and_audited_once.


def test_admin_flag_queue_exposes_a_legacy_other_flag_without_detail(
    admin_client, conv, participant,
):
    """A legacy 'other' flag carries no explanation. The console used to print
    '(no explanation provided)'; the payload counterpart is an explicit null
    detail alongside the resolved category label, so the SPA can say so."""
    flag = ContentFlag(
        conversation_id=conv.id,
        participant_id=participant.id,
        content_type='statement',
        statement_tid=8,
        category='other',
        detail=None,
        status='open',
    )
    db.session.add(flag)
    db.session.commit()

    with patch('app._statement_text_map', return_value={8: 'Legacy statement'}):
        resp = admin_client.get(f'/api/v1/admin/conversations/{conv.id}/flags')

    assert resp.status_code == 200
    row = resp.get_json()['data']['open'][0]
    assert row['category'] == 'other'
    assert row['categoryLabel'] == 'Other'
    assert row['detail'] is None
    assert row['target']['text'] == 'Legacy statement'
