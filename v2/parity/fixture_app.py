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
os.environ['DEV_FAKE_LOGIN'] = '1'
os.environ['DEV_DATABASE_URL'] = f'sqlite:///{DATABASE_PATH}'
os.environ.setdefault('SECRET_KEY', 'parity-fixture-only-secret')
os.environ.setdefault('TOOL_TOOLFORGE_API_URL', '')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module  # noqa: E402  (environment must precede app configuration)
from db import (  # noqa: E402
    AdminRole, AuditEvent, Conversation, ConversationInvite, Participant,
    Participation, db,
)


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

_PARITY_PSEUDONYMS = [
    'calm-otter', 'bright-fox', 'steady-heron', 'gentle-raven', 'quiet-badger',
]
_PARITY_NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
app_module._generate_pseudonyms = lambda count=5: _PARITY_PSEUDONYMS[:count]
app_module._is_emailable = lambda username: username == 'dev-user-2'
_original_eligibility_check = app_module._check_join_eligibility
_original_reveal_context = app_module._reveal_context


def _fixture_eligibility_check(conversation, participant):
    if conversation.eligibility_event_id == 'parity-denied':
        return False, 'ineligible', {'reason': 'This fixture account needs more edits.'}
    return _original_eligibility_check(conversation, participant)


app_module._check_join_eligibility = _fixture_eligibility_check
app_module._reveal_context = lambda conversation, participation: _original_reveal_context(
    conversation, participation, now=_PARITY_NOW,
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
    participant = Participant(
        mw_user_id=-1,
        mw_username='dev-user-1',
        xid=app_module._derive_xid('dev-fake:-1:dev-user-1'),
    )
    moderator = Participant(
        mw_user_id=-2,
        mw_username='dev-user-2',
        xid=app_module._derive_xid('dev-fake:-2:dev-user-2'),
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
    about_public = Conversation(
        slug='parity-about-public', polis_id='parity-about-public-polis',
        title='Public conversation record', active=True, access_policy='public',
        phase_submission=True,
        intro_text='<p>A public introduction with <strong>trusted HTML</strong>.</p>',
    )
    about_participant = Conversation(
        slug='parity-about-participant', polis_id='parity-about-participant-polis',
        title='Participant conversation record', active=True, access_policy='public',
        phase_submission=True,
        outro_text='<p>A closing note for participants.</p>',
    )
    about_moderator = Conversation(
        slug='parity-about-moderator', polis_id='parity-about-moderator-polis',
        title='Moderator conversation record', active=True, access_policy='public',
        phase_argument_mapping=True,
    )
    about_scheduled = Conversation(
        slug='parity-about-scheduled', polis_id='parity-about-scheduled-polis',
        title='Scheduled conversation record', active=True, access_policy='public',
        scheduled_transition_at=datetime(2030, 2, 3, 14, 30, tzinfo=timezone.utc),
        scheduled_transition_target='submission',
    )
    about_mixed = Conversation(
        slug='parity-about-mixed', polis_id='parity-about-mixed-polis',
        title='Mixed output conversation record', active=True, access_policy='public',
        phase_submission=True,
        phase_argument_mapping=True,
    )
    join_public = Conversation(
        slug='parity-join-public', polis_id='parity-join-public-polis',
        title='Public consultation invitation', active=True, access_policy='public',
        intro_text='<p>Help shape a shared plan with <strong>trusted context</strong>.</p>',
    )
    join_email = Conversation(
        slug='parity-join-email', polis_id='parity-join-email-polis',
        title='Email-ready consultation', active=True, access_policy='public',
    )
    join_invite = Conversation(
        slug='parity-join-invite', polis_id='parity-join-invite-polis',
        title='Invited contributors only', active=True, access_policy='invite_only',
    )
    join_eligibility = Conversation(
        slug='parity-join-eligibility', polis_id='parity-join-eligibility-polis',
        title='Experienced editor consultation', active=True, access_policy='public',
        eligibility_event_id='parity-denied',
        eligibility_label='Experienced editors',
    )
    join_conflict = Conversation(
        slug='parity-join-conflict', polis_id='parity-join-conflict-polis',
        title='Pseudonym conflict consultation', active=True, access_policy='public',
    )
    pseudonym_owner = Conversation(
        slug='parity-pseudonym-owner', polis_id='parity-pseudonym-owner-polis',
        title='Pseudonym owner fixture', active=False, access_policy='public',
    )
    reveal_pending = Conversation(
        slug='parity-reveal-pending', polis_id='parity-reveal-pending-polis',
        title='Pending identity consultation', active=False, access_policy='public',
        closed_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
    )
    reveal_open = Conversation(
        slug='parity-reveal-open', polis_id='parity-reveal-open-polis',
        title='Open identity consultation', active=False, access_policy='public',
        closed_at=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc),
    )
    reveal_revealed = Conversation(
        slug='parity-reveal-linked', polis_id='parity-reveal-linked-polis',
        title='Linked identity consultation', active=False, access_policy='public',
        closed_at=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc),
    )
    reveal_expired = Conversation(
        slug='parity-reveal-expired', polis_id='parity-reveal-expired-polis',
        title='Expired identity consultation', active=False, access_policy='public',
        closed_at=datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc),
    )
    db.session.add_all([
        admin, target, participant, moderator, moderation, closed,
        about_public, about_participant, about_moderator, about_scheduled, about_mixed,
        join_public, join_email, join_invite, join_eligibility, join_conflict,
        pseudonym_owner, reveal_pending, reveal_open, reveal_revealed, reveal_expired,
    ])
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
        Participation(
            participant_id=participant.id,
            conversation_id=about_participant.id,
            pseudonym='curious-lynx',
            new_stmt_ids=[101, 102],
        ),
        Participation(
            participant_id=moderator.id,
            conversation_id=about_moderator.id,
            pseudonym='careful-raven',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=about_scheduled.id,
            pseudonym='patient-badger',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=about_mixed.id,
            pseudonym='steady-wolf',
        ),
        Participation(
            participant_id=admin.id,
            conversation_id=pseudonym_owner.id,
            pseudonym='calm-otter',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=reveal_pending.id,
            pseudonym='waiting-orca',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=reveal_open.id,
            pseudonym='open-penguin',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=reveal_revealed.id,
            pseudonym='linked-marten',
            public_username=participant.mw_username,
            revealed_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=reveal_expired.id,
            pseudonym='private-heron',
        ),
        ConversationInvite(
            conversation_id=join_invite.id,
            mw_username=participant.mw_username,
        ),
        AdminRole(
            participant_id=moderator.id,
            conversation_id=about_moderator.id,
            role='moderator',
            granted_by=admin.id,
        ),
        AdminRole(
            participant_id=moderator.id,
            conversation_id=join_invite.id,
            role='moderator',
            granted_by=admin.id,
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
