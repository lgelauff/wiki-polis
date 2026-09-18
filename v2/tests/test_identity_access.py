"""Identity and rate-limit invariants for voucher accounts (#368, #411)."""

import hashlib
import hmac
import importlib.util
import logging
import os
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import _ratelimit_identity_key
from db import ACCOUNT_KIND_VOUCHER, ACCOUNT_KIND_WIKIMEDIA, Participant, db
from logging_setup import _redact
from services.identity import (
    create_voucher_participant,
    reconcile_participant_login,
)


def test_voucher_participant_is_new_conversation_scoped_identity(app, conversation):
    participant = create_voucher_participant(
        conversation_id=conversation.id,
        xid='v' * 64,
    )

    assert participant.account_kind == ACCOUNT_KIND_VOUCHER
    assert participant.mw_user_id is None
    assert participant.mw_username is None
    assert participant.conversation_id == conversation.id

    db.session.add(participant)
    db.session.commit()
    stored = db.session.get(Participant, participant.id)
    assert stored.account_kind == ACCOUNT_KIND_VOUCHER
    assert stored.conversation_id == conversation.id
    assert stored.conversation is conversation


def test_wikimedia_reconciliation_keeps_existing_xid(app):
    existing = Participant(
        mw_user_id=1001,
        mw_username='old-name',
        account_kind=ACCOUNT_KIND_WIKIMEDIA,
        xid='o' * 64,
    )
    db.session.add(existing)
    db.session.commit()

    result = reconcile_participant_login(
        existing,
        mw_user_id=1001,
        mw_username='new-name',
        new_xid='n' * 64,
        xid_key_version=2,
    )

    assert result is existing
    assert result.mw_username == 'new-name'
    assert result.xid == 'o' * 64


def test_toolforge_limiter_uses_account_not_forwarded_address(app):
    secret = 's' * 32
    app.config['RATELIMIT_IDENTITY_SECRET'] = secret
    with patch.dict(os.environ, {
        'TOOL_TOOLFORGE_API_URL': 'https://toolforge.example.test',
        'TOOL_NAME': 'wiki-polis',
    }, clear=False):
        with app.test_request_context('/', headers={
            'X-Forwarded-For': '203.0.113.10',
        }, environ_base={'REMOTE_ADDR': '192.0.2.10'}):
            from flask import session

            session['xid'] = 'account-xid'
            first = _ratelimit_identity_key()

        with app.test_request_context('/', headers={
            'X-Forwarded-For': '198.51.100.20',
        }, environ_base={'REMOTE_ADDR': '192.0.2.10'}):
            session['xid'] = 'account-xid'
            second = _ratelimit_identity_key()

    expected = 'account:' + hmac.new(
        secret.encode('utf-8'),
        b'xid:account-xid',
        hashlib.sha256,
    ).hexdigest()
    assert first == second == expected
    assert '203.0.113.10' not in first
    assert '198.51.100.20' not in second


def test_toolforge_limiter_separates_anonymous_sessions(app):
    app.config['RATELIMIT_IDENTITY_SECRET'] = 's' * 32
    with patch.dict(os.environ, {
        'TOOL_TOOLFORGE_API_URL': 'https://toolforge.example.test',
        'TOOL_NAME': 'wiki-polis',
    }, clear=False):
        with app.test_request_context('/'):
            from flask import session

            session['_ratelimit_session_id'] = 'browser-a'
            first = _ratelimit_identity_key()
        with app.test_request_context('/'):
            session['_ratelimit_session_id'] = 'browser-b'
            second = _ratelimit_identity_key()

    assert first.startswith('session:')
    assert second.startswith('session:')
    assert first != second


def test_temporary_toolforge_probe_never_logs_raw_addresses(app, caplog):
    app.config['RATELIMIT_IDENTITY_SECRET'] = 's' * 32
    with patch.dict(os.environ, {
        'TOOL_TOOLFORGE_API_URL': 'https://toolforge.example.test',
        'TOOL_NAME': 'wiki-polis-dev',
    }, clear=False):
        with app.test_request_context('/', headers={
            'X-Forwarded-For': '203.0.113.10, 172.16.0.4',
        }, environ_base={'REMOTE_ADDR': '192.0.2.10'}):
            with caplog.at_level(logging.INFO):
                _ratelimit_identity_key()

    assert 'TEMPORARY ratelimit proxy probe' in caplog.text
    assert '203.0.113.10' not in caplog.text
    assert '172.16.0.4' not in caplog.text
    assert '192.0.2.10' not in caplog.text


def test_voucher_path_redaction_covers_the_credential():
    code = '0123456789AB'
    redacted = _redact(f'GET /v/{code}?next=/c/demo')

    assert code not in redacted
    assert '/v/[redacted]?next=/c/demo' in redacted


def test_voucher_paths_use_a_no_referrer_policy(client):
    response = client.get('/v/0123456789AB')

    assert response.headers['Referrer-Policy'] == 'no-referrer'


def test_identity_migration_keeps_existing_wikimedia_rows_and_adds_scope():
    migration_path = (
        Path(__file__).parents[1]
        / 'migrations'
        / 'versions'
        / '6a7090c4c5d7_add_participant_account_kind_and_.py'
    )
    spec = importlib.util.spec_from_file_location('identity_migration', migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('conversations', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table(
        'participants', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('mw_user_id', sa.Integer, nullable=False, unique=True),
        sa.Column('mw_username', sa.String(255), nullable=False),
        sa.Column('xid', sa.String(64), nullable=False, unique=True),
        sa.Column('xid_key_version', sa.Integer, nullable=False, server_default='2'),
        sa.Column('is_demo', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('is_global_admin', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        inspector = sa.inspect(connection)
        columns = {
            column['name']: column
            for column in inspector.get_columns('participants')
        }
        assert columns['mw_user_id']['nullable'] is True
        assert columns['mw_username']['nullable'] is True
        assert columns['account_kind']['nullable'] is False
        assert columns['conversation_id']['nullable'] is True
        foreign_keys = inspector.get_foreign_keys('participants')
        assert any(
            foreign_key['referred_table'] == 'conversations'
            and foreign_key['constrained_columns'] == ['conversation_id']
            for foreign_key in foreign_keys
        )
