"""Participant informed-voting read model."""

import random

from sqlalchemy.orm import joinedload

from db import Argument, FeaturedStatement, Participation, db


def build_informed_voting_state(
    *, conversation_id: int, participation: Participation,
    participant_payload: dict,
) -> dict:
    """Build a stable, privacy-safe queue from local content and upstream progress."""
    featured = (
        FeaturedStatement.query
        .filter_by(conversation_id=conversation_id, confirmed_by_admin=True)
        .options(joinedload(FeaturedStatement.arguments).joinedload(Argument.votes))
        .all()
    )
    eligible = [item for item in featured if item.statement_text]
    by_id = {item.id: item for item in eligible}
    stored_order = list(participation.phase6_card_order or [])
    if participation.phase6_card_order is None:
        stored_order = list(by_id)
        random.shuffle(stored_order)
    appended = [item_id for item_id in by_id if item_id not in set(stored_order)]
    effective_order = [item_id for item_id in stored_order if item_id in by_id] + appended
    if participation.phase6_card_order != effective_order:
        participation.phase6_card_order = effective_order
        db.session.commit()

    stored_choices = participation.phase6_choices or {}
    voted_tids = {
        int(value) for value in participant_payload.get('votes', [])
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    }
    cards = []
    for featured_id in effective_order:
        item = by_id[featured_id]
        visible_arguments = [argument for argument in item.arguments if not argument.hidden]

        def arguments(side: str) -> list[dict]:
            ranked = sorted(
                (argument for argument in visible_arguments if argument.side == side),
                key=lambda argument: (-len(argument.votes), argument.id),
            )[:10]
            return [
                {'id': argument.id, 'body': argument.body, 'helpfulVotes': len(argument.votes)}
                for argument in ranked
            ]

        cards.append({
            'featuredStatementId': item.id,
            'statement': item.statement_text,
            'canVote': item.phase6_polis_statement_id is not None,
            'voted': (
                item.phase6_polis_statement_id is not None
                and item.phase6_polis_statement_id in voted_tids
            ),
            # What they chose, when we know it. Polis is authoritative for whether a
            # vote exists (voted_tids above); this only reports the value, which the
            # upstream read contract cannot carry. None for votes cast before this
            # was recorded -- those still show as answered, just without the choice.
            'choice': stored_choices.get(str(item.id)),
            'arguments': {'for': arguments('pro'), 'against': arguments('con')},
        })

    completed = sum(card['voted'] for card in cards)
    return {
        'cards': cards,
        'progress': {
            'completed': completed,
            'total': len(cards),
            'remaining': max(0, len(cards) - completed),
            'allDone': bool(cards) and completed == len(cards),
        },
    }
