"""Voucher code generation and redemption (#368).

A code creates exactly one account and thereafter authenticates that account:
it is single-use for *joining* and reusable for *resuming* (#412). Expiry limits
redemption only; it never ends an account that already redeemed.
"""

import hashlib
import hmac
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from flask import current_app
from sqlalchemy import and_, or_, update

from db import ACCOUNT_KIND_VOUCHER, Participant, VoucherBatch, VoucherCode, db

# Crockford base32: no I (eye), L (ell), O (oh), U (you)
_CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
_CROCKFORD_BITS = 60  # 12 chars × 5 bits
# Letters Crockford base32 leaves out because they are easily misread (I, L, O)
# or produce accidental words (U). Input is never rewritten; a code containing
# them is refused with its own message, so the holder can check what they typed.
_EXCLUDED_LETTERS = frozenset('ILOU')

_VOUCHER_CODE_RE = re.compile(r'^[0-9A-HJKMNP-TV-Z]{12}$')


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


def has_excluded_letters(code: str) -> bool:
    """Whether *code* uses a letter voucher codes never contain (I, L, O, U)."""
    return not _EXCLUDED_LETTERS.isdisjoint(normalize_code(code))


def is_well_formed(code: str) -> bool:
    return _VOUCHER_CODE_RE.fullmatch(normalize_code(code)) is not None


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
    """12-character Crockford base32 (~60 bits of entropy).

    Generated code conforms to ``_VOUCHER_CODE_RE``: no I, L, O, or U.
    """
    bits = secrets.randbits(_CROCKFORD_BITS)
    chars = []
    for _ in range(12):
        bits, rem = divmod(bits, 32)
        chars.append(_CROCKFORD[rem])
    return ''.join(chars)


def generate_voucher_codes(batch: VoucherBatch, count: int) -> list[str]:
    """Generate *count* voucher codes and add them to *batch*.

    The raw codes are returned once, for the organizer to hand out; only their
    HMACs are stored. The caller commits.
    """
    codes = [generate_voucher_code() for _ in range(count)]
    db.session.add_all([
        VoucherCode(batch=batch, code_hmac=voucher_code_hmac(raw, batch.conversation_id))
        for raw in codes
    ])
    return codes


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
