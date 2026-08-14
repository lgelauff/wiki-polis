"""Disposable Flask server with deterministic records for visual parity capture."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile


def _fixture_database_path() -> Path:
    configured = os.environ.get('PARITY_FIXTURE_DATABASE', '').strip()
    if not configured:
        raise RuntimeError('PARITY_FIXTURE_DATABASE must name a disposable SQLite file.')
    path = Path(configured).expanduser().resolve()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    allowed_roots = {temporary_root, Path('/private/tmp').resolve()}
    if path.suffix != '.db' or not any(root in path.parents for root in allowed_roots):
        raise RuntimeError(
            'Parity fixture database must be a .db file under a temporary directory.',
        )
    return path


DATABASE_PATH = _fixture_database_path()
os.environ['FLASK_DEBUG'] = '1'
os.environ['DEV_LOGIN_USER'] = 'ParityAdmin'
os.environ['DEV_FAKE_LOGIN'] = ''
os.environ['DEV_DATABASE_URL'] = f'sqlite:///{DATABASE_PATH}'
os.environ.setdefault('SECRET_KEY', 'parity-fixture-only-secret')
os.environ.setdefault('TOOL_TOOLFORGE_API_URL', '')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module  # noqa: E402  (environment must precede app configuration)
from db import AuditEvent, Conversation, Participant, Participation, db  # noqa: E402


application = app_module.app
application.config.update(
    TESTING=True,
    WTF_CSRF_ENABLED=False,
    RATELIMIT_ENABLED=False,
    POLIS_DATABASE_URL='',
    POLIS_SERVER_URL='',
    POLIS_ADMIN_EMAIL='',
    POLIS_ADMIN_PASSWORD='',
)


def _seed() -> None:
    db.create_all()
    if Conversation.query.filter_by(slug='parity-moderation').first() is not None:
        return

    username = 'ParityAdmin'
    admin = Participant(
        mw_user_id=abs(hash(username)) % 10**9,
        mw_username=username,
        xid=app_module._derive_xid(f'dev:{username}'),
        is_global_admin=True,
    )
    target = Participant(
        mw_user_id=424242,
        mw_username='ParityTarget',
        xid=app_module._derive_xid('parity-target'),
    )
    moderation = Conversation(
        slug='parity-moderation',
        polis_id='parity-moderation-polis',
        title='Parity moderation history',
        active=True,
        access_policy='public',
    )
    closed = Conversation(
        slug='parity-closed-output',
        polis_id='parity-closed-output-polis',
        title='Parity closed consultation',
        active=False,
        paused=False,
        access_policy='public',
        phase_public_results=True,
        closed_at=datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    db.session.add_all([admin, target, moderation, closed])
    db.session.flush()
    db.session.add_all([
        Participation(
            participant_id=admin.id,
            conversation_id=moderation.id,
            pseudonym='steady-heron',
        ),
        Participation(
            participant_id=target.id,
            conversation_id=moderation.id,
            pseudonym='quiet-otter',
        ),
        Participation(
            participant_id=admin.id,
            conversation_id=closed.id,
            pseudonym='patient-fox',
        ),
    ])
    db.session.add_all([
        AuditEvent(
            ts=datetime(2026, 8, 13, 8, 15, tzinfo=timezone.utc),
            actor_participant_id=admin.id,
            conversation_id=moderation.id,
            operation='participant.ban',
            target_type='participant',
            target_id=str(target.id),
            detail={'summary': 'private fixture note'},
        ),
        AuditEvent(
            ts=datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc),
            actor_participant_id=admin.id,
            conversation_id=moderation.id,
            operation='participant.unban',
            target_type='participant',
            target_id=str(target.id),
            detail={'summary': 'another private fixture note'},
        ),
    ])
    db.session.commit()


with application.app_context():
    _seed()


if __name__ == '__main__':
    application.run(
        host='127.0.0.1',
        port=int(os.environ.get('PARITY_FIXTURE_PORT', '5002')),
        debug=False,
        use_reloader=False,
    )
