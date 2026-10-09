"""#504 — family spacing of the Explore deck.

A family is every statement that shares a root: the original and the rewordings derived
from it, directly or indirectly (`statement_provenance.derived_from_tid`). The deck must
never serve two of them back to back, or a rewording reads as a repeat of what the
participant just saw. A seed belongs to a family when it has a parent; meta statements are
not part of any family and keep their place at the front of the deck.

`FAMILY_MIN_DISTANCE = 1` today: at least one statement of another family in between.
"""
import hashlib
import math
import random
import signal
from collections import Counter
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event

from db import Participation, StatementProvenance, db
from services.explore import (FAMILY_MIN_DISTANCE, build_explore_state,
                              normalise_statements, space_by_family)

# One meta statement, a seed, five statements that are each their own family, the original
# 50, its direct rewording 51 and the rewording of that rewording 52 — one family of three.
DECK = {
    '1': {'id': 1, 'text': 'Meta statement', 'is_meta': True},
    '2': {'id': 2, 'text': 'Seed statement', 'is_seed': True},
    '3': {'id': 3, 'text': 'Unrelated 3'},
    '4': {'id': 4, 'text': 'Unrelated 4'},
    '8': {'id': 8, 'text': 'Unrelated 8'},
    '9': {'id': 9, 'text': 'Unrelated 9'},
    '10': {'id': 10, 'text': 'Unrelated 10'},
    '50': {'id': 50, 'text': 'The original'},
    '51': {'id': 51, 'text': 'A rewording of the original'},
    '52': {'id': 52, 'text': 'A rewording of the rewording'},
}
FAMILIES = {
    1: 1, 2: 2, 3: 3, 4: 4, 8: 8, 9: 9, 10: 10,
    50: 50, 51: 50, 52: 50,
}
# The same deck with the seed rewording the original: a seed with a parent is in the family.
SEEDED_FAMILIES = {**FAMILIES, 2: 50}
ORDERING_KEYS = [f'participant-{index}' for index in range(12)]


def _state(votes=(), statements=(), ordering_key='participant-0', families=FAMILIES):
    return build_explore_state(
        statements_payload=DECK,
        participant_payload={'votes': list(votes), 'statements': list(statements)},
        ordering_key=ordering_key,
        new_statement_unlock_at=10,
        new_statement_max=3,
        new_statements_used=0,
        families=families,
    )


def _served(votes=(), statements=(), ordering_key='participant-0', families=FAMILIES):
    """Play the participant: answer whatever is served until the deck is done.

    Returns the ids served, in order, plus the final state.
    """
    answered = list(votes)
    served: list[int] = []
    for _ in range(len(DECK) + 2):
        state = _state(answered, statements, ordering_key, families)
        current = state['currentStatement']
        if current is None:
            return served, state
        served.append(current['id'])
        answered.append(current['id'])
    raise AssertionError('the deck never finished')


def _pin_order(statements_payload, ordering_key):
    """The order the pin produces: meta first, then seeds, then a per-participant digest."""
    statements = [
        {'id': int(key), 'isMeta': bool(raw.get('is_meta')),
         'isSeed': bool(raw.get('is_seed'))}
        for key, raw in statements_payload.items()
    ]
    return [
        statement['id'] for statement in sorted(
            statements,
            key=lambda statement: (
                not statement['isMeta'],
                not statement['isSeed'],
                hashlib.sha256(
                    f"{ordering_key}:{statement['id']}".encode(),
                ).hexdigest(),
            ),
        )
    ]


@pytest.mark.parametrize('ordering_key', ORDERING_KEYS)
@pytest.mark.parametrize('families', [FAMILIES, SEEDED_FAMILIES],
                         ids=['plain-seed', 'seed-in-the-family'])
def test_served_order_never_shows_two_family_members_back_to_back(
    ordering_key, families,
):
    served, state = _served(ordering_key=ordering_key, families=families)

    assert state['progress']['allDone'] is True
    assert state['progress']['completed'] == len(DECK)
    # Every statement is served exactly once, meta first.
    assert sorted(served) == sorted(int(key) for key in DECK)
    assert served[0] == 1

    deck = served[1:]
    assert len(set(deck)) == len(deck)
    for previous, current in zip(deck, deck[1:]):
        assert families[previous] != families[current], (
            f'{previous} and {current} share a family and were served back to back'
        )


