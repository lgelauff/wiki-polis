"""Explore-phase read model and server-side Particiapi gateway."""

import hashlib
from dataclasses import dataclass

import requests


class ExploreUpstreamError(RuntimeError):
    """Particiapi could not complete an Explore read or command."""


@dataclass
class ParticiapiSessionState:
    cookie: str | None = None
    csrf_token: str | None = None

    @classmethod
    def from_dict(cls, value: dict | None):
        value = value or {}
        return cls(cookie=value.get('cookie'), csrf_token=value.get('csrfToken'))

    def to_dict(self) -> dict:
        return {'cookie': self.cookie, 'csrfToken': self.csrf_token}


class ExploreGateway:
    """Translate wiki-polis use cases into private Particiapi HTTP calls."""

    def __init__(self, *, base_url: str, transport, state: ParticiapiSessionState,
                 subject: str | None, subject_secret: str | None):
        self.base_url = base_url.rstrip('/')
        self.transport = transport
        self.state = state
        self.subject = subject
        self.subject_secret = subject_secret

    def _cookies(self) -> dict:
        return {'session': self.state.cookie} if self.state.cookie else {}

    def ensure_session(self) -> None:
        if self.state.cookie and self.state.csrf_token:
            return
        binding = bool(self.subject and self.subject_secret)
        headers = {}
        if binding:
            headers = {
                'X-Particiapi-Sub': self.subject,
                'X-Particiapi-Sub-Secret': self.subject_secret,
            }
        try:
            response = self.transport.post(
                f'{self.base_url}/api/session',
                params={} if binding else {'create': 'true'},
                headers=headers,
                cookies={} if binding else self._cookies(),
                json={},
                timeout=5,
            )
        except requests.RequestException as exc:
            raise ExploreUpstreamError('Particiapi is unavailable.') from exc
        if not response.ok:
            raise ExploreUpstreamError(
                f'Particiapi session failed with HTTP {response.status_code}.',
            )
        payload = response.json() if response.content else {}
        if not isinstance(payload, dict):
            raise ExploreUpstreamError('Particiapi returned an invalid session payload.')
        cookie = response.cookies.get('session') or self.state.cookie
        csrf_token = payload.get('csrf_token')
        if not cookie or not csrf_token:
            raise ExploreUpstreamError('Particiapi returned an incomplete session.')
        self.state.cookie = cookie
        self.state.csrf_token = csrf_token

    def read(self, conversation_id: str) -> tuple[dict, dict]:
        self.ensure_session()
        try:
            statements = self.transport.get(
                f'{self.base_url}/api/conversations/{conversation_id}/statements/',
                cookies=self._cookies(), timeout=10,
            )
            participant = self.transport.get(
                f'{self.base_url}/api/conversations/{conversation_id}/participant',
                cookies=self._cookies(), timeout=10,
            )
        except requests.RequestException as exc:
            raise ExploreUpstreamError('Particiapi is unavailable.') from exc
        if not statements.ok or not participant.ok:
            status = statements.status_code if not statements.ok else participant.status_code
            raise ExploreUpstreamError(f'Particiapi read failed with HTTP {status}.')
        statement_payload = statements.json() if statements.content else {}
        participant_payload = participant.json() if participant.content else {}
        if not isinstance(statement_payload, dict) or not isinstance(participant_payload, dict):
            raise ExploreUpstreamError('Particiapi returned an invalid Explore payload.')
        return statement_payload, participant_payload

    def vote(self, conversation_id: str, statement_id: int, polis_value: int) -> None:
        self.ensure_session()
        try:
            response = self.transport.put(
                f'{self.base_url}/api/conversations/{conversation_id}/votes/{statement_id}',
                cookies=self._cookies(),
                headers={
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': self.state.csrf_token,
                },
                json={'value': polis_value},
                timeout=10,
            )
        except requests.RequestException as exc:
            raise ExploreUpstreamError('Particiapi is unavailable.') from exc
        if not response.ok:
            raise ExploreUpstreamError(
                f'Particiapi vote failed with HTTP {response.status_code}.',
            )

    def submit_statement(self, conversation_id: str, text: str) -> int:
        """Create one upstream statement. Callers must provide idempotency."""
        self.ensure_session()
        try:
            response = self.transport.post(
                f'{self.base_url}/api/conversations/{conversation_id}/statements/',
                cookies=self._cookies(),
                headers={
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': self.state.csrf_token,
                },
                json={'text': text},
                timeout=10,
            )
        except requests.RequestException as exc:
            raise ExploreUpstreamError(
                'The statement outcome is unknown; do not retry with a new key.',
            ) from exc
        if response.status_code != 201:
            raise ExploreUpstreamError(
                f'Particiapi statement outcome is unknown after HTTP {response.status_code}.',
            )
        payload = response.json() if response.content else {}
        statement_id = payload.get('id') if isinstance(payload, dict) else None
        if not isinstance(statement_id, int):
            raise ExploreUpstreamError(
                'Particiapi created a statement but returned no usable identifier.',
            )
        return statement_id


def normalise_statements(payload: dict) -> list[dict]:
    statements = []
    for raw_id, raw in (payload or {}).items():
        if not isinstance(raw, dict):
            continue
        try:
            statement_id = int(raw.get('id', raw_id))
        except (TypeError, ValueError):
            continue
        text = str(raw.get('text') or raw.get('txt') or '').strip()
        if not text:
            continue
        statements.append({
            'id': statement_id,
            'text': text,
            'isMeta': bool(raw.get('is_meta')),
            'isSeed': bool(raw.get('is_seed')),
        })
    return statements


def build_explore_state(
    *,
    statements_payload: dict,
    participant_payload: dict,
    ordering_key: str,
    new_statement_unlock_at: int,
    new_statement_max: int,
    new_statements_used: int,
) -> dict:
    """Build a privacy-safe, stable participant queue projection."""
    statements = normalise_statements(statements_payload)
    voted = {int(value) for value in participant_payload.get('votes', [])}
    authored = {int(value) for value in participant_payload.get('statements', [])}

    def order_key(statement: dict):
        digest = hashlib.sha256(
            f"{ordering_key}:{statement['id']}".encode(),
        ).hexdigest()
        return (not statement['isMeta'], not statement['isSeed'], digest)

    statements.sort(key=order_key)
    completed_ids = voted | authored
    current = next(
        (statement for statement in statements if statement['id'] not in completed_ids),
        None,
    )
    total = len(statements)
    completed = sum(statement['id'] in completed_ids for statement in statements)
    effective_unlock = min(new_statement_unlock_at, total or new_statement_unlock_at)
    new_statement_unlocked = completed >= effective_unlock or current is None
    quota_remaining = max(0, new_statement_max - new_statements_used)
    return {
        'currentStatement': current,
        'progress': {
            'completed': completed,
            'total': total,
            'remaining': max(0, total - completed),
            'allDone': current is None,
        },
        'newStatement': {
            'unlocked': new_statement_unlocked and quota_remaining > 0,
            'unlockAfter': effective_unlock,
            'quota': new_statement_max,
            'used': new_statements_used,
            'remaining': quota_remaining,
        },
    }
