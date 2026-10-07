"""#504 — family spacing of the Explore deck.

A family is every statement that shares a root: the original and the rewordings derived
from it, directly or indirectly (`statement_provenance.derived_from_tid`). The deck must
never serve two of them back to back, or a rewording reads as a repeat of what the
participant just saw. A seed belongs to a family when it has a parent; meta statements are
not part of any family and keep their place at the front of the deck.

`FAMILY_MIN_DISTANCE = 1` today: at least one statement of another family in between.
"""
import hashlib
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event

from db import Participation, StatementProvenance, db
from services.explore import (FAMILY_MIN_DISTANCE, build_explore_state,
                              normalise_statements)

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
    served, _ = _served(families={2: 50, 50: 50, 51: 50, 52: 50})

    deck = served[1:]
    for previous, current in zip(deck, deck[1:]):
        assert {3: 3, 4: 4, 8: 8, 9: 9, 10: 10}.get(previous, previous) != \
            {3: 3, 4: 4, 8: 8, 9: 9, 10: 10}.get(current, current)


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


def test_a_larger_minimum_distance_is_honoured():
    """#505 will cut the spaced deck into packs; the constant has to be able to grow."""
    from services.explore import space_by_family

    statements = normalise_statements(DECK)
    deck = [statements[index] for index in (7, 8, 9, 3, 6)]
    spaced = [statement['id'] for statement in space_by_family(deck, FAMILIES, 2)]

    for index in range(len(spaced) - 2):
        assert FAMILIES[spaced[index]] != FAMILIES[spaced[index + 2]]


def _first_fitting_greedy(deck, families):
    """The simpler rule `space_by_family` was written against: always take the first
    remaining statement that fits the window. Kept here as the yardstick it beats."""
    remaining = list(deck)
    placed = []
    while remaining:
        window = [families.get(statement['id'], statement['id'])
                  for statement in placed[-FAMILY_MIN_DISTANCE:]]
        fitting = [position for position, statement in enumerate(remaining)
                   if families.get(statement['id'], statement['id']) not in window]
        placed.append(remaining.pop(fitting[0] if fitting else 0))
    return placed


def test_taking_the_first_statement_that_fits_would_break_the_rule():
    """The yardstick leaves two family members back to back where separation is possible:
    it spends the other families early, so a family clustered late in the deck runs out of
    separators. Here it serves 50 and 51 next to each other."""
    from services.explore import space_by_family

    deck = [statement for statement in normalise_statements(DECK)
            if not statement['isMeta']]
    greedy = [statement['id'] for statement in _first_fitting_greedy(deck, FAMILIES)]
    served = [statement['id'] for statement in space_by_family(deck, FAMILIES)]

    assert [previous for previous, current in zip(greedy, greedy[1:])
            if FAMILIES[previous] == FAMILIES[current]] == [50, 51]
    assert all(FAMILIES[previous] != FAMILIES[current]
               for previous, current in zip(served, served[1:]))


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
    # A row pointing at a statement that has no row at all: the walk stops there.
    db.session.add(StatementProvenance(
        conversation_id=conversation.id, polis_statement_id=33, derived_from_tid=99,
    ))
    db.session.commit()

    queries: list[str] = []

    def count(connection, cursor, statement, *args):
        queries.append(str(statement))

    event.listen(db.engine, 'before_cursor_execute', count)
    try:
        roots = _statement_family_roots(conversation.id)
        lineage = _lineage_group(conversation.id, 32)
    finally:
        event.remove(db.engine, 'before_cursor_execute', count)

    assert roots == {31: 30, 32: 30, 33: 99}
    assert lineage == [32, 31, 30]
    provenance_queries = [query for query in queries if 'statement_provenance' in query]
    assert len(provenance_queries) == 2, provenance_queries