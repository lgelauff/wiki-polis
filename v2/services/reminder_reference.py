"""The reference in every bot wiki-mail (#622).

A reply to a wiki-mail from the bot reaches the bot's own address, and the wiki
cannot set a reply address per message, so the message itself says what it was:
``Proto K7 ABCDEFGHI-JKLMNOPQR-STUVWXYZ``. ``K7`` names the key; the rest is
eight bytes (what the message was and its row) encrypted with that key.

What the encryption is for: it does not protect a big secret. The reference
points to a delivery row and nothing more, and the key sits in our own database.
It keeps the reference meaningless to anyone reading or searching mail: a plain
id could be searched for, matched up or counted (how many messages Proto
sends), and a guessed reference matches nothing. And it links a sent mail
straight to its event on the backend, with no lookup table to keep.

- **Encryption:** AES key wrap with padding (RFC 5649, NIST SP 800-38F "KWP"),
  from the ``cryptography`` library. For eight bytes it is one AES-256 block
  over the bytes and a fixed check value; unwrapping checks that value, so a
  made-up or altered reference fails to unwrap and matches nothing. Nothing is
  stored on the row: the reference decrypts straight back to it.
- **What is encrypted:** a delivery's id for a reminder, or the send day for a
  test send (a test send has no row of its own that names its recipient). Never
  a username or a user id: the delivery leads to the account, so a reference
  stops pointing to a person once its delivery is unlinked (#576).
- **Keys:** one per UTC month, in their own table, created on first use. Each
  is deleted 90 days after its last use (``delete_unused_keys``, run by the
  daily batch); a key past that age is not used for lookups even before the
  job deletes it. After that the references it made match nothing.
- **Wiki-mail only:** talk pages are public and get no reference.

``lookup`` answers ``None`` for every reference that does not lead to a row:
made up, altered, its key deleted, or its row gone. The caller shows the same
"No match" for all of them. Nothing here logs a reference or what it points to.
"""

from __future__ import annotations

import base64
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from cryptography.hazmat.primitives.keywrap import (
    InvalidUnwrap, aes_key_unwrap_with_padding, aes_key_wrap_with_padding,
)
from sqlalchemy.exc import IntegrityError

from db import ReminderDelivery, ReminderReferenceKey, db

KEY_RETENTION = timedelta(days=90)
PREFIX = 'Proto'

# The first byte says what the other seven are.
KIND_DELIVERY = 1     # a reminder delivery's id
KIND_TEST_SEND = 2    # the send day (proleptic Gregorian ordinal) of a test send

_VALUE_MAX = 2 ** 56 - 1
_CODE_LENGTH = 26     # 16 bytes in base32, without padding
_MAX_INPUT = 2000
_CANDIDATE = re.compile(r'\bK(\d{1,9})[ \t:]+([A-Z2-7]+(?:-[A-Z2-7]+)*)(?![A-Z2-7-])')


@dataclass(frozen=True)
class LookupItem:
    conversation_id: int
    title: str
    reminder_type: str


@dataclass(frozen=True)
class LookupResult:
    kind: str                     # 'reminder' | 'test_send'
    send_day: date
    username: str | None = None   # None: the delivery no longer links to a person
    items: list[LookupItem] = field(default_factory=list)


def _month(now: datetime) -> str:
    return now.strftime('%Y-%m')


def _key_for(now: datetime) -> ReminderReferenceKey:
    """This month's key, created on first use; its last use is now."""
    month = _month(now)
    key = ReminderReferenceKey.query.filter_by(month=month).one_or_none()
    if key is None:
        try:
            with db.session.begin_nested():
                key = ReminderReferenceKey(month=month, key=secrets.token_bytes(32),
                                           created_at=now, last_used_at=now)
                db.session.add(key)
        except IntegrityError:
            # Another process made this month's key first.
            key = ReminderReferenceKey.query.filter_by(month=month).one()
    if key.last_used_at < now:
        key.last_used_at = now
    return key


