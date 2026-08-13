"""Featured-statement administration projections and commands."""

from dataclasses import dataclass
from datetime import timezone

from sqlalchemy.exc import SQLAlchemyError


class FeaturedStatementNotFound(ValueError):
    pass


class FeaturedSourceUnavailable(RuntimeError):
    pass


class LastFeaturedSelectionProtected(RuntimeError):
    pass


class FeaturedRoundSyncFailed(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class FeaturedCommandOutcomeUnknown(RuntimeError):
    pass


@dataclass(frozen=True)
class FeaturedSelectionResult:
    featured_id: int
    statement_id: int
    changed: bool


def build_featured_workspace(
    *, conversation, confirmed, candidates, provenance_by_tid,
    statement_text_by_tid,
    recommendation: int, self_link: str, lifecycle_link: str,
) -> dict:
    def provenance(tid: int):
        row = provenance_by_tid.get(tid)
        return None if row is None else {
            'derivedFromId': row.derived_from_tid,
            'scores': [
                {'model': score.model, 'value': score.value}
                for score in row.scores
            ],
        }

    selected = []
    for row in confirmed:
        selected.append({
            'featuredId': row.id,
            'statementId': row.polis_statement_id,
            'text': row.statement_text or statement_text_by_tid.get(row.polis_statement_id),
            'systemSuggested': bool(row.suggested_by_system),
            'provenance': provenance(row.polis_statement_id),
            'arguments': [{
                'id': argument.id,
                'side': argument.side.value if hasattr(argument.side, 'value') else argument.side,
                'body': argument.body,
                'proposerPseudonym': argument.proposer_pseudonym,
                'hidden': bool(argument.hidden),
                'createdAt': (
                    argument.created_at.replace(
                        tzinfo=argument.created_at.tzinfo or timezone.utc,
                    ).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
                    if argument.created_at else None
                ),
            } for argument in row.arguments],
        })

    projected_candidates = []
    for row in candidates or []:
        agree = int(row.get('n_agree') or 0)
        disagree = int(row.get('n_disagree') or 0)
        position_votes = agree + disagree
        projected_candidates.append({
            'statementId': int(row['tid']),
            'text': str(row.get('text') or ''),
            'seed': bool(row.get('is_seed')),
            'votes': {
                'agree': agree,
                'pass': int(row.get('n_pass') or 0),
                'disagree': disagree,
                'total': int(row.get('n_votes') or 0),
                'agreementPercent': (
                    round(agree * 100 / position_votes, 1)
                    if position_votes else None
                ),
            },
            'provenance': provenance(int(row['tid'])),
        })
    return {
        'conversation': {
            'id': conversation.id, 'slug': conversation.slug,
            'title': conversation.title,
        },
        'selected': selected,
        'candidates': projected_candidates,
        'dataAvailability': {'candidates': candidates is not None},
        'guidance': {
            'recommendedCount': recommendation,
            'note': 'Preserve meaningful viewpoints; agreement percentage is descriptive, not a selection score.',
        },
        'capabilities': {'manage': True},
        'links': {'self': self_link, 'lifecycle': lifecycle_link},
    }


def select_featured_statement(
    *, conversation, statement_id: int, text: str,
    system_suggested: bool, find_existing, create_selection,
    session, sync_live_round, audit,
) -> FeaturedSelectionResult:
    existing = find_existing(statement_id)
    if existing is not None:
        return FeaturedSelectionResult(
            featured_id=existing.id,
            statement_id=statement_id,
            changed=False,
        )
    if not text:
        raise FeaturedStatementNotFound()
    row = create_selection(statement_id, text, system_suggested)
    session.add(row)
    sync_attempted = False
    if conversation.phase_informed_voting and conversation.phase6_polis_conversation_id:
        sync_attempted = True
        ok, message = sync_live_round(conversation)
        if not ok:
            session.rollback()
            raise FeaturedRoundSyncFailed(message)
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        if sync_attempted:
            raise FeaturedCommandOutcomeUnknown() from exc
        raise
    audit(row)
    return FeaturedSelectionResult(
        featured_id=row.id, statement_id=statement_id, changed=True,
    )


def remove_featured_statement(
    *, conversation, selection, selection_count: int,
    session, sync_live_round, audit,
) -> None:
    if conversation.phase_argument_mapping and selection_count <= 1:
        raise LastFeaturedSelectionProtected()
    session.delete(selection)
    sync_attempted = False
    if conversation.phase_informed_voting and conversation.phase6_polis_conversation_id:
        sync_attempted = True
        ok, message = sync_live_round(conversation)
        if not ok:
            session.rollback()
            raise FeaturedRoundSyncFailed(message)
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        if sync_attempted:
            raise FeaturedCommandOutcomeUnknown() from exc
        raise
    audit(selection.id)
