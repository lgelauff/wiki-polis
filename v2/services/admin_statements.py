"""Privacy-safe statement administration projections and moderation commands."""

from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError


_MOD_BY_STATUS = {'hidden': -1, 'pending': 0, 'approved': 1}


def build_statement_workspace(
    *, conversation, buckets: dict[str, list[dict]], featured_tids: set[int],
    provenance_by_tid: dict, moderation_policy: str | None,
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
            'mode': moderation_policy,
            'newStatements': (
                None if moderation_policy is None
                else 'pending' if moderation_policy == 'moderate'
                else 'approved'
            ),
            'available': moderation_policy is not None,
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


class ModerationPolicyVerificationUnavailable(RuntimeError):
    pass


class ModerationPolicyUpstreamFailed(RuntimeError):
    pass


class ModerationPolicySaveFailed(RuntimeError):
    def __init__(self, *, outcome_unknown: bool):
        self.outcome_unknown = outcome_unknown


class SeedImportValidationFailed(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class SeedImportVerificationUnavailable(RuntimeError):
    pass


class SeedImportUpstreamFailed(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class SeedStatementValidationFailed(ValueError):
    pass


class SeedStatementParentNotFound(LookupError):
    def __init__(self, statement_id: int):
        self.statement_id = statement_id


class SeedStatementUpstreamFailed(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ModerationResult:
    statement_id: int
    status: str


@dataclass(frozen=True)
class ModerationPolicyResult:
    policy: str
    changed: bool
    reconciled_statement_ids: tuple[int, ...]


def resolved_moderation_policy(
    *, conversation, upstream_strict: bool | None,
) -> str | None:
    if conversation.statement_moderation_policy is not None:
        return conversation.statement_moderation_policy
    if upstream_strict is None:
        return None
    return 'moderate' if upstream_strict else 'auto_approve'


def set_statement_moderation_policy(
    *, conversation, policy: str, upstream_strict: bool | None,
    pending_statements: list[dict] | None, moderate_upstream,
    set_upstream_strict, session, audit_policy, audit_reconciled,
    upstream_errors: tuple[type[Exception], ...],
) -> ModerationPolicyResult:
    """Converge Polis on explicit per-statement decisions, then store the default."""
    if policy not in {'moderate', 'auto_approve'}:
        raise ValueError('Unknown statement moderation policy.')
    if upstream_strict is None or pending_statements is None:
        raise ModerationPolicyVerificationUnavailable()

    reconciled: list[int] = []
    upstream_changed = False
    if not upstream_strict:
        try:
            for row in pending_statements:
                statement_id = int(row['tid'])
                moderate_upstream(conversation.polis_id, statement_id, 1)
                reconciled.append(statement_id)
            set_upstream_strict(conversation.polis_id, True)
            upstream_changed = True
        except upstream_errors as exc:
            raise ModerationPolicyUpstreamFailed() from exc

    changed = conversation.statement_moderation_policy != policy
    conversation.statement_moderation_policy = policy
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise ModerationPolicySaveFailed(
            outcome_unknown=upstream_changed,
        ) from exc

    for statement_id in reconciled:
        audit_reconciled(statement_id)
    if changed or upstream_changed:
        audit_policy(policy, len(reconciled))
    return ModerationPolicyResult(
        policy=policy,
        changed=changed or upstream_changed,
        reconciled_statement_ids=tuple(reconciled),
    )


@dataclass(frozen=True)
class SeedImportResult:
    imported: int
    skipped_existing: int
    skipped_duplicate_input: int
    failed_upstream: int


@dataclass(frozen=True)
class SeedStatementResult:
    statement_id: int | None
    derived_from_id: int | None
    provenance_recorded: bool | None


def add_seed_statement(
    *, conversation, text: str, derived_from_id: int | None,
    sanitize, statement_text_map, add_seed, add_seed_return_id,
    record_provenance, audit, max_characters: int,
    upstream_errors: tuple[type[Exception], ...],
) -> SeedStatementResult:
    clean = sanitize(text.strip())
    if not clean or len(clean) > max_characters:
        raise SeedStatementValidationFailed()

    try:
        if derived_from_id is None:
            add_seed(conversation.polis_id, clean)
            audit(statement_id=None, derived_from_id=None)
            return SeedStatementResult(
                statement_id=None,
                derived_from_id=None,
                provenance_recorded=None,
            )

        text_by_id = statement_text_map(conversation.polis_id)
        if derived_from_id not in text_by_id:
            raise SeedStatementParentNotFound(derived_from_id)
        statement_id = add_seed_return_id(conversation.polis_id, clean)
    except SeedStatementParentNotFound:
        raise
    except upstream_errors as exc:
        raise SeedStatementUpstreamFailed(
            getattr(exc, 'admin_message', 'The voting service is unavailable.'),
        ) from exc

    provenance = record_provenance(
        conversation.id,
        statement_id,
        derived_from_id,
        parent_text=text_by_id[derived_from_id],
        new_text=clean,
    )
    audit(statement_id=statement_id, derived_from_id=derived_from_id)
    return SeedStatementResult(
        statement_id=statement_id,
        derived_from_id=derived_from_id,
        provenance_recorded=provenance is not None,
    )


def import_seed_statements(
    *, conversation, candidates: list[str], existing_buckets,
    sanitize, strip_formula_prefixes, bulk_add_seeds,
    max_rows: int, max_characters: int,
    upstream_errors: tuple[type[Exception], ...], audit,
) -> SeedImportResult:
    if not candidates:
        raise SeedImportValidationFailed('Provide at least one statement.')
    if len(candidates) > max_rows:
        raise SeedImportValidationFailed(
            f'Import at most {max_rows} statements at a time.',
        )
    if existing_buckets is None:
        raise SeedImportVerificationUnavailable()

    normalized = []
    seen_input: set[str] = set()
    skipped_duplicate_input = 0
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, str):
            raise SeedImportValidationFailed(
                f'Statement {index} must be text.',
            )
        raw = candidate.strip()
        if not raw:
            continue
        if len(raw) > max_characters:
            raise SeedImportValidationFailed(
                f'Statement {index} exceeds {max_characters} characters.',
            )
        clean = strip_formula_prefixes(sanitize(raw)).strip()
        if not clean:
            raise SeedImportValidationFailed(
                f'Statement {index} is empty after sanitization.',
            )
        key = clean.casefold()
        if key in seen_input:
            skipped_duplicate_input += 1
            continue
        seen_input.add(key)
        normalized.append(clean)
    if not normalized:
        raise SeedImportValidationFailed('Provide at least one non-empty statement.')

    existing = {
        str(row.get('txt') or '').strip().casefold()
        for bucket in existing_buckets for row in bucket
    }
    pending = [text for text in normalized if text.casefold() not in existing]
    skipped_existing = len(normalized) - len(pending)
    imported = failed = 0
    if pending:
        try:
            imported, failures = bulk_add_seeds(conversation.polis_id, pending)
        except upstream_errors as exc:
            raise SeedImportUpstreamFailed(
                getattr(exc, 'admin_message', 'The voting service is unavailable.'),
            ) from exc
        failed = len(failures)
        if not imported and failures:
            first_error = failures[0][1]
            raise SeedImportUpstreamFailed(
                getattr(
                    first_error, 'admin_message',
                    'The voting service is unavailable.',
                ),
            ) from first_error
    if imported:
        audit(
            imported=imported,
            skipped_existing=skipped_existing,
            skipped_duplicate_input=skipped_duplicate_input,
            failed_upstream=failed,
        )
    return SeedImportResult(
        imported=imported,
        skipped_existing=skipped_existing,
        skipped_duplicate_input=skipped_duplicate_input,
        failed_upstream=failed,
    )


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
