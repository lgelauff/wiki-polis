"""Logging foundation (Plan 1 / Phase 1).

Substrate only: how records are formatted (text in dev/test, JSON in prod),
correlated (request_id + participant_id via a LogRecord factory), and redacted
(a minimal secret/identifier scrub). Domain logging (audit, engagement) is Plans 2/4.

Design notes from the expert review:
- We configure the root logger *imperatively* (add a handler, set levels) rather than
  via ``logging.config.dictConfig``. dictConfig's ``disable_existing_loggers`` defaults
  to True and would silence already-imported loggers (e.g. ``polis_admin``, ``werkzeug``);
  configuring imperatively never disables anything, so those keep flowing to root.
- request_id / participant_id are injected by a ``LogRecord`` factory, not a Filter, so
  the fields land on *every* record — including Flask's built-in exception log and
  pytest's ``caplog`` — without attaching a filter to each handler.
- Redaction happens in the *formatter* (post-format), so it also scrubs exception
  tracebacks rendered by the formatter (which a record-level filter cannot see).
- participant_id is the internal id only (never username / mw_username / xid) and is read
  best-effort from ``g`` — the factory never issues a query.
"""

import json
import logging
import re
from datetime import datetime, timezone

from flask import g, has_request_context
from sqlalchemy.engine import make_url  # noqa: F401  (re-exported for callers/tests)

_HANDLER_NAME = 'wikipolis-stderr'
_factory_installed = False

# Minimal redaction (full catalogue is Plan 3). Each entry scrubs a concrete high-risk
# token from the final formatted line (message + traceback).
_REDACTIONS = [
    # credentials embedded in a URL: scheme://user:PASSWORD@host -> scheme://user:***@host
    (re.compile(r'(://[^:/?#\s]+:)[^@/?#\s]+(@)'), r'\1***\2'),
    # xid / sha256-shaped hex (reversible identifier, #96)
    (re.compile(r'\b[0-9a-fA-F]{64}\b'), '[redacted-hash]'),
    # key=value / key: value for sensitive keys — redact the whole value run (handles
    # multi-word values like "Bearer <token>"), stopping at a field delimiter.
    (re.compile(r'(?i)\b(authorization|cookie|set-cookie|token|secret|password|passwd|pwd|api[_-]?key)\b'
                r'(["\s:=]+)[^\r\n,;}"\']+'), r'\1\2[redacted]'),
]


def _redact(s: str) -> str:
    for pattern, repl in _REDACTIONS:
        s = pattern.sub(repl, s)
    return s


# Extra record attributes the JSON formatter surfaces as top-level fields when present.
_JSON_EXTRA_FIELDS = ('http_method', 'http_path', 'http_status', 'duration_ms',
                      'env', 'db_backend', 'polis_configured', 'polis_pg_configured', 'git_version')


class RedactingJsonFormatter(logging.Formatter):
    """One JSON object per line, mirroring the Polis server's winston shape."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp':   datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            'level':       record.levelname,
            'service':     'wiki-polis',
            'logger':      record.name,
            'message':     record.getMessage(),
            'request_id':  getattr(record, 'request_id', '-'),
        }
        pid = getattr(record, 'participant_id', None)
        if pid is not None:
            payload['participant_id'] = pid
        for field in _JSON_EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload['stack'] = self.formatException(record.exc_info)
        return _redact(json.dumps(payload, default=str))


class RedactingTextFormatter(logging.Formatter):
    """Human-readable, for dev/test. Redacts the fully-rendered line (incl. traceback)."""

    def format(self, record: logging.LogRecord) -> str:
        return _redact(super().format(record))


def _install_record_factory() -> None:
    """Wrap the LogRecord factory once to stamp request_id + participant_id on every record."""
    global _factory_installed
    if _factory_installed:
        return
    old_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        if has_request_context():
            record.request_id = g.get('request_id', '-')
            participant = g.get('participant')
            record.participant_id = getattr(participant, 'id', None)  # best-effort, no query
        else:
            record.request_id = '-'
            record.participant_id = None
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


def configure_logging(app, on_toolforge: bool = False) -> None:
    """Idempotent. Text in dev/test, JSON in prod (gated on on_toolforge only)."""
    _install_record_factory()

    root = logging.getLogger()
    # Idempotent: remove only OUR previously-installed handler — never clear all root
    # handlers (that would drop pytest's caplog handler mid-test).
    for handler in [h for h in root.handlers if getattr(h, 'name', None) == _HANDLER_NAME]:
        root.removeHandler(handler)

    root.setLevel(logging.INFO if on_toolforge else logging.DEBUG)

    # Defend against an accidental SQLALCHEMY_ECHO / echo=True dumping SQL + bound values.
    for noisy in ('sqlalchemy', 'sqlalchemy.engine', 'sqlalchemy.pool'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Flask's lazy app.logger: drop its default handler and let it propagate to root,
    # so there is a single handler (no double-logging).
    app.logger.handlers = []
    app.logger.propagate = True

    # In tests, let pytest's caplog own the root handler. The record factory still
    # provides request_id / participant_id, so assertions on those fields work.
    if app.testing:
        return

    handler = logging.StreamHandler()  # defaults to sys.stderr
    handler.name = _HANDLER_NAME
    if on_toolforge:
        handler.setFormatter(RedactingJsonFormatter())
    else:
        handler.setFormatter(RedactingTextFormatter(
            '%(asctime)s %(levelname)s [%(request_id)s pid=%(participant_id)s] %(name)s: %(message)s'))
    root.addHandler(handler)
