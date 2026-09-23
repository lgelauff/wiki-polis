"""Voucher code generation, import and redemption (#368).

A code creates exactly one account and thereafter authenticates that account:
it is single-use for *joining* and reusable for *resuming* (#412). Expiry limits
redemption only; it never ends an account that already redeemed.

Codes are either generated here (12 characters of Crockford base32) or imported
from a list the organizers made themselves, which is how the same codes can work
in several processes: only HMACs are stored, so a generated code can never be
copied to another process afterwards. Entry therefore accepts any code shape and
simply looks it up.
"""

import hashlib
import hmac
import re
import secrets
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from flask import current_app
from sqlalchemy import and_, or_, update

from db import ACCOUNT_KIND_VOUCHER, Participant, VoucherBatch, VoucherCode, db

# Crockford base32: no I (eye), L (ell), O (oh), U (you)
_CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
_CROCKFORD_BITS = 60  # 12 chars × 5 bits
# Letters Crockford base32 leaves out because they are easily misread (I, L, O)
# or produce accidental words (U). Input is never rewritten: an imported code may
# well contain them. When a code containing them is not found, the entry page
# says so, so the holder can check what they typed.
_EXCLUDED_LETTERS = frozenset('ILOU')

# Any code, after normalize_code(): generated codes are 12 characters, imported
# ones 5-64 letters and digits. Entry refuses a shorter input up front, since it
# cannot be any code. Imported codes are only as hard to guess as the organizers
# made them; the minimum length is a floor, not a guarantee (a sequential list
# such as WIKI0001, WIKI0002 is trivially guessed), hence weak_codes().
CODE_MIN_LENGTH = 5
CODE_MAX_LENGTH = 64
_IMPORTED_CODE_RE = re.compile(rf'^[0-9A-Z]{{{CODE_MIN_LENGTH},{CODE_MAX_LENGTH}}}$')
# Below this, or digits only, an imported code is easy to guess within the
# failed-attempt budget: 200 five-digit PINs give about 170 hits a day.
WEAK_CODE_LENGTH = 8


def _voucher_hmac_secret() -> str:
    return str(current_app.config.get('VOUCHER_HMAC_SECRET')
               or current_app.config['SECRET_KEY'])


