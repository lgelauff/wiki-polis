"""Admin HTTP adapters for the versioned browser API.

This module registers admin routes on the API v1 blueprint. Application services,
authorization, and transaction ownership remain injected by the composition root.
"""

from collections.abc import Callable

from flask import Blueprint, jsonify, request

from services.invites import InviteBatchSaveError
from services.admin_lifecycle import (
    Phase6InitializationConflict, Phase6InitializationSaveFailed,
    Phase6InitializationUnavailable,
    PhasePreparationFailed, PhaseReadinessBlocked,
    PhaseReadinessUnconfirmed, PhaseTransitionConflict,
    PhaseTransitionSaveFailed, PhaseTransitionUnavailable,
    ConversationClosed, PublicationPhase6Missing,
    InvalidAdvancedPhaseSet,
    PublicationReadinessUnconfirmed, PublicationUnavailable,
    ScheduleInPast, ScheduleUnavailable,
)
from services.admin_termination import (
    DeletionBlockedByVotes, DeletionOutcomeUnknown, DeletionUpstreamFailed,
    DeletionVerificationUnavailable,
)
from services.admin_statements import (
    LastFeaturedStatementProtected, StatementModerationUpstreamFailed,
    ModerationPolicySaveFailed, ModerationPolicyUpstreamFailed,
    ModerationPolicyVerificationUnavailable,
    SeedImportUpstreamFailed, SeedImportValidationFailed,
    SeedImportVerificationUnavailable, SeedStatementParentNotFound,
    SeedStatementUpstreamFailed, SeedStatementValidationFailed,
)
from services.admin_featured import (
    ArgumentNotInFeaturedWorkspace,
    FeaturedCommandOutcomeUnknown, FeaturedRoundSyncFailed,
    FeaturedSourceUnavailable, FeaturedStatementNotFound,
    LastFeaturedSelectionProtected,
)
from services.admin_catalog import (
    ConversationCreationSaveFailed, ConversationCreationUpstreamFailed,
    ConversationSlugConflict, GlobalAdminParticipantNotFound,
)