@pytest.mark.parametrize('ordering_key', ORDERING_KEYS[:4])
@pytest.mark.parametrize('answered', range(1, len(DECK)))
def test_continuing_after_k_answers_serves_the_rest_of_the_sequence(ordering_key, answered):
    """A participant who reloads, or answers out of band, continues the same sequence."""
    full, _ = _served(ordering_key=ordering_key)
    continuation, state = _served(votes=full[:answered], ordering_key=ordering_key)

    assert continuation == full[answered:]
    if continuation:
        # The very first read after those answers serves the next statement of the sequence.
        first_read = _state(full[:answered], ordering_key=ordering_key)
        assert first_read['currentStatement']['id'] == continuation[0]
    else:
        assert state['progress']['allDone'] is True


def test_only_family_members_left_are_all_served_in_order():
    everything_else = [statement_id for statement_id in FAMILIES
                       if FAMILIES[statement_id] != 50]
    in_deck_order = [statement_id for statement_id in _pin_order(DECK, 'participant-0')
                     if FAMILIES[statement_id] == 50]

    served, state = _served(votes=everything_else)

    # The rule cannot hold for one family left; all of it is still served, in deck order.
    assert sorted(in_deck_order) == [50, 51, 52]
    assert served == in_deck_order
    assert state['progress']['allDone'] is True


def test_the_same_inputs_serve_the_same_statement_on_two_reads():
    first, first_state = _served(votes=[3, 8], ordering_key='participant-2')
    second, second_state = _served(votes=[3, 8], ordering_key='participant-2')

    assert first == second
    assert first_state['currentStatement'] == second_state['currentStatement']


def test_without_families_the_served_order_is_the_pin_order():
    assert FAMILY_MIN_DISTANCE == 1

    for ordering_key in ORDERING_KEYS:
        expected = _pin_order(DECK, ordering_key)
        assert _served(ordering_key=ordering_key, families=None)[0] == expected
        assert _served(ordering_key=ordering_key, families={})[0] == expected


def test_a_statement_the_caller_did_not_pass_is_its_own_root():
    """No provenance row at all for the unrelated statements: they are their own roots."""
    families = {2: 50, 50: 50, 51: 50, 52: 50}
    served, _ = _served(families=families)

    deck = served[1:]
    assert sorted(deck) == [2, 3, 4, 8, 9, 10, 50, 51, 52]
    for previous, current in zip(deck, deck[1:]):
        assert families.get(previous, previous) != families.get(current, current), (
            f'{previous} and {current} share a family and were served back to back'
        )


def test_the_family_keeps_its_own_order_inside_the_spaced_deck():
    served, _ = _served(families=SEEDED_FAMILIES)
    in_deck_order = [
        statement_id for statement_id in _pin_order(DECK, 'participant-0')
        if SEEDED_FAMILIES[statement_id] == 50
    ]
    family = [
        statement_id for statement_id in served
        if SEEDED_FAMILIES[statement_id] == 50
    ]

    assert sorted(in_deck_order) == [2, 50, 51, 52]
    assert family == in_deck_order


def _deck(ids):
    return [{'id': statement_id, 'text': f'Statement {statement_id}',
             'isMeta': False, 'isSeed': False} for statement_id in ids]


def _ids(statements):
    return [statement['id'] for statement in statements]


def test_a_larger_minimum_distance_is_honoured():
    """#505 will cut the spaced deck into packs; the constant has to be able to grow.

    Family 60 (60, 61) in front of two others: at distance 2 both others go in between."""
    spaced = _ids(space_by_family(_deck([60, 61, 3, 4]), {61: 60}, 2))

    assert spaced == [60, 3, 4, 61]


def _first_fitting_greedy(deck, families):
    """The brief's plain rule: always take the first remaining statement that fits the
    window, else the first remaining. The yardstick the critical-family override beats."""
    remaining = list(deck)
    placed = []
    while remaining:
        window = [families.get(statement['id'], statement['id'])
                  for statement in placed[-FAMILY_MIN_DISTANCE:]]
        fitting = [position for position, statement in enumerate(remaining)
                   if families.get(statement['id'], statement['id']) not in window]
        placed.append(remaining.pop(fitting[0] if fitting else 0))
    return placed


