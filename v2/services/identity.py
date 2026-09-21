"""Participant identity operations.

The stored xid is a durable bridge to Polis. It is minted once and must not be
re-derived for an existing participant: changing the derivation secret would otherwise
silently orphan that participant's Polis history (GitHub #290).
"""

from db import (
    ACCOUNT_KIND_VOUCHER,
    ACCOUNT_KIND_WIKIMEDIA,
    Participant,
)


def reconcile_participant_login(
    existing: Participant | None,
    *,
    mw_user_id: int,
    mw_username: str,
    new_xid: str,
    xid_key_version: int,
) -> Participant:
    """Create a participant or refresh mutable Wikimedia profile data.

    ``new_xid`` and ``xid_key_version`` are used only for a new row. For an
    existing row both fields are deliberately preserved as durable identifiers.
    The caller owns the transaction so this operation composes with OAuth, local
    development login, and future API commands.
    """
    if existing is None:
        return Participant(
            mw_user_id=mw_user_id,
            mw_username=mw_username,
            account_kind=ACCOUNT_KIND_WIKIMEDIA,
            xid=new_xid,
            xid_key_version=xid_key_version,
        )

    existing.mw_username = mw_username
    return existing


def create_voucher_participant(
    *,
    conversation_id: int,
    xid: str,
    xid_key_version: int = 2,
) -> Participant:
    """Build a new, conversation-scoped voucher participant.

    Voucher redemption must always take this new-row path. In particular, it must
    not look up or refresh a Wikimedia participant: an existing participant's xid
    is a durable Polis identity and must never be re-derived (#290).

    The caller owns the transaction and adds/commits the returned row. ``xid`` is
    supplied by the caller after deriving the namespaced ``voucher:<random>``
    subject with the application's normal xid helper.
    """
    if conversation_id is None:
        raise ValueError('voucher participants require a conversation_id')
    return Participant(
        mw_user_id=None,
        mw_username=None,
        account_kind=ACCOUNT_KIND_VOUCHER,
        conversation_id=conversation_id,
        xid=xid,
        xid_key_version=xid_key_version,
    )
