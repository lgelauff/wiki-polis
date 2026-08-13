"""Local metadata attached to idempotent Explore vote replacement."""

from datetime import datetime, timezone

from db import StatementPassSignal, db


def update_pass_signal(
    *, participant_id: int, conversation_id: int, statement_id: int,
    choice: str, pass_reason: str | None,
) -> str | None:
    signal = StatementPassSignal.query.filter_by(
        participant_id=participant_id,
        conversation_id=conversation_id,
        statement_id=statement_id,
    ).first()
    if choice != 'pass':
        if signal is not None:
            db.session.delete(signal)
        return None
    if pass_reason is None:
        return signal.reason if signal is not None else None
    if signal is None:
        signal = StatementPassSignal(
            participant_id=participant_id,
            conversation_id=conversation_id,
            statement_id=statement_id,
            reason=pass_reason,
        )
        db.session.add(signal)
    else:
        signal.reason = pass_reason
        signal.updated_at = datetime.now(timezone.utc)
    return pass_reason