def register_admin_routes(
    bp: Blueprint,
    *,
    no_store: Callable,
    error_response: Callable,
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
) -> None:
    """Register admin-only HTTP adapters on the shared API blueprint."""
    _no_store = no_store
    @bp.get('/admin')
    def get_admin_catalog():
        return _no_store(jsonify({'data': resolve_admin_catalog()}))

    @bp.post('/admin/conversations')
    def post_admin_conversation():
        body = request.get_json(silent=True)
        required = {
            'slug', 'title', 'introHtml', 'outroHtml', 'accessPolicy',
            'phaseRoute', 'eligibilityEventId', 'eligibilityLabel', 'polisId',
        }
        if (not isinstance(body, dict) or set(body) != required
                or not isinstance(body.get('slug'), str)
                or not isinstance(body.get('title'), str)
                or not body['title'].strip() or len(body['title'].strip()) > 255
                or any(not isinstance(body.get(key), str) for key in (
                    'introHtml', 'outroHtml', 'phaseRoute',
                    'eligibilityEventId', 'eligibilityLabel',
                ))
                or len(body['eligibilityEventId']) > 80
                or len(body['eligibilityLabel']) > 255
                or body.get('accessPolicy') not in {'public', 'invite_only', 'demo'}
                or (body.get('polisId') is not None
                    and not isinstance(body['polisId'], str))):
            return error_response(
                'validation_failed', 'Check the conversation fields.', 400,
            )
        try:
            data = create_admin_conversation(body)
        except ConversationSlugConflict:
            return error_response(
                'slug_conflict', 'That conversation slug is already in use.', 409,
            )
        except ConversationCreationUpstreamFailed:
            return error_response(
                'upstream_unavailable',
                'The voting conversation could not be created.', 502,
            )
        except ConversationCreationSaveFailed as exc:
            return error_response(
                'command_outcome_unknown' if exc.outcome_unknown else 'save_failed',
                ('A voting conversation may have been created. Do not retry until a site admin checks it.'
                 if exc.outcome_unknown else 'The conversation could not be saved.'),
                409 if exc.outcome_unknown else 503,
            )
        return _no_store(jsonify({'data': data})), 201

    @bp.post('/admin/global-admin-grants')
    def post_global_admin_grant():
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'username'}
                or not isinstance(body.get('username'), str)
                or not body['username'].strip()):
            return error_response(
                'validation_failed', 'Provide a Wikimedia username.', 400,
            )
        try:
            data = grant_global_admin(body)
        except GlobalAdminParticipantNotFound:
            return error_response(
                'participant_not_found',
                'That account must sign in once before it can be granted access.', 404,
            )
        return _no_store(jsonify({'data': data})), 201 if data['changed'] else 200

    @bp.put('/admin/global-admins/<int:participant_id>')
    def put_global_admin(participant_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'granted'}
                or not isinstance(body.get('granted'), bool)):
            return error_response(
                'validation_failed', 'Use granted true or false.', 400,
            )
        try:
            data = set_global_admin(participant_id, body)
        except GlobalAdminParticipantNotFound:
            return error_response(
                'participant_not_found', 'That participant does not exist.', 404,
            )
        return _no_store(jsonify({'data': data}))

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
            'eligibilityEventId', 'eligibilityLabel', 'recommendationTier',
            'adminNotes',
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
        for key in ('introHtml', 'outroHtml', 'eligibilityEventId', 'eligibilityLabel', 'adminNotes'):
            if not isinstance(body[key], str):
                fields[key] = ['Use text.']
        if isinstance(body['eligibilityEventId'], str) and len(body['eligibilityEventId']) > 80:
            fields['eligibilityEventId'] = ['Use at most 80 characters.']
        if isinstance(body['eligibilityLabel'], str) and len(body['eligibilityLabel']) > 255:
            fields['eligibilityLabel'] = ['Use at most 255 characters.']
        if isinstance(body['adminNotes'], str) and len(body['adminNotes']) > 4000:
            fields['adminNotes'] = ['Use at most 4000 characters.']
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

    @bp.put('/admin/conversations/<int:conversation_id>/recommendation-tier')
    def put_admin_conversation_recommendation_tier(conversation_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'tier'}
                or body['tier'] not in {'simple', 'medium', 'complex'}):
            return error_response(
                'validation_failed', 'Choose a supported scope tier.', 400,
                details={'fields': {'tier': ['Choose simple, medium, or complex.']}},
            )
        return _no_store(jsonify({
            'data': update_admin_recommendation_tier(conversation_id, body),
        }))

    @bp.get('/admin/conversations/<int:conversation_id>/termination')
    def get_admin_conversation_termination(conversation_id: int):
        return _no_store(jsonify({
            'data': resolve_admin_termination(conversation_id),
        }))

    @bp.delete('/admin/conversations/<int:conversation_id>')
    def delete_admin_conversation_route(conversation_id: int):
        try:
            data = delete_admin_conversation(conversation_id)
        except DeletionVerificationUnavailable:
            return error_response(
                'deletion_verification_unavailable',
                'Voting data could not be verified; nothing was deleted.', 503,
            )
        except DeletionBlockedByVotes as exc:
            return error_response(
                'deletion_blocked_by_votes',
                'A conversation with votes must be retained or archived.', 409,
                details={'validVoteCount': exc.count},
            )
        except DeletionUpstreamFailed:
            return error_response(
                'upstream_unavailable',
                'The voting service could not be hidden; nothing was deleted.', 502,
            )
        except DeletionOutcomeUnknown:
            return error_response(
                'command_outcome_unknown',
                'The voting service was hidden, but local deletion failed. Do not retry.',
                409,
            )
        return _no_store(jsonify({'data': data}))

    @bp.get('/admin/conversations/<int:conversation_id>/statements')
    def get_admin_conversation_statements(conversation_id: int):
        return _no_store(jsonify({
            'data': resolve_admin_statements(conversation_id),
        }))

    @bp.put('/admin/conversations/<int:conversation_id>/statement-moderation-policy')
    def put_admin_statement_moderation_policy(conversation_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'mode'}
                or body['mode'] not in {'moderate', 'auto_approve'}):
            return error_response(
                'validation_failed', 'Choose moderate or auto_approve.', 400,
            )
        try:
            data = set_admin_statement_policy(conversation_id, body)
        except ModerationPolicyVerificationUnavailable:
            return error_response(
                'verification_unavailable',
                'The current moderation state could not be verified; nothing was changed.', 503,
            )
        except ModerationPolicyUpstreamFailed:
            return error_response(
                'upstream_unavailable',
                'The moderation baseline could not be reconciled safely.', 502,
            )
        except ModerationPolicySaveFailed as exc:
            return error_response(
                'command_outcome_unknown' if exc.outcome_unknown else 'save_failed',
                ('The voting service may have changed. Do not retry until a site admin checks it.'
                 if exc.outcome_unknown else 'The moderation policy could not be saved.'),
                409 if exc.outcome_unknown else 503,
            )
        return _no_store(jsonify({'data': data}))

    @bp.put('/admin/conversations/<int:conversation_id>/statements/<int:statement_id>/moderation')
    def put_admin_statement_moderation(conversation_id: int, statement_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'status'}
                or body['status'] not in {'approved', 'pending', 'hidden'}):
            return error_response(
                'validation_failed',
                'Choose approved, pending, or hidden.', 400,
            )
        try:
            data = moderate_admin_statement(conversation_id, statement_id, body)
        except LastFeaturedStatementProtected:
            return error_response(
                'last_featured_statement_protected',
                'Keep one featured statement while argument mapping is active.', 409,
            )
        except StatementModerationUpstreamFailed:
            return error_response(
                'upstream_unavailable',
                'Statement moderation is temporarily unavailable.', 502,
            )
        return _no_store(jsonify({'data': data}))

    @bp.post('/admin/conversations/<int:conversation_id>/statement-imports')
    def post_admin_statement_import(conversation_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'statements'}
                or not isinstance(body['statements'], list)):
            return error_response(
                'validation_failed', 'Provide a statements array.', 400,
            )
        try:
            data = import_admin_seed_statements(conversation_id, body)
        except SeedImportValidationFailed as exc:
            return error_response('validation_failed', exc.message, 400)
        except SeedImportVerificationUnavailable:
            return error_response(
                'verification_unavailable',
                'Existing statements could not be verified; nothing was imported.',
                503,
            )
        except SeedImportUpstreamFailed as exc:
            return error_response('upstream_unavailable', exc.message, 502)
        return _no_store(jsonify({'data': data}))

    @bp.post('/admin/conversations/<int:conversation_id>/statements')
    def post_admin_seed_statement(conversation_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict)
                or set(body) != {'text', 'derivedFromId'}
                or not isinstance(body['text'], str)
                or (body['derivedFromId'] is not None
                    and (not isinstance(body['derivedFromId'], int)
                         or isinstance(body['derivedFromId'], bool)
                         or body['derivedFromId'] < 0))):
            return error_response(
                'validation_failed',
                'Provide statement text and an optional statement ID it corrects.', 400,
            )
        try:
            data = add_admin_seed_statement(conversation_id, body)
        except SeedStatementValidationFailed as exc:
            return error_response(
                'validation_failed', str(exc) or 'Provide 1 to 280 characters.', 400,
            )
        except SeedStatementParentNotFound as exc:
            return error_response(
                'derived_statement_not_found',
                f'Statement #{exc.statement_id} was not found in this conversation.', 404,
            )
        except SeedStatementUpstreamFailed as exc:
            return error_response('upstream_unavailable', exc.message, 502)
        return _no_store(jsonify({'data': data})), 201

    @bp.get('/admin/conversations/<int:conversation_id>/featured-statements')
    def get_admin_featured_statements(conversation_id: int):
        return _no_store(jsonify({
            'data': resolve_admin_featured(conversation_id),
        }))

    @bp.put('/admin/conversations/<int:conversation_id>/featured-statements/<int:statement_id>')
    def put_admin_featured_statement(conversation_id: int, statement_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'source'}
                or body['source'] not in {'system', 'manual'}):
            return error_response(
                'validation_failed', 'Choose the system or manual source.', 400,
            )
        try:
            data = select_admin_featured(conversation_id, statement_id, body)
        except FeaturedSourceUnavailable:
            return error_response(
                'verification_unavailable',
                'The statement could not be verified; nothing was selected.', 503,
            )
        except FeaturedStatementNotFound:
            return error_response(
                'statement_not_found',
                'That statement does not belong to this conversation.', 404,
            )
        except FeaturedRoundSyncFailed as exc:
            return error_response('round_sync_failed', exc.message, 502)
        except FeaturedCommandOutcomeUnknown:
            return error_response(
                'command_outcome_unknown',
                'The informed-voting round changed, but the local save failed. Do not retry.',
                409,
            )
        return _no_store(jsonify({'data': data}))

    @bp.delete('/admin/conversations/<int:conversation_id>/featured-selections/<int:featured_id>')
    def delete_admin_featured_selection(conversation_id: int, featured_id: int):
        try:
            data = remove_admin_featured(conversation_id, featured_id)
        except LastFeaturedSelectionProtected:
            return error_response(
                'last_featured_statement_protected',
                'Keep one featured statement while argument mapping is active.', 409,
            )
        except FeaturedRoundSyncFailed as exc:
            return error_response('round_sync_failed', exc.message, 502)
        except FeaturedCommandOutcomeUnknown:
            return error_response(
                'command_outcome_unknown',
                'The informed-voting round changed, but the local save failed. Do not retry.',
                409,
            )
        return _no_store(jsonify({'data': data}))

    @bp.put('/admin/conversations/<int:conversation_id>/featured-arguments/<int:argument_id>')
    def put_admin_featured_argument(conversation_id: int, argument_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'hidden'}
                or not isinstance(body['hidden'], bool)):
            return error_response(
                'validation_failed', 'Provide the desired hidden state.', 400,
            )
        try:
            data = set_admin_featured_argument(
                conversation_id, argument_id, body,
            )
        except ArgumentNotInFeaturedWorkspace:
            return error_response(
                'argument_not_found',
                'That argument does not belong to this conversation.', 404,
            )
        return _no_store(jsonify({'data': data}))

    @bp.delete('/admin/conversations/<int:conversation_id>/featured-arguments/<int:argument_id>')
    def delete_admin_featured_argument_route(
        conversation_id: int, argument_id: int,
    ):
        try:
            data = delete_admin_featured_argument(conversation_id, argument_id)
        except ArgumentNotInFeaturedWorkspace:
            return error_response(
                'argument_not_found',
                'That argument does not belong to this conversation.', 404,
            )
        return _no_store(jsonify({'data': data}))

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

    @bp.post('/admin/conversations/<int:conversation_id>/phase6-initialization')
    def create_admin_phase6_initialization(conversation_id: int):
        try:
            data = initialize_admin_phase6(conversation_id)
        except Phase6InitializationUnavailable as exc:
            messages = {
                'inactive': ('conversation_inactive', 'A closed or paused conversation cannot initialize informed voting.'),
                'phase_disabled': ('phase_disabled', 'Enable informed voting before initializing its voting round.'),
                'already_initialized': ('already_initialized', 'The informed-voting round is already initialized.'),
            }
            code, message = messages[exc.reason]
            return error_response(code, message, 409)
        except PhasePreparationFailed:
            return error_response(
                'phase_preparation_failed',
                'The informed-voting round could not be prepared safely.', 502,
            )
        except Phase6InitializationConflict:
            return error_response(
                'initialization_conflict',
                'The round was initialized concurrently. Reload before retrying.', 409,
            )
        except Phase6InitializationSaveFailed:
            return error_response(
                'command_outcome_unknown',
                'A linked voting round may have been created. Do not retry until a site admin checks it.',
                409,
            )
        return _no_store(jsonify({'data': data})), 201

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

    @bp.put('/admin/conversations/<int:conversation_id>/archive')
    def put_admin_conversation_archive(conversation_id: int):
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'archived'}
                or not isinstance(body.get('archived'), bool)):
            return error_response(
                'validation_failed', 'Use archived true or false.', 400,
            )
        try:
            data = set_admin_archive(conversation_id, body)
        except ConversationClosed:
            return error_response(
                'conversation_closed',
                'A published conversation cannot be archived or reopened.', 409,
            )
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


