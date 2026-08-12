"""Durable idempotency primitives for non-idempotent browser commands."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from db import CommandReceipt, db

_KEY_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$')


class InvalidIdempotencyKey(ValueError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


class CommandOutcomeUnknown(RuntimeError):
    pass


@dataclass(frozen=True)
class Reservation:
    receipt: CommandReceipt
    replay: dict | None


def request_digest(payload: dict) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_idempotency_key(idempotency_key: str) -> None:
    if _KEY_RE.fullmatch(idempotency_key or '') is None:
        raise InvalidIdempotencyKey(idempotency_key)


def reserve_command(*, participant_id: int, conversation_id: int,
                    command: str, idempotency_key: str,
                    request_hash: str) -> Reservation:
    validate_idempotency_key(idempotency_key)
    lookup = dict(
        participant_id=participant_id,
        conversation_id=conversation_id,
        command=command,
        idempotency_key=idempotency_key,
    )
    existing = CommandReceipt.query.filter_by(**lookup).first()
    if existing is None:
        receipt = CommandReceipt(**lookup, request_hash=request_hash, state='pending')
        db.session.add(receipt)
        try:
            db.session.commit()
            return Reservation(receipt=receipt, replay=None)
        except IntegrityError:
            db.session.rollback()
            existing = CommandReceipt.query.filter_by(**lookup).one()
    if existing.request_hash != request_hash:
        raise IdempotencyConflict('The key was already used for another request.')
    if existing.state == 'completed' and isinstance(existing.response, dict):
        return Reservation(receipt=existing, replay=existing.response)
    raise CommandOutcomeUnknown('The original command outcome is not known yet.')


def release_reservation(receipt: CommandReceipt) -> None:
    db.session.delete(receipt)
    db.session.commit()


def complete_command(receipt: CommandReceipt, response: dict) -> None:
    receipt.state = 'completed'
    receipt.response = response
    receipt.completed_at = datetime.now(timezone.utc)
