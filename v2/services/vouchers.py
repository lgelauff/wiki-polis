"""Voucher code generation and redemption (#368)."""

import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone

from flask import current_app

from db import VoucherBatch, VoucherCode, db

# Crockford base32: no I (eye), L (ell), O (oh), U (you)
_CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
_CROCKFORD_BITS = 60  # 12 chars × 5 bits
_VOUCHER_RESERVATION_MINUTES = 30

_VOUCHER_CODE_RE = re.compile(r'^[0-9A-HJKMNP-TV-Z]{12}$')


def _voucher_hmac_secret() -> str:
    return str(current_app.config.get('VOUCHER_HMAC_SECRET')
               or current_app.config['SECRET_KEY'])


def normalize_code(code: str) -> str:
    """Upper-case, strip whitespace and hyphens."""
    return re.sub(r'[\s\-]+', '', code).upper()


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
    import secrets
    bits = secrets.randbits(_CROCKFORD_BITS)
    chars = []
    for _ in range(12):
        bits, rem = divmod(bits, 32)
        chars.append(_CROCKFORD[rem])
    return ''.join(chars)


def generate_voucher_codes(batch: VoucherBatch, count: int) -> list[str]:
    """Generate *count* voucher codes and persist them in *batch*."""
    secret = _voucher_hmac_secret()
    codes: list[str] = []
    vouchers: list[VoucherCode] = []
    for _ in range(count):
        raw = generate_voucher_code()
        codes.append(raw)
        vouchers.append(VoucherCode(
            batch_id=batch.id,
            code_hmac=hmac.new(
                secret.encode(),
                f'voucher:{batch.conversation_id}:{raw}'.encode(),
                hashlib.sha256,
            ).hexdigest(),
        ))
    db.session.add_all(vouchers)
    return codes


def lookup_voucher(code: str, conversation_id: int) -> VoucherCode | None:
    """Find a voucher row by normalised code and conversation scope."""
    digest = voucher_code_hmac(code, conversation_id)
    return VoucherCode.query.filter_by(code_hmac=digest).first()


def reserve_voucher(voucher: VoucherCode) -> None:
    """Mark a voucher as reserved for 30 minutes."""
    voucher.status = 'reserved'
    voucher.reserved_until = datetime.now(timezone.utc) + timedelta(
        minutes=_VOUCHER_RESERVATION_MINUTES,
    )


def redeem_voucher(voucher: VoucherCode, participant_id: int) -> None:
    """Mark a voucher as redeemed and link the participant."""
    voucher.status = 'redeemed'
    voucher.participant_id = participant_id
    voucher.redeemed_at = datetime.now(timezone.utc)
    voucher.reserved_until = None


def revoke_voucher(voucher: VoucherCode) -> None:
    """Mark a voucher as revoked."""
    voucher.status = 'revoked'
    voucher.revoked_at = datetime.now(timezone.utc)
    voucher.reserved_until = None