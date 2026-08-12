"""Participant-facing conversation state projections shared by HTML and JSON."""

from typing import Literal

ConversationBucket = Literal['needs_attention', 'caught_up', 'inactive', 'archived']

_ACTION_PHASES = frozenset({'submission', 'argument_mapping', 'informed_voting'})


def classify_joined_conversation(
    *,
    active: bool,
    paused: bool,
    phases: set[str] | frozenset[str],
    statements_remaining: int | None,
) -> ConversationBucket:
    """Classify an open record by what its participant can do right now.

    Explore is currently the only phase with a reliable per-participant completion
    signal. Other action phases remain in ``needs_attention`` until equivalent
    argument/informed-vote signals exist.
    """
    if not active:
        return 'archived'
    action_phases = set(phases) & _ACTION_PHASES
    if paused or not action_phases:
        return 'inactive'
    if action_phases == {'submission'} and statements_remaining == 0:
        return 'caught_up'
    return 'needs_attention'
