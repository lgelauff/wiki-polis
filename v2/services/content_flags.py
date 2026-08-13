"""Participant content-flag command shared by HTML and JSON adapters."""

from dataclasses import dataclass

import nh3

from db import FLAG_CATEGORIES, ContentFlag, Conversation, Participation, db


class InvalidFlag(ValueError):
    pass


@dataclass(frozen=True)
class FlagResult:
    flag: ContentFlag
    created: bool


def submit_content_flag(
    *, conversation: Conversation, participation: Participation,
    content_type: str, target_id: int, category: str, detail: str | None,
    audit,
) -> FlagResult:
    if content_type not in {'statement', 'argument'} or category not in FLAG_CATEGORIES:
        raise InvalidFlag()
    clean_detail = nh3.clean((detail or '').strip(), tags=frozenset())[:1000]
    if category == 'other' and not clean_detail:
        raise InvalidFlag()
    target = {'statement_tid': target_id} if content_type == 'statement' else {
        'argument_id': target_id,
    }
    lookup = {
        'conversation_id': conversation.id,
        'participant_id': participation.participant_id,
        'content_type': content_type,
        'category': category,
        'status': 'open',
        **target,
    }
    existing = ContentFlag.query.filter_by(**lookup).first()
    if existing is not None:
        return FlagResult(flag=existing, created=False)
    flag = ContentFlag(**lookup, detail=clean_detail or None)
    db.session.add(flag)
    db.session.commit()
    audit(
        'content_flag.create', conv_id=conversation.id,
        target_type=content_type, target_id=target_id, category=category,
    )
    return FlagResult(flag=flag, created=True)
