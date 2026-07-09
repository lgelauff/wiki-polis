"""Phase 1 logging foundation tests (Plan 1).

Covers the review's must-prove items: loggers aren't disabled, request_id +
participant_id ride records without a DB query, X-Request-Id is minted/validated,
redaction scrubs secrets, the startup fingerprint exposes only a scheme, and the
completion line skips successful static hits.
"""
import json
import logging
import re

import pytest
from flask import Flask

from logging_setup import (RedactingJsonFormatter, RedactingLokiQueueHandler,
                           _HANDLER_NAME, _LOKI_HANDLER_NAME, _redact,
                           configure_logging)


# ── Redaction (minimal Phase-1 filter) ──────────────────────────────────────

def test_redact_db_url_password():
    out = _redact('mysql+pymysql://user:supersecret@host/db')
    assert 'supersecret' not in out
    assert '***' in out


def test_redact_xid_sha256():
    xid = 'a' * 64
    assert xid not in _redact(f'participant xid={xid}')


def test_redact_sensitive_kv():
    for line in ('token=abc123secretvalue', 'password: hunter2hunter2', 'Authorization: Bearer xyz789abc'):
        out = _redact(line)
        assert 'abc123secretvalue' not in out
        assert 'hunter2hunter2' not in out
        assert 'xyz789abc' not in out


# ── JSON formatter shape + redaction (mirrors the prod line) ─────────────────

def test_json_formatter_shape_and_redaction():
    rec = logging.LogRecord('x', logging.INFO, __file__, 1,
                            'connect mysql://u:pw@h/db', None, None)
    rec.request_id = 'abc'
    rec.participant_id = None
    out = RedactingJsonFormatter().format(rec)
    data = json.loads(out)
    assert data['service'] == 'wiki-polis'
    assert data['request_id'] == 'abc'
    assert 'participant_id' not in data           # omitted when None
    assert 'pw' not in out                         # password scrubbed inside JSON


def test_startup_fingerprint_logs_scheme_not_secrets(tmp_path, caplog):
    # Drive the real create_app fingerprint and assert it logs the DB scheme but no secret.
    import os
    from unittest.mock import patch

    from cachelib.file import FileSystemCache

    from app import create_app

    session_dir = tmp_path / 'sessions'
    session_dir.mkdir()
    env = {'FLASK_DEBUG': '0', 'DEV_LOGIN_USER': '', 'RATELIMIT_STORAGE_URI': '',
           'RATELIMIT_KEY_PREFIX': '', 'RATELIMIT_IDENTITY_SECRET': '', 'TRUST_PROXY_HEADERS': '',
           'TOOL_TOOLFORGE_API_URL': '', 'TOOL_REDIS_URI': ''}
    with caplog.at_level(logging.INFO):
        with patch.dict(os.environ, env, clear=False):
            create_app({
                'TESTING': True,
                'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/t.db',
                'WTF_CSRF_ENABLED': False, 'RATELIMIT_ENABLED': False,
                'SECRET_KEY': 'super-secret-key', 'SESSION_TYPE': 'cachelib',
                'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
                'SESSION_PERMANENT': False,
            })
    startup = [r for r in caplog.records if r.getMessage().startswith('startup ')]
    assert startup, 'expected a startup fingerprint log record'
    msg = startup[0].getMessage()
    assert 'db=sqlite' in msg                 # scheme only
    assert 'super-secret-key' not in msg      # no SECRET_KEY in the line


# ── configure_logging idempotency (non-testing app) ─────────────────────────

def test_configure_logging_idempotent():
    a = Flask('idem-test')          # .testing is False → installs the stderr handler
    root = logging.getLogger()
    try:
        configure_logging(a, on_toolforge=True)
        configure_logging(a, on_toolforge=True)
        ours = [h for h in root.handlers if getattr(h, 'name', None) == _HANDLER_NAME]
        assert len(ours) == 1
    finally:
        for h in [h for h in root.handlers if getattr(h, 'name', None) == _HANDLER_NAME]:
            root.removeHandler(h)