def _encode(code: bytes) -> str:
    text = base64.b32encode(code).decode('ascii').rstrip('=')
    return f'{text[:9]}-{text[9:18]}-{text[18:]}'


def _make(kind: int, value: int, now: datetime) -> str:
    if not 0 <= value <= _VALUE_MAX:
        raise ValueError('value out of range')
    key = _key_for(now)
    plain = bytes([kind]) + value.to_bytes(7, 'big')
    wrapped = aes_key_wrap_with_padding(key.key, plain)
    # Committed before the message leaves, so a crash after the send cannot lose the
    # key that the sent reference needs.
    db.session.commit()
    return f'{PREFIX} K{key.id} {_encode(wrapped)}'


def for_delivery(delivery_id: int, now: datetime) -> str:
    """The reference for a reminder wiki-mail: its (first) delivery, encrypted."""
    return _make(KIND_DELIVERY, delivery_id, now)


def for_test_send(now: datetime) -> str:
    """The reference for a test wiki-mail: the day it was sent, encrypted."""
    return _make(KIND_TEST_SEND, now.date().toordinal(), now)


def subject_with(subject: str, reference: str) -> str:
    return f'{subject} [{reference}]'


def body_with(body: str, reference: str) -> str:
    """The reference as the body's last line: a reply that changes the subject usually
    still quotes the text. Outside the translated text, so no translation can drop it."""
    return f'{body}\n\nReference: {reference}'


def _decode(code: str) -> bytes | None:
    if len(code) != _CODE_LENGTH:
        return None
    try:
        raw = base64.b32decode(code + '=' * 6)
    except ValueError:
        return None
    # The last character carries two unused bits; a reference with them set is not
    # one Proto made, so it is refused rather than read as its neighbour.
    if _encode(raw).replace('-', '') != code:
        return None
    return raw


def _unwrap(text: str, now: datetime) -> tuple[int, int] | None:
    """(kind, value) for the first reference in ``text`` that decrypts, else None."""
    text = (text or '')[:_MAX_INPUT].upper()
    for match in list(_CANDIDATE.finditer(text))[:5]:
        wrapped = _decode(match.group(2).replace('-', ''))
        if wrapped is None:
            continue
        key = db.session.get(ReminderReferenceKey, int(match.group(1)))
        if key is None or key.last_used_at < now - KEY_RETENTION:
            continue
        try:
            plain = aes_key_unwrap_with_padding(key.key, wrapped)
        except InvalidUnwrap:
            continue
        if len(plain) == 8:
            return plain[0], int.from_bytes(plain[1:], 'big')
    return None


def lookup(text: str, now: datetime) -> LookupResult | None:
    """What a reference points to, or None for every kind of no match."""
    found = _unwrap(text, now)
    if found is None:
        return None
    kind, value = found
    if kind == KIND_TEST_SEND:
        try:
            return LookupResult(kind='test_send', send_day=date.fromordinal(value))
        except (ValueError, OverflowError):
            return None
    if kind != KIND_DELIVERY:
        return None
    first = db.session.get(ReminderDelivery, value)
    if first is None or first.channel != 'email':
        return None
    rows = [first] + (ReminderDelivery.query.filter_by(combined_into_id=first.id)
                      .order_by(ReminderDelivery.id).all())
    # The participant row is the account's, keyed by its Wikimedia user id and
    # refreshed at every sign-in, so a renamed account shows its current name.
    person = first.participation.participant if first.participation is not None else None
    return LookupResult(
        kind='reminder',
        send_day=first.reminder.send_day,
        username=person.mw_username if person is not None else None,
        items=[LookupItem(conversation_id=row.reminder.conversation_id,
                          title=row.reminder.conversation.title,
                          reminder_type=row.reminder.reminder_type) for row in rows],
    )


def delete_unused_keys(now: datetime) -> int:
    """Delete every key last used more than 90 days ago. Returns how many."""
    deleted = (ReminderReferenceKey.query
               .filter(ReminderReferenceKey.last_used_at < now - KEY_RETENTION)
               .delete(synchronize_session=False))
    db.session.commit()
    return deleted