def _adjacent_pairs(order, families):
    return [(previous, current) for previous, current in zip(order, order[1:])
            if families.get(previous, previous) == families.get(current, current)]


def test_the_plain_rule_fails_where_the_critical_family_override_separates():
    """The plain rule spends the other statements first, so a family that sits late in the
    deck runs out of separators. The override takes a family member as soon as the family
    could otherwise no longer be kept apart (2 * left > remaining), and nothing earlier."""
    families = {71: 70, 72: 70}
    deck = _deck([1, 2, 70, 71, 72])

    plain = _ids(_first_fitting_greedy(deck, families))
    spaced = _ids(space_by_family(deck, families))

    assert _adjacent_pairs(plain, families) == [(70, 71), (71, 72)]
    assert spaced == [70, 1, 71, 2, 72]

    # The test deck: the plain rule puts 50 and 51 together; the override separates them
    # while keeping the first four statements (the seed first) where they were.
    deck = [statement for statement in normalise_statements(DECK) if not statement['isMeta']]
    plain = _ids(_first_fitting_greedy(deck, FAMILIES))
    spaced = _ids(space_by_family(deck, FAMILIES))

    assert _adjacent_pairs(plain, FAMILIES)
    assert _adjacent_pairs(spaced, FAMILIES) == []
    assert spaced == [2, 3, 4, 8, 50, 9, 51, 10, 52]


def _random_deck(rng):
    """A deck of 1..24 statements with random ids, cut into 1..n families of random size."""
    size = rng.randint(1, 24)
    ids = rng.sample(range(100, 10_000), size)
    family_count = rng.randint(1, size)
    roots = ids[:family_count]
    families = {statement_id: rng.choice(roots) for statement_id in ids}
    return _deck(ids), families


def test_property_spacing_over_many_seeded_random_decks():
    """For distance 1: every statement exactly once, and no two family members back to back
    whenever a separation exists (largest family at most ceil(n / 2))."""
    separable_with_families = inseparable = 0
    for seed in range(400):
        rng = random.Random(seed)
        deck, families = _random_deck(rng)
        spaced = _ids(space_by_family(deck, families))

        assert sorted(spaced) == sorted(_ids(deck)), seed
        sizes = Counter(families.values())
        if max(sizes.values()) <= math.ceil(len(deck) / 2):
            assert _adjacent_pairs(spaced, families) == [], (seed, spaced, families)
            separable_with_families += max(sizes.values()) > 1
        else:
            inseparable += 1
    # The sample really exercises both cases.
    assert separable_with_families > 100
    assert inseparable > 20


def test_property_without_families_the_order_is_unchanged():
    for seed in range(200):
        rng = random.Random(seed)
        deck, _ = _random_deck(rng)
        own_roots = {statement['id']: statement['id'] for statement in deck}

        assert _ids(space_by_family(deck, None)) == _ids(deck), seed
        assert _ids(space_by_family(deck, {})) == _ids(deck), seed
        assert _ids(space_by_family(deck, own_roots)) == _ids(deck), seed


def test_property_served_through_the_explore_state():
    """The same property through `build_explore_state`, with meta statements and seeds:
    meta first in their own order, then every other statement exactly once, spaced."""
    for seed in range(60):
        rng = random.Random(10_000 + seed)
        deck, families = _random_deck(rng)
        payload = {}
        for statement in deck:
            payload[str(statement['id'])] = {
                'id': statement['id'], 'text': statement['text'],
                'is_seed': rng.random() < 0.2,
            }
        meta_ids = rng.sample(range(10, 99), rng.randint(0, 2))
        for meta_id in meta_ids:
            payload[str(meta_id)] = {'id': meta_id, 'text': 'Meta', 'is_meta': True}
        ordering_key = f'random-{seed}'

        answered: list[int] = []
        while True:
            state = build_explore_state(
                statements_payload=payload,
                participant_payload={'votes': answered, 'statements': []},
                ordering_key=ordering_key, new_statement_unlock_at=10,
                new_statement_max=3, new_statements_used=0, families=families,
            )
            if state['currentStatement'] is None:
                break
            answered.append(state['currentStatement']['id'])

        pin = _pin_order(payload, ordering_key)
        assert answered[:len(meta_ids)] == pin[:len(meta_ids)], seed
        rest = answered[len(meta_ids):]
        assert sorted(rest) == sorted(_ids(deck)), seed
        if max(Counter(families.values()).values()) <= math.ceil(len(deck) / 2):
            assert _adjacent_pairs(rest, families) == [], seed


