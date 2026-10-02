"""Repro for #309 — admin actions are audited with a NULL actor.

`_is_global_admin()` short-circuits on the env-listed `ADMIN_USERS` branch
(v2/app.py:2229) and returns before `_current_participant()` ever runs, so `g.participant`
is left unset for the whole request. `record_audit()` (v2/app.py:5092) then reads
`g.get('participant')` directly, concludes there is no actor, and labels the row
`detail.actor_kind = 'env_admin'` — even when the env-listed admin has a Participant row
of their own, because they have participated at some point.

The result: an admin action on a conversation is recorded with
`actor_participant_id = NULL`, so the audit trail identifies a person when they vote or
flag and loses them the moment they act as an administrator.

The tests drive a real admin HTTP route with the Flask test client. Only the
environment-supplied `ADMIN_USERS` list is overridden (that is deployment config, not the
code under test), and the upstream Polis client is stubbed at the network boundary, the
way v2/tests/test_audit.py already does.

Known bug: the failing tests are marked xfail(strict=True). When the fix lands they pass,
strict mode turns that into a failure, and the fix removes the marker.
"""

from unittest.mock import patch

import pytest

from db import AuditEvent, Conversation, Participant, db

ENV_ADMIN = 'EnvListedAdmin'


def _env_admin_participant(app):
    """An env-listed superadmin who also has a Participant row (they have participated)."""
    with app.app_context():
        p = Participant(mw_user_id=4711, mw_username=ENV_ADMIN, xid='9' * 64)
        db.session.add(p)
        db.session.commit()
        return p.id


def _login_as(client, username, xid):
    with client.session_transaction() as sess:
        sess['username'] = username
        sess['xid'] = xid
        sess['emailable'] = False


def _seed_one_statement(client, app):
    with app.app_context():
        conv = Conversation(slug='repro309', title='Repro 309', active=True, polis_id='p309')
        db.session.add(conv)
        db.session.commit()
        return conv.id


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='#309: an ADMIN_USERS admin with a Participant row is audited with no actor')
def test_env_listed_admin_action_is_audited_with_their_participant_row(client, app):
    pid = _env_admin_participant(app)
    _login_as(client, ENV_ADMIN, '9' * 64)
    conv_id = _seed_one_statement(client, app)

    with patch('app.ADMIN_USERS', [ENV_ADMIN]), \
            patch('app.PolisServerClient.add_seed'):
        response = client.post(
            f'/api/v1/admin/conversations/{conv_id}/statements',
            json={'text': 'An audited statement.', 'derivedFromId': None},
        )
    assert response.status_code == 201, response.get_data(as_text=True)

    with app.app_context():
        rows = AuditEvent.query.filter_by(operation='statement.seed').all()
        assert len(rows) == 1, f'expected exactly one statement.seed row, got {len(rows)}'
        assert rows[0].actor_participant_id == pid, (
            '#309: an action by an ADMIN_USERS-listed admin who has a Participant row must '
            'record that row id in audit_events.actor_participant_id, so the audit trail '
            'still identifies who acted; the row was written with actor_participant_id='
            f'{rows[0].actor_participant_id!r} and detail={rows[0].detail!r}.'
        )
        assert rows[0].detail.get('actor_kind') != 'env_admin', (
            '#309: once the participant row is found, the row is no longer an '
            f'env_admin-with-no-record; detail={rows[0].detail!r}.'
        )


def test_env_listed_admin_without_participant_row_stays_env_admin(client, app):
    """The other half of the contract, so a fix that always invents an actor fails too."""
    _login_as(client, ENV_ADMIN, 'a' * 64)
    conv_id = _seed_one_statement(client, app)

    with patch('app.ADMIN_USERS', [ENV_ADMIN]), \
            patch('app.PolisServerClient.add_seed'):
        response = client.post(
            f'/api/v1/admin/conversations/{conv_id}/statements',
            json={'text': 'An audited statement.', 'derivedFromId': None},
        )
    assert response.status_code == 201, response.get_data(as_text=True)

    with app.app_context():
        rows = AuditEvent.query.filter_by(operation='statement.seed').all()
        assert len(rows) == 1, f'expected exactly one statement.seed row, got {len(rows)}'
        assert rows[0].actor_participant_id is None, (
            '#309: an ADMIN_USERS-listed admin with genuinely no Participant row must keep a '
            f'NULL actor; got {rows[0].actor_participant_id!r}.'
        )
        assert rows[0].detail.get('actor_kind') == 'env_admin', (
            '#309: that NULL actor must stay explained by actor_kind=env_admin so the two '
            f'cases stay distinguishable; detail={rows[0].detail!r}.'
        )