def _utcnow() -> datetime:
    """Naive UTC, matching how the DateTime columns store and return values."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def normalize_code(code: str) -> str:
    """Upper-case, strip whitespace and hyphens."""
    return re.sub(r'[\s\-]+', '', code).upper()


def is_too_short(code: str) -> bool:
    """Whether *code* is shorter than any code can be (after normalising)."""
    return len(normalize_code(code)) < CODE_MIN_LENGTH


def weak_codes(codes: Iterable[str]) -> list[str]:
    """Normalised codes that are digits only or shorter than WEAK_CODE_LENGTH."""
    weak = []
    for code in codes:
        normalized = normalize_code(code)
        if normalized.isdigit() or len(normalized) < WEAK_CODE_LENGTH:
            weak.append(normalized)
    return weak


def has_excluded_letters(code: str) -> bool:
    """Whether *code* uses a letter generated codes never contain (I, L, O, U)."""
    return not _EXCLUDED_LETTERS.isdisjoint(normalize_code(code))


def voucher_code_hmac(code: str, conversation_id: int) -> str:
    """HMAC-SHA256 digest scoped to a conversation.

    Scoping by conversation_id makes the same raw code string produce
    distinct digests in different processes, so an organizer can re-use
    a code without collisions.
    """
    secret = _voucher_hmac_secret()
    normalized = normalize_code(code)
    payload = f'voucher:{conversation_id}:{normalized}'
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def generate_voucher_code() -> str:
    """12-character Crockford base32 (~60 bits of entropy): no I, L, O or U."""
    bits = secrets.randbits(_CROCKFORD_BITS)
    chars = []
    for _ in range(12):
        bits, rem = divmod(bits, 32)
        chars.append(_CROCKFORD[rem])
    return ''.join(chars)


def _batch_conversation_id(batch: VoucherBatch) -> int:
    """The batch's conversation id, also for a batch built with ``conversation=``
    and not yet flushed: the HMAC must never be taken over ``None``."""
    conversation_id = batch.conversation_id
    if conversation_id is None and batch.conversation is not None:
        conversation_id = batch.conversation.id
    if conversation_id is None:
        raise ValueError('a voucher batch needs a saved conversation')
    return conversation_id


def generate_voucher_codes(batch: VoucherBatch, count: int) -> list[str]:
    """Generate *count* voucher codes and add them to *batch*.

    The raw codes are returned once, for the organizer to hand out; only their
    HMACs are stored. The caller commits.
    """
    conversation_id = _batch_conversation_id(batch)
    codes = [generate_voucher_code() for _ in range(count)]
    db.session.add_all([
        VoucherCode(batch=batch, code_hmac=voucher_code_hmac(raw, conversation_id))
        for raw in codes
    ])
    return codes


@dataclass
class VoucherImport:
    """What an import added and what it left out, by normalised code."""

    added: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def import_voucher_codes(batch: VoucherBatch, lines: Iterable[str]) -> VoucherImport:
    """Add organizer-supplied codes, one per line, to *batch*.

    Codes are normalised the same way entry is (case, spaces and hyphens do not
    matter) and must then be 5-64 letters and digits. A code that repeats within
    the list, or already exists in this conversation, is reported and skipped.
    Blank lines are ignored. The caller commits.
    """
    conversation_id = _batch_conversation_id(batch)
    result = VoucherImport()
    seen: set[str] = set()
    for line in lines:
        code = normalize_code(line)
        if not code:
            continue
        if _IMPORTED_CODE_RE.fullmatch(code) is None:
            result.rejected.append(code)
            continue
        if code in seen or lookup_voucher(code, conversation_id) is not None:
            result.duplicates.append(code)
            continue
        seen.add(code)
        result.added.append(code)
        db.session.add(VoucherCode(
            batch=batch, code_hmac=voucher_code_hmac(code, conversation_id),
        ))
    return result


def lookup_voucher(code: str, conversation_id: int) -> VoucherCode | None:
    """Find a voucher row by normalised code, within one conversation."""
    return (
        VoucherCode.query
        .join(VoucherBatch, VoucherCode.batch_id == VoucherBatch.id)
        .filter(
            VoucherCode.code_hmac == voucher_code_hmac(code, conversation_id),
            VoucherBatch.conversation_id == conversation_id,
        )
        .first()
    )


@dataclass(frozen=True)
class VoucherEntry:
    """What entering a code would do. ``invalid`` covers wrong, revoked,
    expired-unredeemed and in-flight codes alike, so a response never reveals
    which of them applies."""

    outcome: Literal['invalid', 'redeem', 'resume']
    voucher: VoucherCode | None = None
    participant: Participant | None = None


def _classify(voucher: VoucherCode | None, conversation_id: int) -> VoucherEntry:
    if voucher is None or voucher.status == 'revoked':
        return VoucherEntry('invalid')

    if voucher.status == 'redeemed':
        participant = (
            db.session.get(Participant, voucher.participant_id)
            if voucher.participant_id is not None else None
        )
        # A redeemed code whose account is gone never mints a second one.
        if (participant is None
                or participant.account_kind != ACCOUNT_KIND_VOUCHER
                or participant.conversation_id != conversation_id):
            return VoucherEntry('invalid')
        return VoucherEntry('resume', voucher, participant)

    now = _utcnow()
    expires_at = _naive_utc(voucher.expires_at)
    if expires_at is not None and expires_at <= now:
        return VoucherEntry('invalid')
    # A live reservation is someone else's in-flight entry; a lapsed one is free.
    reserved_until = _naive_utc(voucher.reserved_until)
    if voucher.status == 'reserved' and reserved_until is not None and reserved_until > now:
        return VoucherEntry('invalid')
    return VoucherEntry('redeem', voucher)


def classify_voucher(code: str, conversation_id: int) -> VoucherEntry:
    return _classify(lookup_voucher(code, conversation_id), conversation_id)


def redeem_voucher_code(
    voucher: VoucherCode,
    conversation_id: int,
    make_participant: Callable[[], Participant],
) -> Participant | None:
    """Claim *voucher* and create its account in one transaction.

    The claim is a conditional UPDATE, so of two concurrent first uses exactly
    one creates an account; the other resumes the winner's account rather than
    erroring. Returns ``None`` when the code is no longer usable.
    """
    voucher_id = voucher.id
    now = _utcnow()
    try:
        claimed = db.session.execute(
            update(VoucherCode)
            .where(
                VoucherCode.id == voucher_id,
                VoucherCode.participant_id.is_(None),
                or_(
                    VoucherCode.status == 'unused',
                    and_(VoucherCode.status == 'reserved',
                         VoucherCode.reserved_until <= now),
                ),
                or_(VoucherCode.expires_at.is_(None), VoucherCode.expires_at > now),
            )
            .values(status='redeemed', redeemed_at=now, reserved_until=None)
            .execution_options(synchronize_session=False)
        ).rowcount == 1

        if not claimed:
            db.session.rollback()
            current = db.session.get(VoucherCode, voucher_id, populate_existing=True)
            entry = _classify(current, conversation_id)
            return entry.participant if entry.outcome == 'resume' else None

        participant = make_participant()
        db.session.add(participant)
        db.session.flush()
        db.session.execute(
            update(VoucherCode)
            .where(VoucherCode.id == voucher_id)
            .values(participant_id=participant.id)
            .execution_options(synchronize_session=False)
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return participant


def revoke_voucher(voucher: VoucherCode) -> None:
    """Mark a voucher as revoked. The caller commits."""
    voucher.status = 'revoked'
    voucher.revoked_at = _utcnow()
    voucher.reserved_until = None
