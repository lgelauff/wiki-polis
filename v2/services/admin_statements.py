"""Privacy-safe statement administration projections and moderation commands."""

from dataclasses import dataclass


_MOD_BY_STATUS = {'hidden': -1, 'pending': 0, 'approved': 1}


def build_statement_workspace(
    *, conversation, buckets: dict[str, list[dict]], featured_tids: set[int],
    provenance_by_tid: dict, strict_moderation: bool | None,
    statements_available: bool, seed_lock_reason: str | None,
    max_import_rows: int, max_statement_characters: int,
    self_link: str, lifecycle_link: str,
) -> dict:
    def project(row: dict, status: str) -> dict:
        tid = int(row['tid'])
        provenance = provenance_by_tid.get(tid)
        return {
            'id': tid,
            'text': str(row.get('txt') or ''),
            'moderation': status,
            'seed': bool(row.get('is_seed')),
            'featured': tid in featured_tids,
            'votes': {
                'agree': int(row.get('agree_count') or 0),
                'pass': int(row.get('pass_count') or 0),
                'disagree': int(row.get('disagree_count') or 0),
            },
            'provenance': None if provenance is None else {
                'derivedFromId': provenance.derived_from_tid,
                'scores': [
                    {'model': score.model, 'value': score.value}
                    for score in provenance.scores
                ],
            },
        }

    return {
        'conversation': {
            'id': conversation.id,
            'slug': conversation.slug,
            'title': conversation.title,
        },
        'statements': {
            status: [project(row, status) for row in buckets[status]]
            for status in ('pending', 'approved', 'hidden')
        },
        'moderationPolicy': {
            'strict': strict_moderation,
            'available': strict_moderation is not None,
        },
        'dataAvailability': {'statements': statements_available},
        'seeding': {
            'allowed': seed_lock_reason is None,
            'lockReason': seed_lock_reason,
            'maxStatementsPerImport': max_import_rows,
            'maxCharactersPerStatement': max_statement_characters,
        },
        'capabilities': {
            'moderate': statements_available,
            'seed': seed_lock_reason is None,
        },
        'links': {'self': self_link, 'lifecycle': lifecycle_link},
    }


class LastFeaturedStatementProtected(RuntimeError):
    pass


class StatementModerationUpstreamFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class ModerationResult:
    statement_id: int
    status: str


def moderate_statement(
    *, conversation, statement_id: int, status: str,
    is_featured: bool, featured_count: int, moderate_upstream,
    audit, upstream_errors: tuple[type[Exception], ...],
) -> ModerationResult:
    if (status in {'hidden', 'pending'} and is_featured
            and conversation.phase_argument_mapping and featured_count <= 1):
        raise LastFeaturedStatementProtected()
    try:
        moderate_upstream(conversation.polis_id, statement_id, _MOD_BY_STATUS[status])
    except upstream_errors as exc:
        raise StatementModerationUpstreamFailed() from exc
    audit(statement_id, _MOD_BY_STATUS[status])
    return ModerationResult(statement_id=statement_id, status=status)
