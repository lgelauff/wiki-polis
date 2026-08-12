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
    join_conversation: Callable[[str, dict], tuple[dict, int]],
    resolve_pseudonym_suggestions: Callable[[str], list[str]],
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
