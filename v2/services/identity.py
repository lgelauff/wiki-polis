"""Participant identity operations.

The stored xid is a durable bridge to Polis. It is minted once and must not be
re-derived for an existing participant: changing the derivation secret would otherwise
silently orphan that participant's Polis history (GitHub #290).
"""

from db import Participant


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
            xid=new_xid,
            xid_key_version=xid_key_version,
        )

    existing.mw_username = mw_username
    return existing
