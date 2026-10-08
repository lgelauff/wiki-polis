"""Explore-phase read model and server-side Particiapi gateway."""

import hashlib
import heapq
from collections import deque
from dataclasses import dataclass

import requests


class ExploreUpstreamError(RuntimeError):
    """Particiapi could not complete an Explore read or command."""

    def __init__(self, message: str, *, outcome_unknown: bool = False,
                 status_code: int | None = None, problem_type: str | None = None):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown
        # What Particiapi answered, for logging only: an HTTP status and the RFC 9457
        # problem ``type`` when the body carried one. Never statement text.
        self.status_code = status_code
        self.problem_type = problem_type


class StatementAlreadyExists(ExploreUpstreamError):
    """Particiapi refused the statement because identical text is already in the conversation.

    A definite refusal: nothing was created, and retrying the same text can never succeed.
    """


# Particiapi's problem-details ``type`` for a duplicate statement: problemdetails.py builds it
# as ``tag:partici.app,2024:api:errors:<name>`` from ProblemDetails.STATEMENT_EXISTS, and
# api.py returns it with HTTP 409 when the database's unique constraint on the text fires.
_STATEMENT_EXISTS_SUFFIX = ':api:errors:statement_exists'


def _problem_type(response) -> str | None:
    """The problem-details ``type`` of an error response, or None. Never raises."""
    try:
        payload = response.json() if response.content else None
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get('type')
    return value if isinstance(value, str) and value else None


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

    def _refresh_session(self) -> None:
        self.state.cookie = None
        self.state.csrf_token = None
        self.ensure_session()

    def _retry_authenticated_request(self, response, send):
        if response.status_code not in {401, 403}:
            return response
        self._refresh_session()
        return send()

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

    def read_participant(self, conversation_id: str) -> dict:
        def send():
            return self.transport.get(
                f'{self.base_url}/api/conversations/{conversation_id}/participant',
                cookies=self._cookies(), timeout=10,
            )

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
            problem_type = _problem_type(response)
            if (response.status_code == 409 and problem_type is not None
                    and problem_type.lower().endswith(_STATEMENT_EXISTS_SUFFIX)):
                raise StatementAlreadyExists(
                    'Particiapi already holds a statement with this text.',
                    status_code=409, problem_type=problem_type,
                )
            raise ExploreUpstreamError(
                f'Particiapi statement failed with HTTP {response.status_code}.',
                outcome_unknown=response.status_code >= 500,
                status_code=response.status_code, problem_type=problem_type,
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


# #504: how many statements of another family sit between two statements of one family.
# 1 means never back to back; it fits the packs of 10 of #505 and can be raised later.
FAMILY_MIN_DISTANCE = 1


def space_by_family(statements: list[dict], families: dict | None,
                    min_distance: int = FAMILY_MIN_DISTANCE,
                    last_roots: list | None = None) -> list[dict]:
    """Reorder a deck so that no two statements of one family are closer than `min_distance`.

    `last_roots` are the family roots of the statements served just before this deck, oldest
    first (p526-1). They seed the window, so the first statements of the deck also keep their
    distance from what was already served. Spacing the unanswered rest of a deck with the
    roots of its last answered statements gives exactly the rest of the full deck's order.

    One deterministic pass over the deck in its existing order (#504). At each step, with
    `left` statements of a family still to place and `remaining` statements in all:

    1. if a family is *critical* — it can no longer be kept apart unless one of its members
       is placed now, i.e. ``left > ceil((remaining - 1) / (min_distance + 1))`` (for
       distance 1: ``2 * left > remaining``) — take the first remaining member of that family,
       if it fits the window of the last `min_distance` placed;
    2. otherwise take the first remaining statement whose family differs from the last
       `min_distance` placed;
    3. if none fits, take the first remaining statement (one family left: served in order).

    Each family keeps its own deck order, and a statement only moves where separation forces
    it, so seeds keep their place at the front unless a family needs room. For distance 1
    the pass separates every deck for which a separation exists (largest family at most
    ``ceil(n / 2)``); for a larger distance it is best effort.

    Considered and not used (owner, 2026-10-08): always serving the family with the most
    statements left first. It separates as often, but front-loads every family to the start
    of every participant's deck, ahead of the per-participant order and the seeds. It may
    come back later as an opt-in, cf. #506.

    Cost: roots are looked up once; without any family of two or more the deck is returned
    unchanged. Otherwise O(n log n) for n statements (a heap of family heads and a lazy
    max-heap of family sizes; each step touches at most `min_distance` + a few entries).
    Deterministic: the same deck and families always give the same order.
    """
    lookup = families or {}
    roots = [lookup.get(statement['id'], statement['id']) for statement in statements]
    queues: dict[int, deque] = {}
    for position, root in enumerate(roots):
        queues.setdefault(root, deque()).append(position)
    placed_roots: list = list(last_roots or [])[-min_distance:] if min_distance >= 1 else []
    if min_distance < 1 or (all(len(queue) < 2 for queue in queues.values())
                            and not set(placed_roots) & queues.keys()):
        return list(statements)

    # Heads: (deck position of the family's first remaining member, root). One live entry
    # per family; an entry is stale once that member has been placed.
    heads = [(queue[0], root) for root, queue in queues.items()]
    heapq.heapify(heads)
    # Sizes: (-left, head position, root); an entry is stale once its `left` changed.
    sizes = [(-len(queue), queue[0], root) for root, queue in queues.items()]
    heapq.heapify(sizes)

    def live_head(entry):
        queue = queues[entry[1]]
        return bool(queue) and queue[0] == entry[0]

    def live_size(entry):
        return len(queues[entry[2]]) == -entry[0]

    order: list[dict] = []
    remaining = len(statements)
    while remaining:
        window = set(placed_roots[-min_distance:])
        threshold = -(-(remaining - 1) // (min_distance + 1))  # ceil((remaining-1)/(d+1))
        take_root = None

        # 1. A critical family that fits; if several, the one whose next member comes first.
        popped = []
        critical = []
        while sizes:
            entry = sizes[0]
            if not live_size(entry):
                heapq.heappop(sizes)
                continue
            if -entry[0] <= threshold:
                break
            popped.append(heapq.heappop(sizes))
            if entry[2] not in window:
                critical.append((queues[entry[2]][0], entry[2]))
        for entry in popped:
            heapq.heappush(sizes, entry)
        if critical:
            take_root = min(critical)[1]

        # 2./3. The first remaining statement that fits, else the first remaining.
        if take_root is None:
            skipped = []
            while heads:
                entry = heads[0]
                if not live_head(entry):
                    heapq.heappop(heads)
                    continue
                if entry[1] in window:
                    skipped.append(heapq.heappop(heads))
                    continue
                take_root = entry[1]
                break
            for entry in skipped:
                heapq.heappush(heads, entry)
            if take_root is None:
                take_root = min(skipped)[1]

        queue = queues[take_root]
        position = queue.popleft()
        if queue:
            heapq.heappush(heads, (queue[0], take_root))
            heapq.heappush(sizes, (-len(queue), queue[0], take_root))
        order.append(statements[position])
        placed_roots.append(take_root)
        remaining -= 1
    return order


def build_explore_state(
    *,
    statements_payload: dict,
    participant_payload: dict,
    ordering_key: str,
    new_statement_unlock_at: int,
    new_statement_max: int,
    new_statements_used: int,
    families: dict | None = None,
    recent_answers: list[int] | None = None,
) -> dict:
    """Build a privacy-safe, stable participant queue projection.

    `families` maps statement id to family root (#504). Without it every statement is its
    own family and the order is exactly the pin's.

    `recent_answers` are the statements this participant answered last, oldest first, as the
    app recorded them (p526-1). Only the unanswered statements are spaced, and the window
    starts from the roots of the last answered ones, so a deck that changes mid-session (a
    rewording added, a statement moderated out) never serves a family member right after the
    statement just answered. Without a record (another browser, an expired session) the last
    answered statements are taken from the spaced order of the whole deck, which is exact for
    a deck that did not change. For a deck that did not change, the served sequence is the
    same either way.

    Research note (p526-2): the served order is no longer a function of the sha256 pin
    alone. It is the pin, then family spacing over the provenance (`derived_from_tid`) as it
    stood at each read, then the participant's own last answers. Rebuilding the exposure
    order of a participant therefore needs the provenance table as of each read, not only
    as of the export; nothing extra is logged for that.
    """
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
    # Meta statements keep their place at the front of the deck and are never spaced: they
    # are not part of a family.
    meta = [statement for statement in statements if statement['isMeta']]
    deck = [statement for statement in statements if not statement['isMeta']]
    lookup = families or {}
    recent = [statement_id for statement_id in (recent_answers or [])
              if statement_id in completed_ids]
    if not recent:
        recent = [statement['id'] for statement in space_by_family(deck, families)
                  if statement['id'] in completed_ids]
    last_roots = [lookup.get(statement_id, statement_id)
                  for statement_id in recent[-FAMILY_MIN_DISTANCE:]]
    unanswered = space_by_family(
        [statement for statement in deck if statement['id'] not in completed_ids],
        families, last_roots=last_roots,
    )
    current = next(
        (statement for statement in meta if statement['id'] not in completed_ids),
        unanswered[0] if unanswered else None,
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
