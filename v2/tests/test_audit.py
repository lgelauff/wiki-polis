"""Phase 2 audit logging tests (#135).

Covers: record_audit writes a correct append-only row + a correlated log line; real
admin routes produce audit rows; and the load-bearing privacy contract — no statement
text / username / xid ever lands in an audit row.
"""
import logging

from db import AuditEvent, Conversation, Participant, db


def _make_admin(app):
    with app.app_context():
        p = Participant(mw_user_id=99, mw_username='AdminUser', xid='f' * 64, is_global_admin=True)
        db.session.add(p)
        db.session.commit()
        return p.id


def _login(client, app):
    pid = _make_admin(app)
    with client.session_transaction() as s:
        s['xid'] = 'f' * 64
        s['username'] = 'AdminUser'
    return pid


# ── record_audit unit behaviour ─────────────────────────────────────────────

def test_record_audit_writes_row_and_logs(app, caplog):
    from app import record_audit
    with app.test_request_context('/'):
        from flask import g
        g.request_id = 'rid-9'
        with caplog.at_level(logging.INFO):
            record_audit('conversation.close', conv_id=None, target_type='conversation',
                         target_id=7, outcome='ok', note='x')
        rows = AuditEvent.query.all()
    assert len(rows) == 1
    r = rows[0]
    assert r.operation == 'conversation.close'
    assert r.target_type == 'conversation'
    assert r.target_id == '7'                       # coerced to str
    assert r.outcome == 'ok'
    assert r.detail == {'note': 'x'}
    rec = [x for x in caplog.records if x.getMessage().startswith('audit ')]
    assert rec and rec[0].operation == 'conversation.close'
    assert rec[0].request_id == 'rid-9'             # correlated via the Phase-1 factory


def test_audit_row_target_id_none_stays_none(app):
    from app import record_audit
    with app.test_request_context('/'):
        record_audit('phase.set', conv_id=None)
        rows = AuditEvent.query.all()
    assert rows[0].target_id is None


# ── A real admin route produces an audit row ────────────────────────────────

def test_close_route_writes_audit_row(client, app):
    from unittest.mock import patch

    pid = _login(client, app)
    with app.app_context():
        conv = Conversation(slug='auditc', title='Audit C', active=True, polis_id='p1',
                            phase_public_results=True,
                            phase6_polis_conversation_id='p6-private')
        db.session.add(conv)
        db.session.commit()
        conv_id = conv.id
    confirmed = [
        'cleanup_reviewed_results', 'cleanup_moderated_flagged',
        'cleanup_reviewed_exclusions', 'cleanup_report_intro',
    ]
    with patch('app.PolisServerClient.get_statements', return_value=([], [], [])):
        r = client.post(f'/api/v1/admin/conversations/{conv_id}/publication',
                        json={'confirmedPreconditionIds': confirmed})
    assert r.status_code == 201
    with app.app_context():
        rows = AuditEvent.query.filter_by(operation='conversation.close').all()
        assert len(rows) == 1
        assert rows[0].conversation_id == conv_id
        assert rows[0].actor_participant_id == pid     # the acting admin


# ── Privacy contract: no content / PII in audit rows ────────────────────────

def test_audit_rows_carry_no_pii_or_content(client, app):
    """Drive routes whose inputs include statement text / usernames and assert none of
    that ever reaches an audit row — only ids / enums / counts.

    The Polis client is mocked so statement.seed actually reaches its record_audit call
    (otherwise add_seed raises and no row is written — the assertion would be vacuous)."""
    from unittest.mock import patch

    _login(client, app)
    with app.app_context():
        conv = Conversation(slug='auditp', title='Audit P', active=True, polis_id='p2')
        db.session.add(conv)
        # The grant must actually change something, or no audit row is written and
        # the 'global_admin.grant' assertion below would be vacuous.
        db.session.add(Participant(mw_user_id=1234, mw_username='GranteeUser',
                                   xid='e' * 64))
        db.session.commit()
        conv_id = conv.id
    secret_text = 'THE QUICK BROWN FOX statement body'
    with patch('app.PolisServerClient.add_seed', return_value=(7, True)):  # seed path commits a row
        r = client.post(f'/api/v1/admin/conversations/{conv_id}/statements',
                        json={'text': secret_text, 'derivedFromId': None})
        assert r.status_code == 201
    grant = client.post('/api/v1/admin/global-admin-grants',
                        json={'username': 'GranteeUser'})
    assert grant.status_code == 201                        # 201 == actually changed

    with app.app_context():
        ops = {row.operation for row in AuditEvent.query.all()}
        assert 'statement.seed' in ops                     # the seed row WAS written (not vacuous)
        assert 'global_admin.grant' in ops
        for row in AuditEvent.query.all():
            blob = f'{row.target_type} {row.target_id} {row.detail}'
            assert secret_text not in blob                 # statement text never stored
            assert 'AdminUser' not in blob                 # actor username never stored
            assert 'GranteeUser' not in blob               # target username never stored
            assert 'f' * 64 not in blob                    # xid never present


