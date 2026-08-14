"""Disposable Flask server with deterministic records for visual parity capture."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
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
    AdminRole, Argument, ArgumentSideState, ArgumentVote, AuditEvent,
    ContentFlag, Conversation, ConversationBan, ConversationInvite, FeaturedStatement,
    Participant, Participation, StatementProvenance, StatementSimilarityScore, db,
)
from services.admin_moderation import AdminFlagQueue, AdminFlagRow  # noqa: E402
from services.invites import InviteBatchResult, InviteBatchSaveError  # noqa: E402


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
_original_load_intermediate_results = app_module._load_intermediate_results
_original_build_admin_catalog = app_module.build_admin_catalog
_original_admin_view = application.view_functions['admin.admin']
_original_build_invitation_roster = app_module.build_invitation_roster
_original_add_conversation_invites = app_module.add_conversation_invites
_original_admin_invitation_view = application.view_functions[
    'admin.admin_conversation_invites'
]
_original_admin_participant_roster_model = app_module._admin_participant_roster_model
_original_admin_flag_queue_model = app_module._admin_flag_queue_model
_original_load_admin_statement_sources = app_module._load_admin_statement_sources
_original_seed_statement_lock_reason = app_module._seed_statement_lock_reason
_original_admin_statements_view = application.view_functions[
    'admin.admin_conversation_statements'
]


def _parity_state():
    state = app_module.request.args.get('parity-state')
    if state is None and app_module.request.referrer:
        state = parse_qs(urlparse(app_module.request.referrer).query).get(
            'parity-state', [None],
        )[0]
    return state


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
    if conversation.slug.startswith('parity-preliminary-results'):
        detailed = not conversation.slug.endswith('-unavailable')
        statements = [{
            'fs_id': 201,
            'text': 'Regional communities should share infrastructure funding.',
            'p2': {'n_agree': 12, 'n_pass': 3, 'n_disagree': 5, 'n_voters': 20,
                   'pct_agree': 60.0, 'pct_pass': 15.0, 'pct_disagree': 25.0},
            'p6': {'n_agree': 14, 'n_pass': 4, 'n_disagree': 2, 'n_voters': 20,
                   'pct_agree': 70.0, 'pct_pass': 20.0, 'pct_disagree': 10.0},
            'shift': 10.0,
            'my_p6_label': 'Agree' if participation else None,
        }]
        return {
            'statements': statements,
            'p2_participants': 25,
            'p6_participants': 22,
            'matched_participants': None,
            'p2_consensus': statements,
            'p2_divisive': statements,
            'filter': results_filter or app_module.Phase6ResultsFilter.empty(),
            'is_preliminary': True,
            'clusters': None,
            'pg_available': detailed,
        }
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


def _fixture_intermediate_results(conversation):
    if not conversation.slug.startswith('parity-intermediate-'):
        return _original_load_intermediate_results(conversation)
    if conversation.slug == 'parity-intermediate-recomputing':
        return None, None, True
    if conversation.slug == 'parity-intermediate-pending':
        return None, None, False
    results = {
        'majority': {
            'agree': [
                {'statement_text': 'Shared maintenance should be funded collectively.', 'value': .82},
            ],
            'disagree': [
                {'statement_text': 'Every platform should use one central budget.', 'value': .64},
            ],
        },
        'groups': [{
            'agree': [
                {'statement_text': 'Local communities should retain operational autonomy.', 'value': .76},
            ],
            'disagree': [
                {'statement_text': 'Standards should be imposed without consultation.', 'value': .61},
            ],
        }],
    }
    participant_count = 30 if conversation.slug.endswith('-large') else 12
    return results, {'n_participants': participant_count}, False


app_module._load_intermediate_results = _fixture_intermediate_results


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
    state = _parity_state()
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


def _fixture_admin_catalog(**kwargs):
    state = _parity_state()
    if state == 'admin-empty':
        kwargs = {**kwargs, 'conversations': [], 'global_admins': []}
    elif state == 'admin-global-admin-roster':
        kwargs = {
            **kwargs,
            'conversations': [],
            'global_admins': Participant.query.filter(
                Participant.mw_username.in_(['ParityAdmin', 'ParityTarget']),
            ).order_by(Participant.mw_username).all(),
        }
    return _original_build_admin_catalog(**kwargs)


def _fixture_admin_view():
    state = _parity_state()
    if state not in ('admin-empty', 'admin-global-admin-roster'):
        return _original_admin_view()
    global_admins = []
    if state == 'admin-global-admin-roster':
        global_admins = Participant.query.filter(
            Participant.mw_username.in_(['ParityAdmin', 'ParityTarget']),
        ).order_by(Participant.mw_username).all()
    return app_module.render_template(
        'admin.html',
        conversations=[],
        participants=[],
        global_admins=global_admins,
        phase_routes=app_module.PHASE_ROUTES,
    )


app_module.build_admin_catalog = _fixture_admin_catalog
application.view_functions['admin.admin'] = _fixture_admin_view


def _fixture_invitation_roster(**kwargs):
    roster = _original_build_invitation_roster(**kwargs)
    if _parity_state() == 'admin-invitations-empty':
        roster['invitations'] = []
    return roster


def _fixture_add_conversation_invites(*args, **kwargs):
    state = _parity_state()
    if state == 'admin-invitations-batch':
        return InviteBatchResult(
            added=1,
            already_present=1,
            concurrent_conflicts=0,
            duplicate_inputs=1,
        )
    if state == 'admin-invitations-save-error':
        raise InviteBatchSaveError('parity fixture save failure')
    return _original_add_conversation_invites(*args, **kwargs)


def _fixture_admin_invitation_view(**kwargs):
    if _parity_state() != 'admin-invitations-empty':
        return _original_admin_invitation_view(**kwargs)
    conversation = app_module._require_mod_for_conv(kwargs['conv_id'])
    return app_module.render_template(
        'admin_invites.html', conversation=conversation, invites=[],
    )


app_module.build_invitation_roster = _fixture_invitation_roster
app_module.add_conversation_invites = _fixture_add_conversation_invites
application.view_functions[
    'admin.admin_conversation_invites'
] = _fixture_admin_invitation_view


def _fixture_admin_participant_roster(conversation):
    roster = _original_admin_participant_roster_model(conversation)
    state = _parity_state()
    if state == 'admin-participants-empty':
        return replace(roster, rows=[])
    if state == 'admin-participants-progress-unavailable':
        return replace(roster, statement_progress_unavailable=True)
    return roster


app_module._admin_participant_roster_model = _fixture_admin_participant_roster


def _fixture_admin_flag_queue(conversation):
    state = _parity_state()
    if not state or not state.startswith('admin-flags-'):
        return _original_admin_flag_queue_model(conversation)
    rows = []
    if state in ('admin-flags-open-statement', 'admin-flags-moderator'):
        flag = ContentFlag(
            id=9101,
            conversation_id=conversation.id,
            content_type='statement',
            statement_tid=12,
            category='privacy',
            detail='Contains identifying details.',
            status='open',
            created_at=_PARITY_NOW,
        )
        rows.append(AdminFlagRow(
            flag=flag,
            category_label='Privacy violation',
            target_label='Statement #12',
            target_text='A statement containing private information.',
        ))
    elif state == 'admin-flags-open-argument':
        flag = ContentFlag(
            id=9102,
            conversation_id=conversation.id,
            content_type='argument',
            argument_id=42,
            category='off_topic',
            detail=None,
            status='open',
            created_at=_PARITY_NOW,
        )
        rows.append(AdminFlagRow(
            flag=flag,
            category_label='Off-topic',
            target_label='Argument #42',
            target_text='This argument needs moderator review.',
        ))
    elif state == 'admin-flags-resolved':
        flag = ContentFlag(
            id=9103,
            conversation_id=conversation.id,
            content_type='statement',
            statement_tid=13,
            category='other',
            detail=None,
            status='resolved',
            created_at=_PARITY_NOW,
            resolved_at=_PARITY_NOW,
            resolution_note='Reviewed by the moderation team.',
        )
        rows.append(AdminFlagRow(
            flag=flag,
            category_label='Other',
            target_label='Statement #13',
            target_text='A previously reviewed statement.',
        ))
    return AdminFlagQueue(
        conversation=conversation,
        rows=rows,
        statement_texts_available=True,
    )


app_module._admin_flag_queue_model = _fixture_admin_flag_queue


def _fixture_statement_rows():
    state = _parity_state()
    if not state or not state.startswith('admin-statements-'):
        return None
    if state in {'admin-statements-empty', 'admin-statements-seed-import-open'}:
        return ([], [], [])
    if state == 'admin-statements-upstream-unavailable':
        return None
    pending = [{
        'tid': 11,
        'txt': 'A participant proposal awaiting moderator review.',
        'mod': 0,
        'is_seed': False,
        'agree_count': 2,
        'pass_count': 1,
        'disagree_count': 3,
    }]
    approved = [{
        'tid': 12,
        'txt': 'Regional communities should share infrastructure funding.',
        'mod': 1,
        'is_seed': True,
        'agree_count': 14,
        'pass_count': 4,
        'disagree_count': 2,
    }]
    hidden = [{
        'tid': 14,
        'txt': 'A hidden statement retained for moderator review.',
        'mod': -1,
        'is_seed': False,
        'agree_count': 1,
        'pass_count': 2,
        'disagree_count': 7,
    }]
    if state == 'admin-statements-provenance':
        pending = []
        approved = [{
            'tid': 13,
            'txt': 'Regional communities should jointly fund shared infrastructure.',
            'mod': 1,
            'is_seed': True,
            'agree_count': 11,
            'pass_count': 3,
            'disagree_count': 2,
        }]
        hidden = []
    return pending, approved, hidden


def _fixture_admin_statement_sources(conversation):
    rows = _fixture_statement_rows()
    if rows is None and _parity_state() != 'admin-statements-upstream-unavailable':
        return _original_load_admin_statement_sources(conversation)
    conversation.statement_moderation_policy = None
    strict = _parity_state() == 'admin-statements-strict-moderation'
    return rows, None if rows is None else strict


def _fixture_seed_statement_lock_reason(conversation):
    if _parity_state() == 'admin-statements-seed-import-locked':
        return 'Seed statements are locked because statement submission has ended.'
    return _original_seed_statement_lock_reason(conversation)


def _fixture_admin_statements_view(conv_id):
    state = _parity_state()
    if not state or not state.startswith('admin-statements-'):
        return _original_admin_statements_view(conv_id)
    conversation = app_module._require_mod_for_conv(conv_id)
    rows, strict = _fixture_admin_statement_sources(conversation)
    if rows is None:
        pending = approved = hidden = []
        app_module.flash('Could not load statements. Check server logs.', 'error')
    else:
        pending, approved, hidden = rows
    tids = [row['tid'] for row in pending + approved + hidden]
    lock_reason = _fixture_seed_statement_lock_reason(conversation)
    return app_module.render_template(
        'admin_statements.html',
        conversation=conversation,
        pending=pending,
        approved=approved,
        hidden=hidden,
        settings={'strict_moderation': strict} if strict is not None else {},
        featured_tids={
            row.polis_statement_id
            for row in FeaturedStatement.query.filter_by(
                conversation_id=conversation.id,
            ).all()
        },
        provenance_map=app_module._provenance_map(conversation.id, tids),
        phase_active=conversation.phase_argument_mapping,
        seed_import_allowed=lock_reason is None,
        seed_import_lock_reason=lock_reason,
        polis_public_url='https://pol.is',
        max_import_rows=app_module.MAX_ROWS,
        max_import_chars=app_module.MAX_TEXT_CHARS,
    )


app_module._load_admin_statement_sources = _fixture_admin_statement_sources
app_module._seed_statement_lock_reason = _fixture_seed_statement_lock_reason
application.view_functions[
    'admin.admin_conversation_statements'
] = _fixture_admin_statements_view


class _FixtureParticiapiResponse:
    def __init__(self, payload: dict, status: int = 200, *, cookies=None):
        self.status_code = status
        self.ok = status < 400
        self._payload = payload
        self.content = json.dumps(payload).encode('utf-8')
        self.text = self.content.decode('utf-8')
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
    if path.endswith('/results'):
        return _FixtureParticiapiResponse({'groups': [], 'majority': {}})
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
        statement_moderation_policy=None,
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
    banned_submission = Conversation(
        slug='parity-banned-submission', polis_id='parity-banned-submission-polis',
        title='Readable suspended consultation', active=True,
        access_policy='public', phase_submission=True,
        intro_text='<p>Participation is moderated independently of visibility.</p>',
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
    arguments_mapping = Conversation(
        slug='parity-arguments-mapping', polis_id='parity-arguments-mapping-polis',
        title='Community infrastructure priorities', active=True,
        access_policy='public', phase_submission=True,
        phase_argument_mapping=True, argument_vote_data={'K': 2},
    )
    arguments_gates = Conversation(
        slug='parity-arguments-gates', polis_id='parity-arguments-gates-polis',
        title='Shared platform principles', active=True,
        access_policy='public', phase_submission=True,
        phase_argument_mapping=True, argument_vote_data={'K': 2},
    )
    arguments_moderator = Conversation(
        slug='parity-arguments-moderator', polis_id='parity-arguments-moderator-polis',
        title='Moderated infrastructure discussion', active=True,
        access_policy='public', phase_submission=True,
        phase_argument_mapping=True, argument_vote_data={'K': 2},
    )
    informed_voting = Conversation(
        slug='parity-informed-voting', polis_id='parity-informed-voting-polis',
        title='Community infrastructure priorities', active=True,
        access_policy='public', phase_submission=True,
        phase_argument_mapping=True, phase_informed_voting=True,
        phase6_polis_conversation_id='parity-informed-voting-phase6',
    )
    informed_pending = Conversation(
        slug='parity-informed-pending', polis_id='parity-informed-pending-polis',
        title='Informed round initialization', active=True,
        access_policy='public', phase_informed_voting=True,
        phase6_polis_conversation_id='parity-informed-pending-phase6',
    )
    informed_empty = Conversation(
        slug='parity-informed-empty', polis_id='parity-informed-empty-polis',
        title='Informed round awaiting statements', active=True,
        access_policy='public', phase_informed_voting=True,
        phase6_polis_conversation_id='parity-informed-empty-phase6',
    )
    preliminary_results = Conversation(
        slug='parity-preliminary-results', polis_id='parity-preliminary-results-polis',
        title='Community infrastructure priorities', active=True,
        access_policy='public', phase_informed_voting=True,
        phase_public_results=True,
        phase6_polis_conversation_id='parity-preliminary-results-phase6',
    )
    preliminary_unavailable = Conversation(
        slug='parity-preliminary-results-unavailable',
        polis_id='parity-preliminary-results-unavailable-polis',
        title='Results data temporarily unavailable', active=True,
        access_policy='public', phase_public_results=True,
        phase6_polis_conversation_id='parity-preliminary-results-unavailable-phase6',
    )
    intermediate_ready = Conversation(
        slug='parity-intermediate-ready', polis_id='parity-intermediate-ready-polis',
        title='Initial community priorities', active=True,
        access_policy='public', phase_public_results=True,
    )
    intermediate_large = Conversation(
        slug='parity-intermediate-large', polis_id='parity-intermediate-large-polis',
        title='Broad community priorities', active=True,
        access_policy='public', phase_public_results=True,
    )
    intermediate_pending = Conversation(
        slug='parity-intermediate-pending', polis_id='parity-intermediate-pending-polis',
        title='Results awaiting enough votes', active=True,
        access_policy='public', phase_public_results=True,
    )
    intermediate_recomputing = Conversation(
        slug='parity-intermediate-recomputing',
        polis_id='parity-intermediate-recomputing-polis',
        title='Results computation in progress', active=True,
        access_policy='public', phase_public_results=True,
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
    workspace_restricted = Conversation(
        slug='parity-workspace-restricted',
        polis_id='parity-workspace-restricted-polis',
        title='Restricted community planning', active=True,
        access_policy='invite_only', phase_submission=True,
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
    seed_conversations = [
        admin, target, participant, moderator, moderation, closed,
        about_public, about_participant, banned_submission, about_moderator,
        about_scheduled, about_mixed,
        arguments_mapping, arguments_gates, arguments_moderator,
        informed_voting, informed_pending, informed_empty,
        preliminary_results, preliminary_unavailable,
        intermediate_ready, intermediate_large,
        intermediate_pending, intermediate_recomputing,
        join_public, join_email, join_invite, workspace_restricted,
        join_eligibility, join_conflict,
        pseudonym_owner, reveal_pending, reveal_open, reveal_revealed, reveal_expired,
        report_public, report_personal, report_empty,
        lane_attention, lane_caught, lane_paused, lane_waiting, lane_closed,
        lane_available, lane_moderated, demo_available, demo_joined,
    ]
    for index, conversation in enumerate(seed_conversations):
        if isinstance(conversation, Conversation) and conversation.created_at is None:
            conversation.created_at = _PARITY_NOW + timedelta(minutes=index)
    db.session.add_all(seed_conversations)
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
            participant_id=participant.id,
            conversation_id=banned_submission.id,
            pseudonym='suspended-ibis',
        ),
        ConversationBan(
            conversation_id=banned_submission.id,
            participant_id=participant.id,
            summary='Participation suspended for parity coverage.',
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
            participant_id=participant.id,
            conversation_id=arguments_mapping.id,
            pseudonym='thoughtful-kestrel',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=arguments_gates.id,
            pseudonym='patient-osprey',
        ),
        Participation(
            participant_id=moderator.id,
            conversation_id=arguments_moderator.id,
            pseudonym='watchful-hawk',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=informed_voting.id,
            pseudonym='reflective-albatross',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=informed_pending.id,
            pseudonym='patient-puffin',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=informed_empty.id,
            pseudonym='waiting-wren',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=preliminary_results.id,
            pseudonym='analytical-kite',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=preliminary_unavailable.id,
            pseudonym='patient-tern',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=intermediate_ready.id,
            pseudonym='careful-egret',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=intermediate_large.id,
            pseudonym='broad-falcon',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=intermediate_pending.id,
            pseudonym='waiting-stork',
        ),
        Participation(
            participant_id=participant.id,
            conversation_id=intermediate_recomputing.id,
            pseudonym='calculating-owl',
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
            conversation_id=arguments_moderator.id,
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
    db.session.flush()

    mapping_participation = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=arguments_mapping.id,
    ).one()
    gates_participation = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=arguments_gates.id,
    ).one()
    moderator_participation = Participation.query.filter_by(
        participant_id=moderator.id, conversation_id=arguments_moderator.id,
    ).one()
    featured_rows = [
        FeaturedStatement(
            conversation_id=arguments_mapping.id, polis_statement_id=201,
            statement_text='Regional communities should share infrastructure funding.',
            confirmed_by_admin=True,
        ),
        FeaturedStatement(
            conversation_id=arguments_gates.id, polis_statement_id=202,
            statement_text='Shared platforms should publish long-term maintenance plans.',
            confirmed_by_admin=True,
        ),
        FeaturedStatement(
            conversation_id=arguments_moderator.id, polis_statement_id=203,
            statement_text='Technical standards should be governed by affected communities.',
            confirmed_by_admin=True,
        ),
    ]
    db.session.add_all(featured_rows)
    db.session.flush()
    mapping_fs, gates_fs, moderator_fs = featured_rows
    statement_featured = FeaturedStatement(
        conversation_id=moderation.id,
        polis_statement_id=12,
        statement_text='Regional communities should share infrastructure funding.',
        confirmed_by_admin=True,
    )
    provenance = StatementProvenance(
        conversation_id=moderation.id,
        polis_statement_id=13,
        derived_from_tid=12,
        provenance_type='derivative',
        link_method='declared',
        created_at=_PARITY_NOW,
    )
    db.session.add_all([statement_featured, provenance])
    db.session.flush()
    db.session.add(StatementSimilarityScore(
        provenance_id=provenance.id,
        model='char',
        value=0.88,
        scored_at=_PARITY_NOW,
    ))

    mapping_arguments = [
        Argument(featured_statement_id=mapping_fs.id, side='pro', body='Shared funding reduces duplicated maintenance work.'),
        Argument(featured_statement_id=mapping_fs.id, side='pro', body='Smaller communities gain access to specialist support.'),
        Argument(featured_statement_id=mapping_fs.id, side='con', body='Shared budgets can blur local accountability.'),
    ]
    gates_arguments = [
        Argument(featured_statement_id=gates_fs.id, side='pro', body='Published plans make deferred maintenance visible.'),
        Argument(featured_statement_id=gates_fs.id, side='pro', body='Communities can coordinate upgrades before systems fail.'),
        Argument(featured_statement_id=gates_fs.id, side='pro', body='Long-term plans make funding requests easier to compare.'),
        Argument(featured_statement_id=gates_fs.id, side='con', body='Plans can become obsolete before implementation.'),
        Argument(featured_statement_id=gates_fs.id, side='con', body='Mandatory planning may burden small volunteer teams.'),
    ]
    moderator_arguments = [
        Argument(featured_statement_id=moderator_fs.id, side='pro', body='Affected communities bring essential operational knowledge.'),
        Argument(featured_statement_id=moderator_fs.id, side='pro', body='Shared governance creates durable legitimacy.', hidden=True),
        Argument(featured_statement_id=moderator_fs.id, side='pro', body='Community review catches implementation risks early.'),
        Argument(featured_statement_id=moderator_fs.id, side='con', body='Broad governance can slow urgent technical decisions.'),
        Argument(featured_statement_id=moderator_fs.id, side='con', body='Specialist standards require sustained technical expertise.'),
        Argument(featured_statement_id=moderator_fs.id, side='con', body='Responsibility may become difficult to assign.'),
    ]
    db.session.add_all(mapping_arguments + gates_arguments + moderator_arguments)
    db.session.flush()
    db.session.add_all([
        ArgumentSideState(participant_id=mapping_participation.participant_id, featured_statement_id=mapping_fs.id, side='pro', skipped=False, argument_order=[item.id for item in mapping_arguments if item.side == 'pro']),
        ArgumentSideState(participant_id=mapping_participation.participant_id, featured_statement_id=mapping_fs.id, side='con', skipped=True, argument_order=[item.id for item in mapping_arguments if item.side == 'con']),
        ArgumentSideState(participant_id=gates_participation.participant_id, featured_statement_id=gates_fs.id, side='pro', skipped=True, argument_order=[item.id for item in gates_arguments if item.side == 'pro']),
        ArgumentSideState(participant_id=gates_participation.participant_id, featured_statement_id=gates_fs.id, side='con', skipped=True, argument_order=[item.id for item in gates_arguments if item.side == 'con']),
        ArgumentSideState(participant_id=moderator_participation.participant_id, featured_statement_id=moderator_fs.id, side='pro', skipped=True, argument_order=[item.id for item in moderator_arguments if item.side == 'pro']),
        ArgumentSideState(participant_id=moderator_participation.participant_id, featured_statement_id=moderator_fs.id, side='con', skipped=True, argument_order=[item.id for item in moderator_arguments if item.side == 'con']),
        ArgumentVote(argument_id=gates_arguments[0].id, participant_id=participant.id),
        ArgumentVote(argument_id=moderator_arguments[0].id, participant_id=moderator.id),
    ])
    informed_fs = FeaturedStatement(
        conversation_id=informed_voting.id, polis_statement_id=301,
        phase6_polis_statement_id=401,
        statement_text='Regional communities should share infrastructure funding.',
        confirmed_by_admin=True,
    )
    pending_fs = FeaturedStatement(
        conversation_id=informed_pending.id, polis_statement_id=302,
        phase6_polis_statement_id=None,
        statement_text='Featured statements should remain visible while initialization completes.',
        confirmed_by_admin=True,
    )
    preliminary_fs = FeaturedStatement(
        conversation_id=preliminary_results.id, polis_statement_id=303,
        phase6_polis_statement_id=403,
        statement_text='Regional communities should share infrastructure funding.',
        confirmed_by_admin=True,
    )
    unavailable_fs = FeaturedStatement(
        conversation_id=preliminary_unavailable.id, polis_statement_id=304,
        phase6_polis_statement_id=404,
        statement_text='Detailed results should degrade without inventing zero counts.',
        confirmed_by_admin=True,
    )
    db.session.add_all([informed_fs, pending_fs, preliminary_fs, unavailable_fs])
    db.session.flush()
    informed_participation = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=informed_voting.id,
    ).one()
    pending_participation = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=informed_pending.id,
    ).one()
    informed_participation.phase6_card_order = [informed_fs.id]
    pending_participation.phase6_card_order = [pending_fs.id]
    db.session.add_all([
        Argument(featured_statement_id=informed_fs.id, side='pro', body='Shared funding reduces duplicated maintenance work.'),
        Argument(featured_statement_id=informed_fs.id, side='pro', body='Smaller communities gain access to specialist support.'),
        Argument(featured_statement_id=informed_fs.id, side='pro', body='Joint investment makes long-term upgrades affordable.'),
        Argument(featured_statement_id=informed_fs.id, side='pro', body='Common infrastructure improves interoperability.'),
        Argument(featured_statement_id=informed_fs.id, side='con', body='Shared budgets can blur local accountability.'),
        Argument(featured_statement_id=informed_fs.id, side='con', body='Regional priorities may require independent timelines.'),
        Argument(featured_statement_id=informed_fs.id, side='con', body='Central coordination can slow urgent local decisions.'),
        Argument(featured_statement_id=informed_fs.id, side='con', body='Funding formulas may disadvantage smaller affiliates.'),
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