# ── the app.py wiring: the route reads the families from the database ──────────

# For the fixtures below (participant 99999, the first conversation of a fresh test DB)
# the pin order of these four statements is 21, 22, 23, 24: the two family members 21 and
# 22 land back to back. The route-level test asserts that precondition.
WIRING_DECK = {
    '21': {'id': 21, 'text': 'The original'},
    '22': {'id': 22, 'text': 'A rewording of it'},
    '23': {'id': 23, 'text': 'Something else'},
    '24': {'id': 24, 'text': 'And something else'},
}


def _response(payload=None, *, status=200, cookies=None):
    response = MagicMock()
    response.status_code = status
    response.ok = status < 400
    response.content = b'{}' if payload is not None else b''
    response.json.return_value = payload or {}
    response.cookies = cookies or {}
    return response


def test_explore_route_skips_a_family_member_the_plain_order_would_serve(
    auth_client, participant, conversation, app,
):
    ordering_key = f'{participant.xid}:{conversation.id}'
    assert _pin_order(WIRING_DECK, ordering_key)[:2] == [21, 22]

    participation = Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='family-otter',
    )
    db.session.add(participation)
    conversation.phase_submission = True
    # 22 is a rewording of 21, so both share the family rooted at 21.
    db.session.add(StatementProvenance(
        conversation_id=conversation.id,
        polis_statement_id=22,
        derived_from_tid=21,
    ))
    db.session.commit()

    # The participant answered 21, so the plain pin order would serve its own family next.
    with (
        patch('app.polis_http.post', return_value=_response(
            {'csrf_token': 'upstream-csrf'}, cookies={'session': 'upstream-cookie'},
        )),
        patch('app.polis_http.get', side_effect=[
            _response(WIRING_DECK),
            _response({'votes': [21], 'statements': []}),
        ]),
    ):
        response = auth_client.get('/api/v1/conversations/test-conv/explore')

    assert response.status_code == 200
    served = response.get_json()['data']['currentStatement']
    # The pin order would have served 22 here, the rewording of the statement just answered.
    assert served['id'] == 23
    assert served['text'] == 'Something else'


def test_family_roots_come_from_one_query_and_are_cycle_safe(app, conversation):
    from app import _lineage_group, _statement_family_roots

    db.session.add(StatementProvenance(
        conversation_id=conversation.id, polis_statement_id=31, derived_from_tid=30,
    ))
    db.session.add(StatementProvenance(
        conversation_id=conversation.id, polis_statement_id=32, derived_from_tid=31,
    ))
    db.session.commit()
    # A real cycle: 30 → 32 closes 32 → 31 → 30 → 32. And 34 hangs under the cycle.
    db.session.add(StatementProvenance(
        conversation_id=conversation.id, polis_statement_id=30, derived_from_tid=32,
    ))
    db.session.add(StatementProvenance(
        conversation_id=conversation.id, polis_statement_id=34, derived_from_tid=32,
    ))
    # A row pointing at a statement that has no row at all: the walk stops there.
    db.session.add(StatementProvenance(
        conversation_id=conversation.id, polis_statement_id=33, derived_from_tid=99,
    ))
    db.session.commit()

    queries: list[str] = []

    def count(connection, cursor, statement, *args):
        queries.append(str(statement))

    def endless(signum, frame):
        raise AssertionError('the walk did not terminate on a provenance cycle')

    # Termination: a walk that loops on the cycle is stopped after 5 s and fails the test.
    previous_handler = signal.signal(signal.SIGALRM, endless)
    signal.alarm(5)
    event.listen(db.engine, 'before_cursor_execute', count)
    try:
        roots = _statement_family_roots(conversation.id)
        lineage = _lineage_group(conversation.id, 32)
    finally:
        event.remove(db.engine, 'before_cursor_execute', count)
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)

    # Every member of the cycle, and what hangs under it, gets the same root (the cycle's
    # smallest id), whichever member the walk starts from.
    assert roots == {30: 30, 31: 30, 32: 30, 34: 30, 33: 99}
    # `_lineage_group` keeps its behaviour: it stops where the cycle closes.
    assert lineage == [32, 31, 30]
    provenance_queries = [query for query in queries if 'statement_provenance' in query]
    assert len(provenance_queries) == 2, provenance_queries

