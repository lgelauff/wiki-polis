"""Featured-statement administration projections and commands."""

from dataclasses import dataclass
from datetime import timezone

from sqlalchemy.exc import SQLAlchemyError

from services import reporting_rules


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


class ArgumentNotInFeaturedWorkspace(ValueError):
    pass


@dataclass(frozen=True)
class FeaturedSelectionResult:
    featured_id: int
    statement_id: int
    changed: bool


def agreement(agree: int, disagree: int, *, floor: int, mark_share: float) -> tuple[int | None, bool]:
    """The agreement share of agree + disagree responses, as the API serves it.

    Withheld (None) below `floor` agree + disagree responses: it is opinion data, which
    follows the floor in admin views too (owner, 2026-10-15). See
    services.reporting_rules.agreement.
    """
    return reporting_rules.agreement(agree, disagree, floor=floor, mark_share=mark_share)


def build_featured_workspace(
    *, conversation, confirmed, candidates, provenance_by_tid,
    statement_text_by_tid,
    recommendation: int, self_link: str, lifecycle_link: str,
    agreement_floor: int = 10, agreement_mark_share: float = 0.7,
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
        percent, marked = agreement(
            agree, disagree, floor=agreement_floor, mark_share=agreement_mark_share,
        )
        # Below the floor the split is withheld too, not only the share: the counts would
        # give the share straight back (owner, 2026-10-30, D6). Total responses stay.
        split = agree + disagree >= max(1, agreement_floor)
        projected_candidates.append({
            'statementId': int(row['tid']),
            'text': str(row.get('text') or ''),
            'seed': bool(row.get('is_seed')),
            'votes': {
                'agree': agree if split else None,
                'pass': int(row.get('n_pass') or 0) if split else None,
                'disagree': disagree if split else None,
                'total': int(row.get('n_votes') or 0),
                'agreementPercent': percent,
                'agreementMarked': marked,
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
        'phase': {
            'argumentMappingActive': bool(conversation.phase_argument_mapping),
            'informedVotingLive': bool(
                conversation.phase_informed_voting
                and conversation.phase6_polis_conversation_id
            ),
        },
        'guidance': {
            'recommendedCount': recommendation,
            'note': 'Preserve meaningful viewpoints; agreement percentage is descriptive, not a selection score.',
            'agreementFloor': agreement_floor,
            'agreementMarkShare': agreement_mark_share,
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


def set_featured_argument_visibility(
    *, argument, hidden: bool, session, audit,
) -> bool:
    changed = argument.hidden != hidden
    if not changed:
        return False
    argument.hidden = hidden
    session.commit()
    audit(argument.id, hidden)
    return True


def delete_featured_argument(*, argument, session, audit) -> None:
    argument_id = argument.id
    featured_id = argument.featured_statement_id
    session.delete(argument)
    session.commit()
    audit(argument_id, featured_id)
