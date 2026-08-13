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
from services.invites import InviteBatchSaveError
from services.admin_lifecycle import (
    PhasePreparationFailed, PhaseReadinessBlocked,
    PhaseReadinessUnconfirmed, PhaseTransitionConflict,
    PhaseTransitionSaveFailed, PhaseTransitionUnavailable,
    ConversationClosed, PublicationPhase6Missing,
    InvalidAdvancedPhaseSet,
    PublicationReadinessUnconfirmed, PublicationUnavailable,
    ScheduleInPast, ScheduleUnavailable,
)

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
    resolve_conversation_lane: Callable[[bool], dict],
    resolve_conversation_about: Callable[[str], dict],
    resolve_identity_reveal: Callable[[str], dict],
    reveal_identity: Callable[[str], tuple[dict, int]],
    join_conversation: Callable[[str, dict], tuple[dict, int]],
    resolve_pseudonym_suggestions: Callable[[str], list[str]],
    resolve_explore_state: Callable[[str], dict],
    resolve_argument_mapping: Callable[[str], dict],
    resolve_informed_voting: Callable[[str], dict],
    submit_informed_vote: Callable[[str, int, str], dict],
    resolve_results_report: Callable[[str], dict],
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
    advance_admin_phase: Callable[[int, dict], dict],
    set_admin_pause: Callable[[int, dict], dict],
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
            return error_response(
                code,
                'Eligibility could not be confirmed.' if exc.status == 'unavailable'
                else 'This account does not meet the participation criteria.',
                403,
                details={'status': exc.status},
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

    @bp.get('/admin/conversations/<int:conversation_id>/participants')
    def get_admin_conversation_participants(conversation_id: int):
        return _no_store(jsonify({
            'data': resolve_admin_participants(conversation_id),
        }))

    @bp.put('/admin/conversations/<int:conversation_id>/participants/<int:participant_id>/access')
    def put_admin_participant_access(conversation_id: int, participant_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict)
                or set(body) - {'banned', 'summary'}
                or not isinstance(body.get('banned'), bool)
                or ('summary' in body and body['summary'] is not None
                    and not isinstance(body['summary'], str))):
            return error_response(
                'validation_failed', 'Check the participant access state.', 400,
                details={'fields': {
                    'banned': ['Use true or false.'],
                    'summary': ['Use text or null.'],
                }},
            )
        return _no_store(jsonify({
            'data': set_admin_participant_access(
                conversation_id, participant_id, body,
            ),
        }))

    @bp.get('/admin/conversations/<int:conversation_id>/flags')
    def get_admin_conversation_flags(conversation_id: int):
        return _no_store(jsonify({
            'data': resolve_admin_flags(conversation_id),
        }))

    @bp.put('/admin/conversations/<int:conversation_id>/flags/<int:flag_id>/resolution')
    def put_admin_flag_resolution(conversation_id: int, flag_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict)
                or set(body) - {'resolved', 'note'}
                or body.get('resolved') is not True
                or ('note' in body and body['note'] is not None
                    and not isinstance(body['note'], str))):
            return error_response(
                'validation_failed', 'Confirm this flag is resolved.', 400,
                details={'fields': {
                    'resolved': ['Set resolved to true.'],
                    'note': ['Use text or null.'],
                }},
            )
        return _no_store(jsonify({
            'data': resolve_admin_flag(conversation_id, flag_id, body),
        }))

    @bp.get('/admin/conversations/<int:conversation_id>/invitations')
    def get_admin_conversation_invites(conversation_id: int):
        return _no_store(jsonify({
            'data': resolve_admin_invites(conversation_id),
        }))

    @bp.put('/admin/conversations/<int:conversation_id>/invitations')
    def put_admin_conversation_invites(conversation_id: int):
        body = request.get_json(silent=True)
        usernames = body.get('usernames') if isinstance(body, dict) else None
        if (not isinstance(body, dict) or set(body) != {'usernames'}
                or not isinstance(usernames, list) or not usernames
                or any(not isinstance(value, str) or not value.strip()
                       or len(value.strip()) > 255 for value in usernames)):
            return error_response(
                'validation_failed', 'Provide one or more Wikimedia usernames.', 400,
                details={'fields': {'usernames': [
                    'Use a non-empty list of usernames up to 255 characters each.',
                ]}},
            )
        try:
            data = add_admin_invites(conversation_id, body)
        except InviteBatchSaveError:
            return error_response(
                'save_failed', 'The invitations could not be saved safely.', 503,
            )
        return _no_store(jsonify({'data': data}))

    @bp.delete('/admin/conversations/<int:conversation_id>/invitations/<int:invite_id>')
    def delete_admin_conversation_invite(conversation_id: int, invite_id: int):
        return _no_store(jsonify({
            'data': remove_admin_invite(conversation_id, invite_id),
        }))

    @bp.get('/admin/conversations/<int:conversation_id>/roles')
    def get_admin_conversation_roles(conversation_id: int):
        return _no_store(jsonify({
            'data': resolve_admin_roles(conversation_id),
        }))

    @bp.get('/admin/conversations/<int:conversation_id>')
    def get_admin_conversation_lifecycle(conversation_id: int):
        return _no_store(jsonify({
            'data': resolve_admin_lifecycle(conversation_id),
        }))

    @bp.get('/admin/conversations/<int:conversation_id>/settings')
    def get_admin_conversation_settings(conversation_id: int):
        return _no_store(jsonify({
            'data': resolve_admin_settings(conversation_id),
        }))

    @bp.put('/admin/conversations/<int:conversation_id>/settings')
    def put_admin_conversation_settings(conversation_id: int):
        body = request.get_json(silent=True)
        expected = {
            'title', 'introHtml', 'outroHtml', 'accessPolicy',
            'recommendationTier',
        }
        fields = {}
        if not isinstance(body, dict) or set(body) != expected:
            return error_response(
                'validation_failed', 'Provide the complete settings representation.',
                400,
            )
        if (not isinstance(body['title'], str) or not body['title'].strip()
                or len(body['title'].strip()) > 255):
            fields['title'] = ['Write a title up to 255 characters.']
        for key in ('introHtml', 'outroHtml'):
            if not isinstance(body[key], str):
                fields[key] = ['Use text.']
        if body['accessPolicy'] not in {'public', 'invite_only', 'demo'}:
            fields['accessPolicy'] = ['Choose public, invite_only, or demo.']
        if body['recommendationTier'] not in {'simple', 'medium', 'complex'}:
            fields['recommendationTier'] = ['Choose a supported scope tier.']
        if fields:
            return error_response(
                'validation_failed', 'Check the highlighted settings.', 400,
                details={'fields': fields},
            )
        return _no_store(jsonify({
            'data': update_admin_settings(conversation_id, body),
        }))

    @bp.put('/admin/conversations/<int:conversation_id>/phase')
    def put_admin_conversation_phase(conversation_id: int):
        body = request.get_json(silent=True)
        confirmed = body.get('confirmedPreconditionIds') if isinstance(body, dict) else None
        if (not isinstance(body, dict)
                or set(body) != {'confirmedPreconditionIds'}
                or not isinstance(confirmed, list)
                or any(not isinstance(value, str) or not value for value in confirmed)
                or len(set(confirmed)) != len(confirmed)):
            return error_response(
                'validation_failed', 'Confirm the transition readiness checks.', 400,
            )
        try:
            data = advance_admin_phase(conversation_id, body)
        except PhaseTransitionUnavailable as exc:
            return error_response(
                'nonlinear_phase_state' if exc.nonlinear else 'final_phase',
                'The conversation does not have a guided next phase.', 409,
            )
        except PhaseReadinessUnconfirmed as exc:
            return error_response(
                'readiness_unconfirmed', 'Confirm every readiness check.', 409,
                details={'preconditionIds': exc.ids},
            )
        except PhaseReadinessBlocked as exc:
            return error_response(
                'readiness_blocked', 'A machine-checked condition is not met.', 409,
                details={'preconditionIds': exc.ids},
            )
        except PhasePreparationFailed:
            return error_response(
                'phase_preparation_failed',
                'The next phase could not be prepared safely.', 502,
            )
        except PhaseTransitionConflict:
            return error_response(
                'transition_conflict',
                'The conversation changed concurrently. Reload before retrying.', 409,
            )
        except PhaseTransitionSaveFailed as exc:
            return error_response(
                'command_outcome_unknown' if exc.outcome_unknown else 'save_failed',
                ('A linked voting round may have been created. Do not retry until a site admin checks it.'
                 if exc.outcome_unknown else 'The phase change could not be saved.'),
                409 if exc.outcome_unknown else 503,
            )
        return _no_store(jsonify({'data': data}))

    @bp.put('/admin/conversations/<int:conversation_id>/phases')
    def put_admin_conversation_phases(conversation_id: int):
        body = request.get_json(silent=True)
        active = body.get('activeKeys') if isinstance(body, dict) else None
        if (not isinstance(body, dict) or set(body) != {'activeKeys'}
                or not isinstance(active, list)
                or any(not isinstance(value, str) or not value for value in active)
                or len(set(active)) != len(active)):
            return error_response(
                'validation_failed', 'Provide a unique phase-key set.', 400,
            )
        try:
            data = set_admin_phases(conversation_id, body)
        except InvalidAdvancedPhaseSet as exc:
            return error_response(
                'phase_not_in_route',
                'One or more phases are not part of this conversation route.', 400,
                details={'phaseKeys': exc.args[0]},
            )
        return _no_store(jsonify({'data': data}))

    @bp.put('/admin/conversations/<int:conversation_id>/pause')
    def put_admin_conversation_pause(conversation_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'paused'}
                or not isinstance(body.get('paused'), bool)):
            return error_response('validation_failed', 'Use paused true or false.', 400)
        try:
            data = set_admin_pause(conversation_id, body)
        except ConversationClosed:
            return error_response('conversation_closed', 'A closed conversation cannot be paused.', 409)
        return _no_store(jsonify({'data': data}))

    @bp.put('/admin/conversations/<int:conversation_id>/schedule')
    def put_admin_conversation_schedule(conversation_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict)
                or set(body) != {'scheduledAt', 'frozen'}
                or body.get('scheduledAt') is not None
                and not isinstance(body.get('scheduledAt'), str)
                or not isinstance(body.get('frozen'), bool)
                or body.get('scheduledAt') is None and body.get('frozen') is True):
            return error_response(
                'validation_failed',
                'Use a date-time and frozen state, or null to cancel.', 400,
            )
        try:
            data = set_admin_schedule(conversation_id, body)
        except ScheduleInPast:
            return error_response(
                'schedule_time_invalid',
                'Choose a valid future date and time.', 400,
            )
        except ScheduleUnavailable:
            return error_response(
                'schedule_unavailable',
                'Only an active-to-passive next phase can be scheduled.', 409,
            )
        return _no_store(jsonify({'data': data}))

    @bp.post('/admin/conversations/<int:conversation_id>/publication')
    def create_admin_conversation_publication(conversation_id: int):
        body = request.get_json(silent=True)
        confirmed = body.get('confirmedPreconditionIds') if isinstance(body, dict) else None
        if (not isinstance(body, dict) or set(body) != {'confirmedPreconditionIds'}
                or not isinstance(confirmed, list)
                or any(not isinstance(value, str) or not value for value in confirmed)
                or len(set(confirmed)) != len(confirmed)):
            return error_response('validation_failed', 'Confirm the publication readiness checks.', 400)
        try:
            data = publish_admin_report(conversation_id, body)
        except ConversationClosed:
            return error_response('conversation_closed', 'The report is already published.', 409)
        except PublicationUnavailable:
            return error_response('publication_unavailable', 'Enter the report cleanup window before publishing.', 409)
        except PublicationReadinessUnconfirmed as exc:
            return error_response('readiness_unconfirmed', 'Confirm every publication readiness check.', 409, details={'preconditionIds': exc.ids})
        except PublicationPhase6Missing:
            return error_response('phase6_missing', 'Initialize informed voting before publishing.', 409)
        return _no_store(jsonify({'data': data})), 201

    @bp.put('/admin/conversations/<int:conversation_id>/roles/<int:participant_id>')
    def put_admin_conversation_roles(conversation_id: int, participant_id: int):
        body = request.get_json(silent=True)
        roles = body.get('roles') if isinstance(body, dict) else None
        if (not isinstance(body, dict) or set(body) != {'roles'}
                or not isinstance(roles, list)
                or any(role not in {'moderator', 'organizer'} for role in roles)
                or len(set(roles)) != len(roles)):
            return error_response(
                'validation_failed', 'Choose a valid conversation role set.', 400,
                details={'fields': {'roles': [
                    'Use unique moderator and/or organizer values.',
                ]}},
            )
        return _no_store(jsonify({
            'data': replace_admin_roles(conversation_id, participant_id, body),
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