# ── p526-1: a deck that changes mid-session ─────────────────────────────────────
#
# The pin of a deck that changes (a rewording added, a statement moderated out) re-spaces
# every statement, answered ones included. The first unanswered statement of that new
# order can then be a family member of the statement the participant has just answered.

def _deck_payload(ids):
    return {str(statement_id): {'id': statement_id, 'text': f'Statement {statement_id}'}
            for statement_id in ids}


def _read_then_vote_then_read(auth_client, participant, conversation, *, before, votes_before,
                              answer, after, provenance_after=()):
    """Read the deck, vote on the card served, change the deck, read again.

    Returns (served on the first read, served on the second read)."""
    db.session.add(Participation(
        participant_id=participant.id, conversation_id=conversation.id,
        pseudonym='family-heron',
    ))
    conversation.phase_submission = True
    db.session.commit()
    session_response = _response(
        {'csrf_token': 'upstream-csrf'}, cookies={'session': 'upstream-cookie'},
    )
    upstream_participant = {'votes': list(votes_before), 'statements': []}
    with (
        patch('app.polis_http.post', return_value=session_response),
        patch('app.polis_http.get', side_effect=[
            _response(_deck_payload(before)), _response(upstream_participant),
            _response(_deck_payload(before)), _response(upstream_participant),
        ]),
        patch('app.polis_http.put', return_value=_response({})),
    ):
        first = auth_client.get('/api/v1/conversations/test-conv/explore')
        vote = auth_client.put(
            f'/api/v1/conversations/test-conv/statements/{answer}/vote',
            json={'choice': 'agree'},
        )
    assert first.status_code == 200
    assert vote.status_code == 200

    for child, parent in provenance_after:
        db.session.add(StatementProvenance(
            conversation_id=conversation.id, polis_statement_id=child,
            derived_from_tid=parent,
        ))
    db.session.commit()
    with (
        patch('app.polis_http.post', return_value=session_response),
        patch('app.polis_http.get', side_effect=[
            _response(_deck_payload(after)),
            _response({'votes': [*votes_before, answer], 'statements': []}),
        ]),
    ):
        second = auth_client.get('/api/v1/conversations/test-conv/explore')
    assert second.status_code == 200
    return (first.get_json()['data']['currentStatement']['id'],
            second.get_json()['data']['currentStatement']['id'])


def test_a_rewording_added_mid_session_is_not_served_after_its_sibling(
    auth_client, participant, conversation,
):
    """Pin [X, A1, A2, Y]; X answered, A1 served and answered; then A3, a rewording of A1,
    arrives with a pin between A2 and Y. The next card must not be from family A."""
    ordering_key = f'{participant.xid}:{conversation.id}'
    x, a1, a2, a3, y = 236, 202, 239, 208, 217
    assert _pin_order(_deck_payload([x, a1, a2, a3, y]), ordering_key) == [x, a1, a2, a3, y]
    db.session.add(StatementProvenance(
        conversation_id=conversation.id, polis_statement_id=a2, derived_from_tid=a1,
    ))
    db.session.commit()

    first, second = _read_then_vote_then_read(
        auth_client, participant, conversation,
        before=[x, a1, a2, y], votes_before=[x], answer=a1,
        after=[x, a1, a2, a3, y], provenance_after=[(a3, a1)],
    )

    assert first == a1
    assert second not in {a1, a2, a3}, (
        f'{second} is a family member of {a1}, the statement just answered'
    )
    assert second == y