def test_loki_handler_posts_redacted_json_line():
    rec = logging.LogRecord('x', logging.INFO, __file__, 1,
                            'token=%s', ('secret-token-value',), None)
    rec.request_id = 'rid'
    rec.participant_id = None
    handler = RedactingLokiQueueHandler(
        'https://logs.example.test',
        {'service': 'wiki-polis', 'env': 'test'},
        auth=('user', 'pass'),
        timeout=0.1,
    )
    handler.setFormatter(RedactingJsonFormatter())
    try:
        from unittest.mock import patch

        with patch('logging_setup.requests.post') as post:
            post.return_value.raise_for_status.return_value = None
            handler._post_record(rec)
    finally:
        handler.close()

    assert post.call_args.args[0] == 'https://logs.example.test/loki/api/v1/push'
    assert post.call_args.kwargs['auth'] == ('user', 'pass')
    payload = post.call_args.kwargs['json']
    stream = payload['streams'][0]
    assert stream['stream'] == {'service': 'wiki-polis', 'env': 'test'}
    line = stream['values'][0][1]
    assert 'secret-token-value' not in line
    assert json.loads(line)['service'] == 'wiki-polis'


def test_configure_logging_installs_one_loki_handler():
    a = Flask('loki-test')
    a.config.update({
        'LOKI_URL': 'https://logs.example.test/loki/api/v1/push',
        'LOKI_LABELS': 'stack=toolforge,request_id=ignored',
    })
    root = logging.getLogger()
    try:
        configure_logging(a, on_toolforge=True)
        configure_logging(a, on_toolforge=True)
        handlers = [h for h in root.handlers if getattr(h, 'name', None) == _LOKI_HANDLER_NAME]
        assert len(handlers) == 1
        assert isinstance(handlers[0].formatter, RedactingJsonFormatter)
        assert handlers[0].labels['service'] == 'wiki-polis'
        assert handlers[0].labels['stack'] == 'toolforge'
        assert 'request_id' not in handlers[0].labels
    finally:
        for h in [h for h in root.handlers
                  if getattr(h, 'name', None) in (_HANDLER_NAME, _LOKI_HANDLER_NAME)]:
            root.removeHandler(h)
            h.close()


# ── Behaviour through a real request (app/client fixtures) ───────────────────

def test_polis_admin_logger_not_disabled(app):
    # We configure imperatively (no dictConfig), so existing loggers are never disabled.
    assert logging.getLogger('polis_admin').disabled is False


def test_request_id_minted_and_returned(client):
    r = client.get('/')
    rid = r.headers.get('X-Request-Id')
    assert rid and re.match(r'^[A-Za-z0-9_-]{1,64}$', rid)


def test_inbound_request_id_ignored_without_trusted_proxy(client):
    r = client.get('/', headers={'X-Request-Id': 'attacker-supplied'})
    assert r.headers['X-Request-Id'] != 'attacker-supplied'   # minted instead


def test_inbound_request_id_reused_when_trusted_and_valid(app):
    app.config['TRUST_PROXY_HEADERS'] = True
    r = app.test_client().get('/', headers={'X-Request-Id': 'valid_id-123'})
    assert r.headers['X-Request-Id'] == 'valid_id-123'


def test_inbound_request_id_rejected_when_malformed(app):
    app.config['TRUST_PROXY_HEADERS'] = True
    c = app.test_client()
    for bad in ('has spaces', 'y' * 65):               # fail the strict pattern
        r = c.get('/', headers={'X-Request-Id': bad})
        assert r.headers['X-Request-Id'] != bad


def test_participant_id_rides_record_when_resolved(app, caplog):
    # Proves the factory stamps participant_id from g.participant (not inert), no query.
    from flask import g

    class _P:
        id = 4242

    with app.test_request_context('/'):
        g.request_id = 'rid-xyz'
        g.participant = _P()
        with caplog.at_level(logging.INFO):
            logging.getLogger('test').info('hello')
    rec = [r for r in caplog.records if r.getMessage() == 'hello'][0]
    assert rec.participant_id == 4242
    assert rec.request_id == 'rid-xyz'


def test_completion_line_carries_request_id_no_participant(client, caplog):
    with caplog.at_level(logging.INFO):
        r = client.get('/')
    recs = [rec for rec in caplog.records if getattr(rec, 'http_path', None) == '/']
    assert recs, 'expected a request-completion log record'
    assert recs[0].request_id == r.headers['X-Request-Id']
    assert recs[0].participant_id is None              # anonymous; no DB query forced


def test_successful_static_hit_not_logged(client, caplog):
    with caplog.at_level(logging.INFO):
        resp = client.get('/static/style.css')
    if resp.status_code == 200:
        static_recs = [r for r in caplog.records
                       if str(getattr(r, 'http_path', '')).startswith('/static/')]
        assert not static_recs                          # skipped to keep logs signal-dense
    else:
        pytest.skip('static asset not served in this checkout')
