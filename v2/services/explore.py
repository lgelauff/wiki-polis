"""Explore-phase read model and server-side Particiapi gateway."""

import hashlib
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# Particiapi signs its session cookie and rejects it after PERMANENT_SESSION_LIFETIME
# (7 days upstream, particiapi/config_defaults.py). An expired cookie is not refused on
# every route: GET /participant answers 200 with an EMPTY participant, which reads as
# "nothing answered yet". Re-binding before that lifetime runs out keeps the cached
# cookie valid; 6 days leaves a day of margin for clock skew and long requests.
DEFAULT_SESSION_MAX_AGE_SECONDS = 6 * 24 * 60 * 60


class ExploreUpstreamError(RuntimeError):
    """Particiapi could not complete an Explore read or command."""

    def __init__(self, message: str, *, outcome_unknown: bool = False):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


class ParticipantAnswersUnavailable(ExploreUpstreamError):
    """Particiapi reports fewer answers than Polis holds for this participant.

    Raised after one forced re-bind did not reconcile the two. Showing the deck then
    would re-offer answered statements, and a vote would overwrite the earlier one, so
    reads show an error state and votes are refused instead.
    """


def subject_digest(subject: str | None) -> str | None:
    """A non-reversible fingerprint of the bound subject, safe to keep in the session."""
    if not subject:
        return None
    return hashlib.sha256(subject.encode()).hexdigest()


@dataclass
class ParticiapiSessionState:
    cookie: str | None = None
    csrf_token: str | None = None
    # Epoch seconds of the session POST that produced ``cookie``. None for state cached
    # before this field existed: its age is unknown, so it is re-bound on first use.
    bound_at: float | None = None
    # sha256 of the subject the cookie was bound to (never the subject itself).
    subject_digest: str | None = None

    @classmethod
    def from_dict(cls, value: dict | None):
        value = value if isinstance(value, dict) else {}
        bound_at = value.get('boundAt')
        if (isinstance(bound_at, bool) or not isinstance(bound_at, (int, float))
                or not math.isfinite(bound_at)):
            bound_at = None
        digest = value.get('subjectDigest')
        return cls(
            cookie=value.get('cookie'),
            csrf_token=value.get('csrfToken'),
            bound_at=bound_at,
            subject_digest=digest if isinstance(digest, str) else None,
        )

    def to_dict(self) -> dict:
        return {
            'cookie': self.cookie,
            'csrfToken': self.csrf_token,
            'boundAt': self.bound_at,
            'subjectDigest': self.subject_digest,
        }


def _vote_count(participant_payload: dict) -> int:
    votes = participant_payload.get('votes') or []
    if not isinstance(votes, list):
        return 0
    return len({value for value in votes if isinstance(value, int)})


