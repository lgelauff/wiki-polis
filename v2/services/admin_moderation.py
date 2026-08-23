"""Admin moderation queue projection and flag-resolution command."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import nh3
from sqlalchemy.orm import joinedload

from db import ContentFlag, Conversation, Participant, db


def _utc_iso(value) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class AdminFlagRow:
    flag: ContentFlag
    category_label: str
    target_label: str
    target_text: str

    def to_api(self, *, review_link: str) -> dict:
        return {
            'id': self.flag.id,
            'status': self.flag.status,
            'category': self.flag.category,
            'categoryLabel': self.category_label,
            'detail': self.flag.detail,
            'flaggedAt': _utc_iso(self.flag.created_at),
            'target': {
                'type': self.flag.content_type,
                'id': (
                    self.flag.statement_tid
                    if self.flag.content_type == 'statement'
                    else self.flag.argument_id
                ),
                'label': self.target_label,
                'text': self.target_text,
                'reviewHref': review_link,
            },
            'resolution': ({
                'resolvedAt': _utc_iso(self.flag.resolved_at),
                'note': self.flag.resolution_note,
            } if self.flag.status == 'resolved' else None),
        }


@dataclass(frozen=True)
class AdminFlagQueue:
    conversation: Conversation
    rows: list[AdminFlagRow]
    statement_texts_available: bool

    @property
    def open_count(self) -> int:
        return sum(row.flag.status == 'open' for row in self.rows)

    def to_api(
        self, *, self_link: str, conversation_link: str,
        statement_review_link: str, argument_review_link: str,
    ) -> dict:
        projected = [
            row.to_api(review_link=(
                statement_review_link
                if row.flag.content_type == 'statement'
                else argument_review_link
            ))
            for row in self.rows
        ]
        return {
            'conversation': {
                'id': self.conversation.id,
                'slug': self.conversation.slug,
                'title': self.conversation.title,
            },
            'open': [row for row in projected if row['status'] == 'open'],
            'resolved': [row for row in projected if row['status'] == 'resolved'],
            'dataAvailability': {
                'statementText': self.statement_texts_available,
            },
            'capabilities': {'resolveFlags': True},
            'links': {'self': self_link, 'conversation': conversation_link},
        }


def build_admin_flag_queue(
    *, conversation: Conversation,
    read_statement_texts: Callable[[], dict[int, str]],
    statement_read_errors: tuple[type[Exception], ...],
    category_labels: dict[str, str],
) -> AdminFlagQueue:
    flags = (
        ContentFlag.query
        .filter_by(conversation_id=conversation.id)
        .options(joinedload(ContentFlag.argument))
        .order_by(ContentFlag.status, ContentFlag.created_at.desc())
        .all()
    )
    has_statement_flags = any(
        flag.content_type == 'statement' for flag in flags
    )
    statement_texts = {}
    statement_texts_available = True
    if has_statement_flags:
        try:
            statement_texts = read_statement_texts()
        except statement_read_errors:
            statement_texts_available = False
    rows = []
    for flag in flags:
        if flag.content_type == 'argument':
            target_text = flag.argument.body if flag.argument else 'Argument removed'
            target_label = f'Argument #{flag.argument_id}'
        else:
            target_text = statement_texts.get(
                flag.statement_tid, 'Statement text unavailable',
            )
            target_label = f'Statement #{flag.statement_tid}'
        rows.append(AdminFlagRow(
            flag=flag,
            category_label=category_labels.get(flag.category, flag.category),
            target_label=target_label,
            target_text=target_text,
        ))
    return AdminFlagQueue(
        conversation=conversation,
        rows=rows,
        statement_texts_available=statement_texts_available,
    )


class FlagNotInConversation(LookupError):
    pass


@dataclass(frozen=True)
class FlagResolutionResult:
    flag: ContentFlag
    changed: bool


def resolve_content_flag(
    *, conversation: Conversation, flag_id: int, note: str | None,
    actor: Participant | None, audit,
) -> FlagResolutionResult:
    flag = (
        ContentFlag.query
        .filter_by(id=flag_id, conversation_id=conversation.id)
        .with_for_update()
        .first()
    )
    if flag is None:
        raise FlagNotInConversation()
    if flag.status == 'resolved':
        db.session.commit()
        return FlagResolutionResult(flag=flag, changed=False)

    clean_note = nh3.clean((note or '').strip(), tags=frozenset())[:1000]
    flag.status = 'resolved'
    flag.resolved_at = datetime.now(timezone.utc)
    flag.resolved_by_id = actor.id if actor else None
    flag.resolution_note = clean_note or None
    db.session.commit()
    audit(
        'content_flag.resolve',
        conv_id=conversation.id,
        target_type='content_flag',
        target_id=flag.id,
        content_type=flag.content_type,
    )
    return FlagResolutionResult(flag=flag, changed=True)
