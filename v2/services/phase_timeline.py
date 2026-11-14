"""When each phase of a consultation ran, replayed from the audit log (#599).

The conversation row holds only the current phase flags; the moments they changed are the
append-only audit rows written by the phase commands (#135). Replaying those rows in order
gives each phase's first start and last end without a schema change. Only phase keys and
timestamps leave this module: never an actor, never an audit detail beyond the phase keys.
"""

from datetime import timezone

# The audit operations that change which phases are on, or end them all.
PHASE_OPERATIONS = (
    'phase.advance', 'phase.schedule.fire', 'phase.set',
    'conversation.archive', 'conversation.reopen', 'conversation.close',
)


def _utc_iso(value) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _replay(events) -> tuple[dict, dict]:
    """First start and last end per phase key, from audit rows oldest first.

    Each event is ``(ts, operation, target_id, detail)``. A guided move (``phase.advance``,
    ``phase.schedule.fire``) turns ``from_phase`` off and its target on; ``phase.set`` names
    the whole new set; archive and close end everything, and reopen resumes what archive
    ended. A phase that is turned on again keeps its first start and loses its end.
    """
    active: set[str] = set()
    before_archive: set[str] = set()
    started: dict = {}
    ended: dict = {}
    for ts, operation, target_id, detail in events:
        detail = detail or {}
        if operation in ('phase.advance', 'phase.schedule.fire'):
            source = detail.get('from_phase')
            # A source missing from the replay was turned on before the audit log existed:
            # its end is still known.
            if source:
                ended[source] = ts
            now_on = (active - {source}) | ({target_id} if target_id else set())
        elif operation == 'phase.set':
            now_on = set(detail.get('active_keys') or [])
        elif operation in ('conversation.archive', 'conversation.close'):
            before_archive = active
            now_on = set()
        elif operation == 'conversation.reopen':
            now_on = set(before_archive)
        else:
            continue
        for key in now_on - active:
            started.setdefault(key, ts)
            ended.pop(key, None)
        for key in active - now_on:
            ended[key] = ts
        active = now_on
    return started, ended


def build_phase_timeline(*, conversation, route: list[dict], events) -> list[dict]:
    """One row per phase on the conversation's route, preparation left out.

    ``route`` is the route's stage list (``key`` and ``flag``), so a phase the route skips
    never appears. The state comes from the conversation as it is now: a phase is running
    while its flag is on and the consultation is neither archived nor closed. A phase is
    ended once it has been reached and is no longer running; one reached before the audit
    log existed is ended with its dates unknown (null).
    """
    started, ended = _replay(events)
    open_now = bool(conversation.active) and conversation.closed_at is None
    current = 0
    for index, stage in enumerate(route):
        if stage['flag'] and getattr(conversation, stage['flag']):
            current = index
    rows = []
    for index, stage in enumerate(route):
        if not stage['flag']:
            continue
        key = stage['key']
        if open_now and getattr(conversation, stage['flag']):
            state = 'running'
        elif key in started or key in ended or index <= current:
            state = 'ended'
        else:
            state = 'not_started'
        rows.append({
            'key': key,
            'state': state,
            'startedAt': _utc_iso(started.get(key)) if state != 'not_started' else None,
            'endedAt': _utc_iso(ended.get(key)) if state == 'ended' else None,
        })
    return rows
