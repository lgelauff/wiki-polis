"""API v1 kernel and session contract.

The API is same-origin and uses the existing Flask session cookie. This module owns
HTTP serialization only; domain and persistence work belongs in application services.
"""

import json
from collections.abc import Callable
from pathlib import Path

from flask import Blueprint, Flask, jsonify, request, session, url_for
from flask_wtf.csrf import CSRFError, generate_csrf
from werkzeug.exceptions import HTTPException

from api.admin_routes import register_admin_routes
from db import Participant
from services.participations import (EligibilityDenied, InvalidPseudonym,
                                     PseudonymUnavailable)
from services.explore import ExploreUpstreamError
from services.idempotency import (CommandOutcomeUnknown, IdempotencyConflict,
                                  InvalidIdempotencyKey,
                                  validate_idempotency_key)
from services.statements import (DerivativeSimilarityTooLow,
                                 StatementPreparationUnavailable,
                                 StatementQuotaExceeded,
                                 UnknownParentStatement)
from services.argument_commands import (
    ContributionGateClosed, ExistingArgumentConflict, HiddenArgument,
    InvalidArgument, PrioritizationUnavailable, PriorityBudgetExceeded,
)
from services.content_flags import InvalidFlag
from services.identity_reveal import RevealUnavailable
from services.conversation_workspace import InviteOnlyWorkspaceAccess

_OPENAPI_SPEC = json.loads(
    (Path(__file__).resolve().parents[1] / 'openapi.json').read_text(encoding='utf-8')
)