def test_a_statement_moderated_out_mid_session_does_not_pull_a_sibling_forward(
    auth_client, participant, conversation,
):
    """Pin [X, Y, A1, A2, A3, Z, B]; X and Y answered, A1 served and answered; then B is
    moderated out. One statement fewer makes family A critical one step earlier, so the
    re-spaced deck puts A1 before Y and serves A2 right after the A1 just answered.

    (The plain [A1, B, A2] case cannot be separated once B is gone: A2 is all that is left.)"""
    ordering_key = f'{participant.xid}:{conversation.id}'
    x, y, a1, a2, a3, z, b = 232, 222, 238, 231, 207, 228, 215
    assert _pin_order(_deck_payload([x, y, a1, a2, a3, z, b]), ordering_key) == \
        [x, y, a1, a2, a3, z, b]
    for child in (a2, a3):
        db.session.add(StatementProvenance(
            conversation_id=conversation.id, polis_statement_id=child, derived_from_tid=a1,
        ))
    db.session.commit()

    first, second = _read_then_vote_then_read(
        auth_client, participant, conversation,
        before=[x, y, a1, a2, a3, z, b], votes_before=[x, y], answer=a1,
        after=[x, y, a1, a2, a3, z],
    )

    assert first == a1
    assert second not in {a1, a2, a3}, (
        f'{second} is a family member of {a1}, the statement just answered'
    )
    assert second == z


def test_the_window_is_seeded_with_the_roots_served_just_before():
    """`last_roots`: the first statement of the deck keeps its distance from the last one
    served, even when no family has two members left in the deck."""
    deck = _deck([61, 3])

    assert _ids(space_by_family(deck, {61: 60})) == [61, 3]
    assert _ids(space_by_family(deck, {61: 60}, last_roots=[60])) == [3, 61]
    assert _ids(space_by_family(deck, {61: 60}, last_roots=[3])) == [61, 3]
    # One statement left: the rule cannot hold, and it is still served.
    assert _ids(space_by_family(_deck([61]), {61: 60}, last_roots=[60])) == [61]


def test_property_recorded_answers_serve_the_same_sequence_on_a_static_deck():
    """Spacing only the unanswered statements, seeded from the last answer, gives the rest
    of the full deck's order: with or without a record of the answers, nothing changes."""
    for seed in range(120):
        rng = random.Random(20_000 + seed)
        deck, families = _random_deck(rng)
        payload = {str(statement['id']): {'id': statement['id'], 'text': statement['text']}
                   for statement in deck}
        ordering_key = f'static-{seed}'

        def read(answered, recent):
            return build_explore_state(
                statements_payload=payload,
                participant_payload={'votes': answered, 'statements': []},
                ordering_key=ordering_key, new_statement_unlock_at=10,
                new_statement_max=3, new_statements_used=0, families=families,
                recent_answers=recent,
            )['currentStatement']

        answered: list[int] = []
        while (current := read(answered, None)) is not None:
            assert read(answered, answered[-1:]) == current, (seed, answered)
            answered.append(current['id'])
        assert sorted(answered) == sorted(_ids(deck)), seed


def test_the_recorded_last_answer_steers_the_next_statement():
    """The pure-function form of p526-1: the deck changed, so the full deck's order says the
    last answer was X, but the participant answered A1 last. The record wins."""
    families = {201: 201, 202: 201, 203: 201}
    payload = {str(statement_id): {'id': statement_id, 'text': f'Statement {statement_id}'}
               for statement_id in (100, 201, 202, 203, 300)}
    ordering_key = next(
        f'key-{index}' for index in range(10_000)
        if _pin_order(payload, f'key-{index}') == [100, 201, 202, 203, 300]
    )

    def read(recent):
        return build_explore_state(
            statements_payload=payload,
            participant_payload={'votes': [100, 201], 'statements': []},
            ordering_key=ordering_key, new_statement_unlock_at=10,
            new_statement_max=3, new_statements_used=0, families=families,
            recent_answers=recent,
        )['currentStatement']['id']

    # Without a record, the full deck [201, 100, 202, 300, 203] says 100 came last.
    assert read(None) == 202
    assert read([100, 201]) == 300
    # A recorded answer that is not among the answered statements is ignored.
    assert read([999]) == 202
