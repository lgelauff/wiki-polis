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
    pid = _login(client, app)
    with app.app_context():
        conv = Conversation(slug='auditc', title='Audit C', active=True, polis_id='p1')
        db.session.add(conv)
        db.session.commit()
        conv_id = conv.id
    r = client.post(f'/admin/conversations/{conv_id}/close')
    assert r.status_code in (302, 303)
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
        db.session.commit()
        conv_id = conv.id
    secret_text = 'THE QUICK BROWN FOX statement body'
    with patch('app.PolisServerClient.add_seed'):          # seed path now commits a row
        r = client.post(f'/admin/conversations/{conv_id}/statements/seed',
                        data={'txt': secret_text})
        assert r.status_code in (302, 303)
    client.post('/admin/global-admins/add', data={'mw_username': 'AdminUser'})

    with app.app_context():
        ops = {row.operation for row in AuditEvent.query.all()}
        assert 'statement.seed' in ops                     # the seed row WAS written (not vacuous)
        assert 'global_admin.grant' in ops
        for row in AuditEvent.query.all():
            blob = f'{row.target_type} {row.target_id} {row.detail}'
            assert secret_text not in blob                 # statement text never stored
            assert 'AdminUser' not in blob                 # username never stored
            assert 'f' * 64 not in blob                    # xid never present