def _no_store(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Vary'] = 'Cookie'
    return response


def error_response(code: str, message: str, status: int, *, details=None):
    error = {'code': code, 'message': message}
    if details is not None:
        error['details'] = details
    return _no_store(jsonify({'error': error})), status


def create_api_v1_blueprint(
    *,
    resolve_participant: Callable[[], Participant | None],
    resolve_global_admin: Callable[[Participant | None], bool],
    resolve_developer_logins: Callable[[], list[dict]],
    resolve_developer_mode: Callable[[], bool],
    resolve_git_version: Callable[[], str],
    resolve_conversation_lane: Callable[[bool], dict],
    resolve_conversation_workspace: Callable[[str], dict],
    resolve_conversation_about: Callable[[str], dict],
    resolve_moderation_log: Callable[[str], dict],
    resolve_conversation_output: Callable[[str, str], dict],
    resolve_identity_reveal: Callable[[str], dict],
    reveal_identity: Callable[[str], tuple[dict, int]],
    resolve_participation_entry: Callable[[str], dict],
    join_conversation: Callable[[str, dict], tuple[dict, int]],
    resolve_pseudonym_suggestions: Callable[[str], list[str]],
    resolve_explore_state: Callable[[str], dict],
    resolve_argument_mapping: Callable[[str], dict],
    resolve_informed_voting: Callable[[str], dict],
    submit_informed_vote: Callable[[str, int, str], dict],
    resolve_intermediate_results: Callable[[str], dict],
    resolve_results_report: Callable[[str], dict],
    resolve_admin_catalog: Callable[[], dict],
    create_admin_conversation: Callable[[dict], dict],
    grant_global_admin: Callable[[dict], dict],
    set_global_admin: Callable[[int, dict], dict],
    resolve_admin_participants: Callable[[int], dict],
    set_admin_participant_access: Callable[[int, int, dict], dict],
    resolve_admin_flags: Callable[[int], dict],
    resolve_admin_flag: Callable[[int, int, dict], dict],
    resolve_admin_invites: Callable[[int], dict],
    add_admin_invites: Callable[[int, dict], dict],
    remove_admin_invite: Callable[[int, int], dict],
    resolve_admin_roles: Callable[[int], dict],
    replace_admin_roles: Callable[[int, int, dict], dict],
    resolve_admin_lifecycle: Callable[[int], dict],
    resolve_admin_settings: Callable[[int], dict],
    update_admin_settings: Callable[[int, dict], dict],
    update_admin_recommendation_tier: Callable[[int, dict], dict],
    resolve_admin_termination: Callable[[int], dict],
    delete_admin_conversation: Callable[[int], dict],
    resolve_admin_statements: Callable[[int], dict],
    set_admin_statement_policy: Callable[[int, dict], dict],
    moderate_admin_statement: Callable[[int, int, dict], dict],
    add_admin_seed_statement: Callable[[int, dict], dict],
    import_admin_seed_statements: Callable[[int, dict], dict],
    resolve_admin_featured: Callable[[int], dict],
    select_admin_featured: Callable[[int, int, dict], dict],
    remove_admin_featured: Callable[[int, int], dict],
    set_admin_featured_argument: Callable[[int, int, dict], dict],
    delete_admin_featured_argument: Callable[[int, int], dict],
    advance_admin_phase: Callable[[int, dict], dict],
    initialize_admin_phase6: Callable[[int], dict],
    set_admin_pause: Callable[[int, dict], dict],
    set_admin_archive: Callable[[int, dict], dict],
    set_admin_schedule: Callable[[int, dict], dict],
    set_admin_phases: Callable[[int, dict], dict],
    publish_admin_report: Callable[[int, dict], dict],
    submit_argument: Callable[[str, int, dict], tuple[dict, int]],
    skip_argument: Callable[[str, int, str], dict],
    set_argument_priority: Callable[[str, int, bool], dict],
    submit_content_flag: Callable[[str, dict], tuple[dict, int]],
    submit_explore_vote: Callable[[str, int, str, str | None], dict],
    submit_statement: Callable[[str, dict, str], tuple[dict, int]],
) -> Blueprint:
    """Build API v1 with explicit dependencies on the current auth context."""
    bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')

    @bp.get('/session')
    def get_session():
        participant = resolve_participant()
        username = session.get('username')

        if participant is not None and participant.is_demo:
            state = 'demo'
        elif username:
            state = 'authenticated'
        else:
            state = 'anonymous'

        user = None
        if state == 'authenticated':
            user = {
                'username': username,
                'emailable': bool(session.get('emailable')),
            }

        response = jsonify({
            'data': {
                'state': state,
                'user': user,
                'capabilities': {
                    'administerSite': bool(resolve_global_admin(participant)),
                },
                'csrfToken': generate_csrf(),
                'developerMode': resolve_developer_mode(),
                'developerLogins': resolve_developer_logins(),
                'gitVersion': resolve_git_version(),
                'links': {
                    'login': url_for('login'),
                    'logout': url_for('logout'),
                },
            },
        })
        return _no_store(response)

    @bp.get('/openapi.json')
    def openapi_spec():
        return _no_store(jsonify(_OPENAPI_SPEC))

    register_admin_routes(
        bp,
        no_store=_no_store,
        error_response=error_response,
        resolve_admin_catalog=resolve_admin_catalog,
        create_admin_conversation=create_admin_conversation,
        grant_global_admin=grant_global_admin,
        set_global_admin=set_global_admin,
        resolve_admin_participants=resolve_admin_participants,
        set_admin_participant_access=set_admin_participant_access,
        resolve_admin_flags=resolve_admin_flags,
        resolve_admin_flag=resolve_admin_flag,
        resolve_admin_invites=resolve_admin_invites,
        add_admin_invites=add_admin_invites,
        remove_admin_invite=remove_admin_invite,
        resolve_admin_roles=resolve_admin_roles,
        replace_admin_roles=replace_admin_roles,
        resolve_admin_lifecycle=resolve_admin_lifecycle,
        resolve_admin_settings=resolve_admin_settings,
        update_admin_settings=update_admin_settings,
        update_admin_recommendation_tier=update_admin_recommendation_tier,
        resolve_admin_termination=resolve_admin_termination,
        delete_admin_conversation=delete_admin_conversation,
        resolve_admin_statements=resolve_admin_statements,
        set_admin_statement_policy=set_admin_statement_policy,
        moderate_admin_statement=moderate_admin_statement,
        add_admin_seed_statement=add_admin_seed_statement,
        import_admin_seed_statements=import_admin_seed_statements,
        resolve_admin_featured=resolve_admin_featured,
        select_admin_featured=select_admin_featured,
        remove_admin_featured=remove_admin_featured,
        set_admin_featured_argument=set_admin_featured_argument,
        delete_admin_featured_argument=delete_admin_featured_argument,
        advance_admin_phase=advance_admin_phase,
        initialize_admin_phase6=initialize_admin_phase6,
        set_admin_pause=set_admin_pause,
        set_admin_archive=set_admin_archive,
        set_admin_schedule=set_admin_schedule,
        set_admin_phases=set_admin_phases,
        publish_admin_report=publish_admin_report,
    )

    @bp.get('/conversations')
    def get_conversation_lane():
        space = request.args.get('space', 'real')
        if space not in {'real', 'demo'}:
            return error_response(
                'validation_failed',
                'The requested conversation space is invalid.',
                400,
                details={'fields': {'space': ['Choose real or demo.']}},
            )
        return _no_store(jsonify({
            'data': resolve_conversation_lane(space == 'demo'),
        }))

    @bp.get('/conversations/<slug>/about')
    def get_conversation_about(slug: str):
        return _no_store(jsonify({
            'data': resolve_conversation_about(slug),
        }))

    @bp.get('/conversations/<slug>/workspace')
    def get_conversation_workspace(slug: str):
        try:
            data = resolve_conversation_workspace(slug)
        except InviteOnlyWorkspaceAccess as exc:
            return error_response(
                'invite_only',
                'You have not been invited to this consultation.',
                403,
                details={
                    'title': exc.title,
                    'canModerate': exc.can_moderate,
                    'links': exc.links,
                },
            )
        return _no_store(jsonify({'data': data}))

    @bp.get('/conversations/<slug>/moderation-log')
    def get_moderation_log(slug: str):
        return _no_store(jsonify({
            'data': resolve_moderation_log(slug),
        }))

    @bp.get('/conversations/<slug>/outputs/<output_key>')
    def get_conversation_output(slug: str, output_key: str):
        return _no_store(jsonify({
            'data': resolve_conversation_output(slug, output_key),
        }))

    @bp.get('/conversations/<slug>/identity-reveal')
    def get_identity_reveal(slug: str):
        return _no_store(jsonify({
            'data': resolve_identity_reveal(slug),
        }))

    @bp.post('/conversations/<slug>/identity-reveal')
    def create_identity_reveal(slug: str):
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or body != {'confirm': True}:
            return error_response(
                'validation_failed',
                'Explicitly confirm the irreversible identity link.',
                400,
                details={'fields': {'confirm': [
                    'Set confirm to true after accepting the irreversible link.',
                ]}},
            )
        try:
            data, status = reveal_identity(slug)
        except RevealUnavailable as exc:
            return error_response(
                'identity_reveal_unavailable',
                'Identity reveal is not available in the current timeline state.',
                409,
                details={'state': exc.state},
            )
        return _no_store(jsonify({'data': data})), status

    @bp.get('/conversations/<slug>/participation-entry')
    def get_participation_entry(slug: str):
        return _no_store(jsonify({'data': resolve_participation_entry(slug)}))

    @bp.get('/conversations/<slug>/pseudonym-suggestions')
    def get_pseudonym_suggestions(slug: str):
        return _no_store(jsonify({
            'data': {'pseudonyms': resolve_pseudonym_suggestions(slug)},
        }))

    @bp.post('/conversations/<slug>/participation')
    def create_participation(slug: str):
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error_response(
                'validation_failed', 'A JSON request body is required.', 400,
            )
        fields = {}
        unknown = sorted(set(body) - {'pseudonym', 'notifyEmail', 'notifyTalkPage'})
        if unknown:
            fields['_request'] = [
                f"Unknown field{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}.",
            ]
        pseudonym = body.get('pseudonym')
        if not isinstance(pseudonym, str):
            fields['pseudonym'] = ['Choose a pseudonym.']
        for key in ('notifyEmail', 'notifyTalkPage'):
            if key in body and not isinstance(body[key], bool):
                fields[key] = ['Use true or false.']
        if fields:
            return error_response(
                'validation_failed', 'Check the highlighted fields.', 400,
                details={'fields': fields},
            )
        try:
            data, status = join_conversation(slug, body)
        except InvalidPseudonym:
            return error_response(
                'validation_failed', 'Check the highlighted fields.', 400,
                details={'fields': {'pseudonym': [
                    'Use two lowercase words separated by a hyphen.',
                ]}},
            )
        except PseudonymUnavailable:
            return error_response(
                'pseudonym_unavailable',
                'That pseudonym was just taken. Choose another.',
                409,
            )
        except EligibilityDenied as exc:
            code = ('eligibility_unavailable'
                    if exc.status == 'unavailable' else 'eligibility_denied')
            display_message = None
            if isinstance(exc.detail, dict):
                candidate = exc.detail.get('reason') or exc.detail.get('message')
                if isinstance(candidate, str) and candidate.strip():
                    display_message = candidate.strip()
            return error_response(
                code,
                'Eligibility could not be confirmed.' if exc.status == 'unavailable'
                else 'This account does not meet the participation criteria.',
                403,
                details={
                    'status': exc.status,
                    'displayMessage': display_message,
                },
            )
        return _no_store(jsonify({'data': data})), status

    @bp.get('/conversations/<slug>/explore')
    def get_explore_state(slug: str):
        try:
            data = resolve_explore_state(slug)
        except ExploreUpstreamError:
            return error_response(
                'upstream_unavailable',
                'The voting service is temporarily unavailable.',
                502,
            )
        return _no_store(jsonify({'data': data}))

    @bp.get('/conversations/<slug>/arguments')
    def get_argument_mapping(slug: str):
        return _no_store(jsonify({
            'data': resolve_argument_mapping(slug),
        }))

    @bp.get('/conversations/<slug>/informed-voting')
    def get_informed_voting(slug: str):
        try:
            data = resolve_informed_voting(slug)
        except ExploreUpstreamError:
            return error_response(
                'upstream_unavailable',
                'Informed-voting progress is temporarily unavailable.', 502,
            )
        return _no_store(jsonify({'data': data}))

    @bp.get('/conversations/<slug>/results')
    def get_results_report(slug: str):
        return _no_store(jsonify({
            'data': resolve_results_report(slug),
        }))

    @bp.get('/conversations/<slug>/intermediate-results')
    def get_intermediate_results(slug: str):
        return _no_store(jsonify({
            'data': resolve_intermediate_results(slug),
        }))

    @bp.put('/conversations/<slug>/featured-statements/<int:featured_statement_id>/informed-vote')
    def put_informed_vote(slug: str, featured_statement_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'choice'}
                or body.get('choice') not in {'agree', 'pass', 'disagree'}):
            return error_response(
                'validation_failed', 'Choose agree, pass, or disagree.', 400,
                details={'fields': {'choice': [
                    'Choose agree, pass, or disagree.',
                ]}},
            )
        try:
            data = submit_informed_vote(
                slug, featured_statement_id, body['choice'],
            )
        except ExploreUpstreamError:
            return error_response(
                'upstream_unavailable',
                'The informed vote could not reach the voting service.', 502,
            )
        return _no_store(jsonify({'data': data}))

    @bp.post('/conversations/<slug>/featured-statements/<int:featured_statement_id>/arguments')
    def create_argument(slug: str, featured_statement_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict)
                or set(body) - {'side', 'body'}
                or body.get('side') not in {'pro', 'con'}
                or not isinstance(body.get('body'), str)
                or not body['body'].strip()
                or len(body['body'].strip()) > 280):
            return error_response(
                'validation_failed', 'Check the argument side and text.', 400,
            )
        try:
            data, status = submit_argument(slug, featured_statement_id, body)
        except InvalidArgument:
            return error_response(
                'validation_failed', 'Check the argument side and text.', 400,
            )
        except ExistingArgumentConflict:
            return error_response(
                'argument_already_submitted',
                'You already submitted a different argument for this side.', 409,
            )
        return _no_store(jsonify({'data': data})), status

    @bp.put('/conversations/<slug>/featured-statements/<int:featured_statement_id>/contributions/<side>/skip')
    def put_argument_skip(slug: str, featured_statement_id: int, side: str):
        if side not in {'pro', 'con'}:
            return error_response(
                'validation_failed', 'Choose the for or against side.', 400,
            )
        try:
            data = skip_argument(slug, featured_statement_id, side)
        except InvalidArgument:
            return error_response(
                'validation_failed', 'Choose the for or against side.', 400,
            )
        except ExistingArgumentConflict:
            return error_response(
                'argument_already_submitted',
                'This side already has your argument and cannot be skipped.', 409,
            )
        return _no_store(jsonify({'data': data}))

    @bp.put('/conversations/<slug>/arguments/<int:argument_id>/priority')
    def put_argument_priority(slug: str, argument_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'selected'}
                or not isinstance(body.get('selected'), bool)):
            return error_response(
                'validation_failed', 'Use selected true or false.', 400,
            )
        try:
            data = set_argument_priority(slug, argument_id, body['selected'])
        except ContributionGateClosed:
            return error_response(
                'contribution_gate_closed',
                'Add an argument or explicitly skip both sides first.', 409,
            )
        except PrioritizationUnavailable:
            return error_response(
                'prioritization_unavailable',
                'Prioritization opens when this side has enough arguments.', 409,
            )
        except PriorityBudgetExceeded:
            return error_response(
                'priority_budget_exceeded',
                'Unmark another argument before selecting this one.', 409,
            )
        except HiddenArgument:
            return error_response(
                'argument_unavailable',
                'This argument is no longer available.', 404,
            )
        return _no_store(jsonify({'data': data}))

    @bp.post('/conversations/<slug>/flags')
    def create_content_flag(slug: str):
        body = request.get_json(silent=True)
        allowed = {'contentType', 'targetId', 'category', 'detail'}
        if (not isinstance(body, dict) or set(body) - allowed
                or body.get('contentType') not in {'statement', 'argument'}
                or not isinstance(body.get('targetId'), int)
                or isinstance(body.get('targetId'), bool)
                or body.get('targetId', 0) < 0
                or body.get('category') not in {
                    'personal_attack', 'privacy', 'off_topic', 'other',
                }
                or ('detail' in body and body['detail'] is not None
                    and not isinstance(body['detail'], str))):
            return error_response(
                'validation_failed', 'Check the flag target and reason.', 400,
            )
        try:
            data, status = submit_content_flag(slug, body)
        except InvalidFlag:
            return error_response(
                'validation_failed', 'Explain the reason when choosing Other.', 400,
                details={'fields': {'detail': ['An explanation is required.']}},
            )
        except ExploreUpstreamError:
            return error_response(
                'upstream_unavailable',
                'The statement could not be validated right now.', 502,
            )
        return _no_store(jsonify({'data': data})), status

    @bp.put('/conversations/<slug>/statements/<int:statement_id>/vote')
    def put_explore_vote(slug: str, statement_id: int):
        body = request.get_json(silent=True)
        choice = body.get('choice') if isinstance(body, dict) else None
        pass_reason = body.get('passReason') if isinstance(body, dict) else None
        if (choice not in {'agree', 'pass', 'disagree'}
                or set(body or {}) - {'choice', 'passReason'}
                or pass_reason not in {None, 'unsure', 'confusing'}
                or (choice != 'pass' and pass_reason is not None)):
            return error_response(
                'validation_failed', 'Check the highlighted fields.', 400,
                details={'fields': {
                    'choice': ['Choose agree, pass, or disagree.'],
                    'passReason': ['Use unsure or confusing only with pass.'],
                }},
            )
        try:
            data = submit_explore_vote(slug, statement_id, choice, pass_reason)
        except ExploreUpstreamError:
            return error_response(
                'upstream_unavailable',
                'The vote could not reach the voting service.',
                502,
            )
        return _no_store(jsonify({'data': data}))

    @bp.post('/conversations/<slug>/statements')
    def create_statement(slug: str):
        body = request.get_json(silent=True)
        fields = {}
        if not isinstance(body, dict):
            return error_response(
                'validation_failed', 'A JSON request body is required.', 400,
            )
        unknown = sorted(set(body) - {'text', 'derivedFromStatementId'})
        if unknown:
            fields['_request'] = [
                f"Unknown field{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}.",
            ]
        text_value = body.get('text')
        if not isinstance(text_value, str):
            fields['text'] = ['Write a statement.']
        elif not text_value.strip() or len(text_value.strip()) > 280:
            fields['text'] = ['Write between 1 and 280 characters.']
        parent = body.get('derivedFromStatementId')
        if parent is not None and (not isinstance(parent, int) or isinstance(parent, bool)):
            fields['derivedFromStatementId'] = ['Use a statement identifier.']
        if fields:
            return error_response(
                'validation_failed', 'Check the highlighted fields.', 400,
                details={'fields': fields},
            )
        idempotency_key = request.headers.get('Idempotency-Key', '')
        try:
            validate_idempotency_key(idempotency_key)
            data, status = submit_statement(slug, body, idempotency_key)
        except InvalidIdempotencyKey:
            return error_response(
                'invalid_idempotency_key',
                'Provide an Idempotency-Key of 8 to 128 safe characters.',
                400,
            )
        except IdempotencyConflict:
            return error_response(
                'idempotency_conflict',
                'That Idempotency-Key was already used for another request.',
                409,
            )
        except CommandOutcomeUnknown:
            return error_response(
                'command_outcome_unknown',
                'The original statement submission may still have succeeded. Do not retry with a new key.',
                409,
            )
        except StatementQuotaExceeded:
            return error_response(
                'statement_quota_exceeded',
                'Your new-statement quota is exhausted.',
                409,
            )
        except UnknownParentStatement:
            return error_response(
                'unknown_parent_statement',
                'The original statement is not available in this conversation.',
                400,
            )
        except DerivativeSimilarityTooLow as exc:
            return error_response(
                'derivative_similarity_too_low',
                'This looks like a different claim. Keep it closer to the original or submit a new statement.',
                409,
                details={
                    'model': exc.model,
                    'similarity': exc.similarity,
                    'threshold': exc.threshold,
                },
            )
        except StatementPreparationUnavailable:
            return error_response(
                'upstream_unavailable',
                'The voting service is temporarily unavailable. It is safe to retry with the same key.',
                502,
            )
        except ExploreUpstreamError:
            return error_response(
                'command_outcome_unknown',
                'The statement may have reached the voting service. Do not retry with a new key.',
                502,
            )
        return _no_store(jsonify({'data': data})), status

    return bp


def register_api_error_handlers(app: Flask) -> None:
    """Keep all API failures machine-readable, including routing and CSRF errors."""

    @app.errorhandler(CSRFError)
    def handle_csrf_error(exc):
        if request.path.startswith('/api/v1/'):
            return error_response('csrf_failed', exc.description, 400)
        return exc

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        if not request.path.startswith('/api/v1/'):
            return exc
        codes = {
            400: 'bad_request',
            401: 'unauthorized',
            403: 'forbidden',
            404: 'not_found',
            405: 'method_not_allowed',
            409: 'conflict',
        }
        return error_response(codes.get(exc.code, 'http_error'), exc.description, exc.code)