# ── Actor of an ADMIN_USERS admin (#309) ────────────────────────────────────

_CLOSE_CONFIRMED = [
    'cleanup_reviewed_results', 'cleanup_moderated_flagged',
    'cleanup_reviewed_exclusions', 'cleanup_report_intro',
]


def _close_as(client, app, slug):
    """Close a fresh conversation through the admin API; return its audit row."""
    from unittest.mock import patch

    with app.app_context():
        conv = Conversation(slug=slug, title='Audit E', active=True, polis_id='pe',
                            phase_public_results=True,
                            phase6_polis_conversation_id='p6-private-e')
        db.session.add(conv)
        db.session.commit()
        conv_id = conv.id
    with patch('app.PolisServerClient.get_statements', return_value=([], [], [])):
        r = client.post(f'/api/v1/admin/conversations/{conv_id}/publication',
                        json={'confirmedPreconditionIds': _CLOSE_CONFIRMED})
    assert r.status_code == 201
    with app.app_context():
        rows = AuditEvent.query.filter_by(operation='conversation.close',
                                          conversation_id=conv_id).all()
        assert len(rows) == 1
        return rows[0].actor_participant_id, dict(rows[0].detail or {}), \
            f'{rows[0].target_type} {rows[0].target_id} {rows[0].detail}'


def test_env_admin_with_participant_row_is_the_actor(client, app, monkeypatch):
    """An ADMIN_USERS admin who has a Participant row is recorded by that row's id,
    and the row still carries no username or xid."""
    import app as app_module
    monkeypatch.setattr(app_module, 'ADMIN_USERS', ['EnvAdmin'])
    with app.app_context():
        # is_global_admin False: admin rights come only from ADMIN_USERS.
        p = Participant(mw_user_id=77, mw_username='EnvAdmin', xid='a' * 64)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    with client.session_transaction() as s:
        s['xid'] = 'a' * 64
        s['username'] = 'EnvAdmin'

    actor, detail, blob = _close_as(client, app, 'audite1')
    assert actor == pid
    assert 'actor_kind' not in detail
    assert 'EnvAdmin' not in blob                          # username never stored
    assert 'a' * 64 not in blob                            # xid never stored


def test_env_admin_without_participant_row_stays_env_admin(client, app, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, 'ADMIN_USERS', ['EnvAdmin'])
    with client.session_transaction() as s:
        s['username'] = 'EnvAdmin'

    actor, detail, blob = _close_as(client, app, 'audite2')
    assert actor is None
    assert detail.get('actor_kind') == 'env_admin'
    assert 'EnvAdmin' not in blob


def test_record_audit_survives_a_failed_actor_lookup(app, monkeypatch):
    import app as app_module

    def _boom():
        raise RuntimeError('db down')
    monkeypatch.setattr(app_module, '_current_participant', _boom)
    with app.test_request_context('/'):
        from flask import session
        session['username'] = 'EnvAdmin'
        app_module.record_audit('phase.set', conv_id=None)
        row = AuditEvent.query.one()
        assert row.actor_participant_id is None
        assert row.detail == {'actor_kind': 'env_admin'}


def test_a_failed_actor_lookup_keeps_the_callers_pending_change(app, monkeypatch):
    """#309: the lookup runs in a savepoint. Rolling back the whole session on its
    failure threw away a change the caller had made but not yet committed."""
    import app as app_module

    def _boom():
        Participant.query.count()  # the lookup has touched the database before failing
        raise RuntimeError('db down')
    monkeypatch.setattr(app_module, '_current_participant', _boom)
    with app.test_request_context('/'):
        conversation = Conversation(slug='audit-pending', polis_id='auditpend1', title='Before')
        db.session.add(conversation)
        db.session.commit()
        conversation.title = 'After'  # pending, not committed
        app_module.record_audit('phase.set', conv_id=conversation.id)

        db.session.expire_all()
        assert db.session.get(Conversation, conversation.id).title == 'After'
        assert AuditEvent.query.filter_by(operation='phase.set').count() == 1


def test_record_audit_outside_a_request_has_no_actor(app):
    from app import record_audit
    with app.app_context():
        record_audit('phase.set', conv_id=None)
        row = AuditEvent.query.one()
        assert row.actor_participant_id is None
        assert row.detail == {}
