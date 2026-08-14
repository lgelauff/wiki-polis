"""Disposable Flask server with deterministic records for visual parity capture."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qs, urlparse


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
for _login_endpoint in ('dev_login', 'dev_fake_login'):
    if _login_endpoint in application.view_functions:
        app_module.limiter.exempt(application.view_functions[_login_endpoint])

_PARITY_PSEUDONYMS = [
    'calm-otter', 'bright-fox', 'steady-heron', 'gentle-raven', 'quiet-badger',
]
_PARITY_NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
app_module._generate_pseudonyms = lambda count=5: _PARITY_PSEUDONYMS[:count]
app_module._is_emailable = lambda username: username == 'dev-user-2'
_original_eligibility_check = app_module._check_join_eligibility
_original_reveal_context = app_module._reveal_context
_original_build_phase6_results = app_module._build_phase6_results
_original_build_conversation_lane = app_module.build_conversation_lane


def _fixture_eligibility_check(conversation, participant):
    if conversation.eligibility_event_id == 'parity-denied':
        return False, 'ineligible', {'reason': 'This fixture account needs more edits.'}
    return _original_eligibility_check(conversation, participant)


app_module._check_join_eligibility = _fixture_eligibility_check
app_module._reveal_context = lambda conversation, participation: _original_reveal_context(
    conversation, participation, now=_PARITY_NOW,
)


def _fixture_results(conversation, participation, results_filter=None):
    if conversation.slug == 'parity-report-empty':
        return None
    if not (conversation.slug.startswith('parity-report-')
            or conversation.slug.startswith('parity-reveal-')):
        return _original_build_phase6_results(
            conversation, participation, results_filter=results_filter,
        )
    statements = [
            {
                'fs_id': 101,
                'text': 'Regional communities should share infrastructure funding.',
                'p2': {'n_agree': 12, 'n_pass': 3, 'n_disagree': 5, 'n_voters': 20,
                       'pct_agree': 60.0, 'pct_pass': 15.0, 'pct_disagree': 25.0},
                'p6': {'n_agree': 14, 'n_pass': 4, 'n_disagree': 2, 'n_voters': 20,
                       'pct_agree': 70.0, 'pct_pass': 20.0, 'pct_disagree': 10.0},
                'shift': 10.0,
            },
            {
                'fs_id': 102,
                'text': 'Local affiliates should retain independent programme budgets.',
                'p2': {'n_agree': 8, 'n_pass': 2, 'n_disagree': 10, 'n_voters': 20,
                       'pct_agree': 40.0, 'pct_pass': 10.0, 'pct_disagree': 50.0},
                'p6': {'n_agree': 7, 'n_pass': 2, 'n_disagree': 11, 'n_voters': 20,
                       'pct_agree': 35.0, 'pct_pass': 10.0, 'pct_disagree': 55.0},
                'shift': -5.0,
            },
        ]
    return {
        'statements': statements,
        'p2_participants': 25,
        'p6_participants': 22,
        'matched_participants': None,
        'p2_consensus': statements,
        'p2_divisive': list(reversed(statements)),
        'filter': results_filter or app_module.Phase6ResultsFilter.empty(),
        'clusters': [
            {
                'n_members': 11,
                'agree': [{'statement_text': 'Shared maintenance matters', 'value': .82}],
                'disagree': [{'statement_text': 'Centralize every budget', 'value': .64}],
            },
            {
                'n_members': 9,
                'agree': [{'statement_text': 'Local autonomy matters', 'value': .76}],
                'disagree': [],
            },
        ],
        'pg_available': True,
    }


app_module._build_phase6_results = _fixture_results


def _fixture_statements_remaining(self, zinvites, xid):
    del self, xid
    return {
        zinvite: (0 if zinvite == 'parity-lane-caught-polis' else 3)
        for zinvite in zinvites
    }


app_module.PolisServerClient.get_statements_remaining_bulk = (
    _fixture_statements_remaining
)


def _fixture_lane(*args, **kwargs):
    lane = _original_build_conversation_lane(*args, **kwargs)
    state = app_module.request.args.get('parity-state')
    if state is None and app_module.request.referrer:
        state = parse_qs(urlparse(app_module.request.referrer).query).get(
            'parity-state', [None],
        )[0]
    if state == 'empty':
        lane.public_conversations = []
        lane.attention_joined = []
        lane.caught_up_joined = []
        lane.inactive_joined = []
        lane.archived_joined = []
        lane.available = []
        lane.moderating = []
        lane.pseudonym_map = {}
        lane.signals_map = {}
    return lane


app_module.build_conversation_lane = _fixture_lane


class _FixtureParticiapiResponse:
    def __init__(self, payload: dict, status: int = 200, *, cookies=None):
        self.status_code = status
        self.ok = status < 400
        self._payload = payload
        self.content = json.dumps(payload).encode('utf-8')
        self.cookies = cookies or {}
        self.headers = {'Content-Type': 'application/json'}

    def json(self):
        return self._payload


def _fixture_particiapi(method='GET', url='', **_kwargs):
    path = urlparse(url).path.rstrip('/')
    if path.endswith('/api/session'):
        return _FixtureParticiapiResponse(
            {'csrf_token': 'parity-particiapi-csrf'},
            cookies={'session': 'parity-particiapi-session'},
        )
    if path.endswith('/statements'):
        if method.upper() == 'POST':
            return _FixtureParticiapiResponse({'id': 44}, status=201)
        return _FixtureParticiapiResponse({
            '12': {
                'id': 12,
                'text': 'Regional communities should share infrastructure funding.',
                'is_seed': True,
            },
        })
    if path.endswith('/participant'):
        referrer_query = parse_qs(urlparse(app_module.request.referrer or '').query)
        empty = referrer_query.get('parity-state') == ['empty']
        return _FixtureParticiapiResponse({
            'votes': [12] if empty else [], 'statements': [],
        })
    if '/votes/' in path:
        return _FixtureParticiapiResponse({})
    return _FixtureParticiapiResponse({}, status=404)


app_module.polis_http.request = _fixture_particiapi
app_module.polis_http.get = lambda url, **kwargs: _fixture_particiapi(
    'GET', url, **kwargs,
)
app_module.polis_http.post = lambda url, **kwargs: _fixture_particiapi(
    'POST', url, **kwargs,
)
app_module.polis_http.put = lambda url, **kwargs: _fixture_particiapi(
    'PUT', url, **kwargs,
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
    report_public = Conversation(
        slug='parity-report-public', polis_id='parity-report-public-polis',
        title='Public final report', active=False, access_policy='public',
        phase_public_results=True,
        phase6_polis_conversation_id='parity-report-public-phase6',
        created_at=datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc),
        report_filter_snapshot={'excluded_tids': [42], 'excluded_pids': [7, 9]},
    )
    report_personal = Conversation(
        slug='parity-report-personal', polis_id='parity-report-personal-polis',
        title='Participant-only final report', active=False, access_policy='public',
        phase_personal_results=True,
        phase6_polis_conversation_id='parity-report-personal-phase6',
        created_at=datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc),
        report_filter_snapshot={'excluded_tids': [], 'excluded_pids': []},
    )
    report_empty = Conversation(
        slug='parity-report-empty', polis_id='parity-report-empty-polis',
        title='Final report awaiting results', active=False, access_policy='public',
        phase_public_results=True,
        phase6_polis_conversation_id='parity-report-empty-phase6',
        created_at=datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc),
        report_filter_snapshot={'excluded_tids': [], 'excluded_pids': []},
    )
    lane_attention = Conversation(
        slug='parity-lane-attention', polis_id='parity-lane-attention-polis',
        title='Community priorities', active=True, access_policy='public',
        phase_submission=True,
        scheduled_transition_at=datetime(2026, 8, 20, 15, 30, tzinfo=timezone.utc),
        scheduled_transition_target='argument_mapping',
        created_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
    )
    lane_caught = Conversation(
        slug='parity-lane-caught', polis_id='parity-lane-caught-polis',
        title='Documentation improvements', active=True, access_policy='public',
        phase_submission=True,
        created_at=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
    )
    lane_paused = Conversation(
        slug='parity-lane-paused', polis_id='parity-lane-paused-polis',
        title='Paused governance review', active=True, paused=True,
        access_policy='public', phase_argument_mapping=True,
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
    )
    lane_waiting = Conversation(
        slug='parity-lane-waiting', polis_id='parity-lane-waiting-polis',
        title='Awaiting informed vote', active=True, access_policy='public',
        phase_cleanup=True,
        created_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
    )
    lane_closed = Conversation(
        slug='parity-lane-closed', polis_id='parity-lane-closed-polis',
        title='Completed community review', active=False, paused=False,
        access_policy='public', phase_public_results=True,
        closed_at=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    lane_available = Conversation(
        slug='parity-lane-available', polis_id='parity-lane-available-polis',
        title='Open movement consultation', active=True, access_policy='public',
        phase_argument_mapping=True,
        created_at=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc),
    )
    lane_moderated = Conversation(
        slug='parity-lane-moderated', polis_id='parity-lane-moderated-polis',
        title='Facilitated policy discussion', active=True, access_policy='public',
        phase_submission=True,
        created_at=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
    )
    demo_available = Conversation(
        slug='parity-demo-available', polis_id='parity-demo-available-polis',
        title='Try a demonstration consultation', active=True,
        access_policy='demo', phase_submission=True,
        created_at=datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
    )
    demo_joined = Conversation(
        slug='parity-demo-joined', polis_id='parity-demo-joined-polis',
        title='Your demonstration conversation', active=True,
        access_policy='demo', phase_submission=True,
        created_at=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
    )
    for reveal_conversation in (
        reveal_pending, reveal_open, reveal_revealed, reveal_expired,
    ):
        reveal_conversation.phase_public_results = True
        reveal_conversation.phase6_polis_conversation_id = f'{reveal_conversation.slug}-phase6'
        reveal_conversation.report_filter_snapshot = {
            'excluded_tids': [], 'excluded_pids': [],
        }
    db.session.add_all([
        admin, target, participant, moderator, moderation, closed,
        about_public, about_participant, about_moderator, about_scheduled, about_mixed,
        join_public, join_email, join_invite, join_eligibility, join_conflict,
        pseudonym_owner, reveal_pending, reveal_open, reveal_revealed, reveal_expired,
        report_public, report_personal, report_empty,
        lane_attention, lane_caught, lane_paused, lane_waiting, lane_closed,
        lane_available, lane_moderated, demo_available, demo_joined,
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
        Participation(
            participant_id=participant.id,
            conversation_id=report_personal.id,
            pseudonym='report-wren',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=lane_attention.id,
            pseudonym='alert-falcon',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=lane_caught.id,
            pseudonym='ready-lark',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=lane_paused.id,
            pseudonym='patient-seal',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=lane_waiting.id,
            pseudonym='waiting-tern',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=lane_closed.id,
            pseudonym='archive-wolf',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=demo_joined.id,
            pseudonym='demo-kite',
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
        AdminRole(
            participant_id=participant.id,
            conversation_id=lane_moderated.id,
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