class ExploreGateway:
    """Translate wiki-polis use cases into private Particiapi HTTP calls.

    ``expected_vote_count`` is the mismatch guard: a callable returning how many answers
    Polis Postgres holds for this gateway's subject in the conversation being read, or
    None when that cannot be known (Postgres not configured or unreachable). When it is
    given, every participant read is checked against it.
    """

    def __init__(self, *, base_url: str, transport, state: ParticiapiSessionState,
                 subject: str | None, subject_secret: str | None,
                 max_age_seconds: float = DEFAULT_SESSION_MAX_AGE_SECONDS,
                 expected_vote_count: Callable[[str], int | None] | None = None,
                 log_context: dict | None = None,
                 clock: Callable[[], float] = time.time):
        self.base_url = base_url.rstrip('/')
        self.transport = transport
        self.state = state
        self.subject = subject
        self.subject_secret = subject_secret
        self.max_age_seconds = max_age_seconds
        self.expected_vote_count = expected_vote_count
        self.log_context = dict(log_context or {})
        self.clock = clock

    @property
    def binding(self) -> bool:
        return bool(self.subject and self.subject_secret)

    @property
    def guard_enabled(self) -> bool:
        return self.binding and self.expected_vote_count is not None

    def _log_fields(self) -> str:
        # Conversation id and phase only: never the xid, subject, username or pid.
        return ' '.join(
            f'{key}={self.log_context[key]}' for key in ('phase', 'conversation_id')
            if key in self.log_context
        )

    def _cookies(self) -> dict:
        return {'session': self.state.cookie} if self.state.cookie else {}

    def rebind_reason(self) -> str | None:
        """Why the cached session cannot be used as it is, or None when it can."""
        state = self.state
        if not (state.cookie and state.csrf_token):
            return 'missing'
        if state.bound_at is None:
            return 'legacy'
        age = self.clock() - state.bound_at
        # A bound_at in the future (clock change, tampered state) is treated as stale.
        if age >= self.max_age_seconds or age < -300:
            return 'age'
        if state.subject_digest != subject_digest(self.subject if self.binding else None):
            return 'subject'
        return None

    def _rebind(self, reason: str) -> None:
        self.state.cookie = None
        self.state.csrf_token = None
        self._bind(reason)

    def _refresh_session(self) -> None:
        self._rebind('rejected')

    def _retry_authenticated_request(self, response, send):
        if response.status_code not in {401, 403}:
            return response
        self._refresh_session()
        return send()

    def ensure_session(self) -> None:
        reason = self.rebind_reason()
        if reason is None:
            return
        if reason == 'subject':
            # Never carry a cookie bound to someone else's subject into the new session.
            self.state.cookie = None
        self._bind(reason)

    def _bind(self, reason: str) -> None:
        binding = self.binding
        headers = {}
        if binding:
            headers = {
                'X-Particiapi-Sub': self.subject,
                'X-Particiapi-Sub-Secret': self.subject_secret,
            }
        logger.info('Particiapi session bind: reason=%s binding=%s %s',
                    reason, binding, self._log_fields())
        try:
            response = self.transport.post(
                f'{self.base_url}/api/session',
                params={} if binding else {'create': 'true'},
                headers=headers,
                # Unbound sessions send the cookie they have, so a still-valid anonymous
                # session is refreshed for the same uid rather than replaced by a new one.
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
        cookie = response.cookies.get('session') or (None if binding else self.state.cookie)
        csrf_token = payload.get('csrf_token')
        if not cookie or not csrf_token:
            raise ExploreUpstreamError('Particiapi returned an incomplete session.')
        self.state.cookie = cookie
        self.state.csrf_token = csrf_token
        self.state.bound_at = self.clock()
        self.state.subject_digest = subject_digest(self.subject if binding else None)

    def _expected_votes(self, conversation_id: str) -> int | None:
        if not self.guard_enabled:
            return None
        try:
            expected = self.expected_vote_count(conversation_id)
        except Exception:
            logger.exception('Particiapi answer guard probe failed %s', self._log_fields())
            expected = None
        if expected is None:
            # Info, not warning: without POLIS_DATABASE_URL this is every read, and a
            # configured-but-failing Postgres is already logged by polis_admin._pg_query.
            logger.info(
                'Particiapi answer guard skipped: Polis Postgres unavailable %s',
                self._log_fields(),
            )
        return expected

    def _guarded(self, conversation_id: str, read_once):
        """Run ``read_once`` and reconcile its participant with Polis Postgres.

        Postgres is read FIRST, so a vote landing between the two reads can only make
        Particiapi's count larger, never smaller: a concurrent vote is not a mismatch.
        """
        expected = self._expected_votes(conversation_id)
        result = read_once()
        if expected is None:
            return result
        participant = result[1] if isinstance(result, tuple) else result
        reported = _vote_count(participant)
        if expected == 0 and reported > 0:
            # Polis knows no answers for a subject Particiapi has answers for: the lookup
            # is not finding this participant (most likely PARTICIAPI_SUB_ISSUER does not
            # match the fork's issuer), so the guard is effectively off. Say so.
            logger.warning(
                'Particiapi answer guard found no Polis record for a participant with '
                'answers (check PARTICIAPI_SUB_ISSUER): particiapi_votes=%d %s',
                reported, self._log_fields(),
            )
        if reported >= expected:
            return result
        logger.warning(
            'Particiapi answer mismatch: particiapi_votes=%d polis_votes=%d attempt=1 %s',
            reported, expected, self._log_fields(),
        )
        self._rebind('mismatch')
        result = read_once()
        participant = result[1] if isinstance(result, tuple) else result
        reported = _vote_count(participant)
        if reported >= expected:
            return result
        logger.error(
            'Particiapi answer mismatch persists after re-bind: '
            'particiapi_votes=%d polis_votes=%d %s',
            reported, expected, self._log_fields(),
        )
        raise ParticipantAnswersUnavailable(
            'Particiapi reports fewer answers than Polis holds for this participant.',
        )

    def read(self, conversation_id: str) -> tuple[dict, dict]:
        def send():
            return (
                self.transport.get(
                    f'{self.base_url}/api/conversations/{conversation_id}/statements/',
                    cookies=self._cookies(), timeout=10,
                ),
                self.transport.get(
                    f'{self.base_url}/api/conversations/{conversation_id}/participant',
                    cookies=self._cookies(), timeout=10,
                ),
            )

        def read_once():
            try:
                self.ensure_session()
                statements, participant = send()
                if {statements.status_code, participant.status_code} & {401, 403}:
                    self._refresh_session()
                    statements, participant = send()
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

        return self._guarded(conversation_id, read_once)

    def read_participant(self, conversation_id: str) -> dict:
        def send():
            return self.transport.get(
                f'{self.base_url}/api/conversations/{conversation_id}/participant',
                cookies=self._cookies(), timeout=10,
            )

        def read_once():
            try:
                self.ensure_session()
                response = self._retry_authenticated_request(send(), send)
            except requests.RequestException as exc:
                raise ExploreUpstreamError('Particiapi is unavailable.') from exc
            if not response.ok:
                raise ExploreUpstreamError(
                    f'Particiapi participant read failed with HTTP {response.status_code}.',
                )
            payload = response.json() if response.content else {}
            if not isinstance(payload, dict):
                raise ExploreUpstreamError('Particiapi returned an invalid participant payload.')
            return payload

        return self._guarded(conversation_id, read_once)

    def verify_answers(self, conversation_id: str) -> None:
        """Refuse to go on unless Particiapi's view of this participant is complete.

        For write paths that do not read the participant anyway: raises
        ParticipantAnswersUnavailable before anything is sent. A no-op without the guard.
        """
        if self.guard_enabled:
            self.read_participant(conversation_id)

    def vote(self, conversation_id: str, statement_id: int, polis_value: int) -> None:
        def send():
            return self.transport.put(
                f'{self.base_url}/api/conversations/{conversation_id}/votes/{statement_id}',
                cookies=self._cookies(),
                headers={
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': self.state.csrf_token,
                },
                json={'value': polis_value},
                timeout=10,
            )

        try:
            self.ensure_session()
            response = self._retry_authenticated_request(send(), send)
        except requests.RequestException as exc:
            raise ExploreUpstreamError('Particiapi is unavailable.') from exc
        if not response.ok:
            raise ExploreUpstreamError(
                f'Particiapi vote failed with HTTP {response.status_code}.',
            )

    def submit_statement(self, conversation_id: str, text: str) -> int:
        """Create one upstream statement. Callers must provide idempotency."""
        def send():
            return self.transport.post(
                f'{self.base_url}/api/conversations/{conversation_id}/statements/',
                cookies=self._cookies(),
                headers={
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': self.state.csrf_token,
                },
                json={'text': text},
                timeout=10,
            )

        try:
            self.ensure_session()
            response = self._retry_authenticated_request(send(), send)
        except requests.RequestException as exc:
            raise ExploreUpstreamError(
                'The statement outcome is unknown; do not retry with a new key.',
                outcome_unknown=True,
            ) from exc
        if response.status_code != 201:
            raise ExploreUpstreamError(
                f'Particiapi statement failed with HTTP {response.status_code}.',
                outcome_unknown=response.status_code >= 500,
            )
        payload = response.json() if response.content else {}
        statement_id = payload.get('id') if isinstance(payload, dict) else None
        if not isinstance(statement_id, int):
            raise ExploreUpstreamError(
                'Particiapi created a statement but returned no usable identifier.',
                outcome_unknown=True,
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
