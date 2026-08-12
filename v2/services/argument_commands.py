"""Transactional commands for participant argument mapping."""

import random
from dataclasses import dataclass

import nh3
from sqlalchemy.exc import IntegrityError

from db import (Argument, ArgumentSideState, ArgumentVote, Conversation,
                FeaturedStatement, Participation, db)


class InvalidArgument(ValueError):
    pass


class ExistingArgumentConflict(RuntimeError):
    pass


class ContributionGateClosed(RuntimeError):
    pass


class PrioritizationUnavailable(RuntimeError):
    pass


class PriorityBudgetExceeded(RuntimeError):
    pass


class HiddenArgument(RuntimeError):
    pass


@dataclass(frozen=True)
class ArgumentSubmission:
    argument: Argument
    created: bool


def _featured(conversation: Conversation, featured_statement_id: int):
    return FeaturedStatement.query.filter_by(
        id=featured_statement_id,
        conversation_id=conversation.id,
        confirmed_by_admin=True,
    ).first_or_404()


def submit_argument(
    *, conversation: Conversation, participation: Participation,
    featured_statement_id: int, side: str, body: str, touch,
) -> ArgumentSubmission:
    _featured(conversation, featured_statement_id)
    clean_body = nh3.clean((body or '').strip(), tags=frozenset())
    if side not in {'pro', 'con'} or not clean_body or len(clean_body) > 280:
        raise InvalidArgument()
    lookup = {
        'proposer_pseudonym': participation.pseudonym,
        'featured_statement_id': featured_statement_id,
        'side': side,
    }
    existing = Argument.query.filter_by(**lookup).first()
    if existing is not None:
        if existing.body != clean_body:
            raise ExistingArgumentConflict()
        return ArgumentSubmission(argument=existing, created=False)

    argument = Argument(**lookup, body=clean_body)
    db.session.add(argument)
    try:
        db.session.flush()
        state = ArgumentSideState.query.filter_by(
            participant_id=participation.participant_id,
            featured_statement_id=featured_statement_id,
            side=side,
        ).with_for_update().first()
        if state is None:
            state = ArgumentSideState(
                participant_id=participation.participant_id,
                featured_statement_id=featured_statement_id,
                side=side,
                argument_order=[],
            )
            db.session.add(state)
            db.session.flush()
        order = list(state.argument_order or [])
        order.insert(random.randint(0, len(order)), argument.id)
        state.argument_order = order
        touch(participation)
        db.session.commit()
        return ArgumentSubmission(argument=argument, created=True)
    except IntegrityError:
        db.session.rollback()
        existing = Argument.query.filter_by(**lookup).one_or_none()
        if existing is not None and existing.body == clean_body:
            return ArgumentSubmission(argument=existing, created=False)
        raise ExistingArgumentConflict()


def skip_argument_contribution(
    *, conversation: Conversation, participation: Participation,
    featured_statement_id: int, side: str, touch,
) -> bool:
    _featured(conversation, featured_statement_id)
    if side not in {'pro', 'con'}:
        raise InvalidArgument()
    proposed = Argument.query.filter_by(
        proposer_pseudonym=participation.pseudonym,
        featured_statement_id=featured_statement_id,
        side=side,
    ).first()
    if proposed is not None:
        raise ExistingArgumentConflict()
    state = ArgumentSideState.query.filter_by(
        participant_id=participation.participant_id,
        featured_statement_id=featured_statement_id,
        side=side,
    ).with_for_update().first()
    changed = state is None or not state.skipped
    if state is None:
        state = ArgumentSideState(
            participant_id=participation.participant_id,
            featured_statement_id=featured_statement_id,
            side=side,
            skipped=True,
        )
        db.session.add(state)
    else:
        state.skipped = True
    touch(participation)
    try:
        db.session.commit()
        return changed
    except IntegrityError:
        db.session.rollback()
        # A concurrent identical PUT created the same unique side-state row.
        state = ArgumentSideState.query.filter_by(
            participant_id=participation.participant_id,
            featured_statement_id=featured_statement_id,
            side=side,
            skipped=True,
        ).one_or_none()
        if state is not None:
            return False
        raise


def set_argument_priority(
    *, conversation: Conversation, participation: Participation,
    argument_id: int, selected: bool, touch,
) -> tuple[ArgumentVote | None, int, int]:
    argument = (
        Argument.query
        .join(FeaturedStatement)
        .filter(
            Argument.id == argument_id,
            FeaturedStatement.conversation_id == conversation.id,
            FeaturedStatement.confirmed_by_admin.is_(True),
        )
        .first_or_404()
    )
    featured_statement_id = argument.featured_statement_id
    budget = max(1, int((conversation.argument_vote_data or {}).get('K', 2)))
    # This row always exists, unlike historical side-state rows. Locking it
    # serializes count-then-insert budget checks across tabs and workers.
    Participation.query.filter_by(id=participation.id).with_for_update().one()
    existing = ArgumentVote.query.filter_by(
        participant_id=participation.participant_id,
        argument_id=argument.id,
    ).first()
    if not selected:
        side_argument_ids = [item.id for item in Argument.query.filter_by(
            featured_statement_id=featured_statement_id,
            side=argument.side,
        ).all()]
        selected_count = ArgumentVote.query.filter(
            ArgumentVote.participant_id == participation.participant_id,
            ArgumentVote.argument_id.in_(side_argument_ids),
        ).count()
        if existing is not None:
            db.session.delete(existing)
            selected_count -= 1
            touch(participation)
            db.session.commit()
        return None, selected_count, budget
    if argument.hidden:
        raise HiddenArgument()

    def contribution_done(side: str) -> bool:
        proposed = Argument.query.filter_by(
            proposer_pseudonym=participation.pseudonym,
            featured_statement_id=featured_statement_id,
            side=side,
        ).first()
        state = ArgumentSideState.query.filter_by(
            participant_id=participation.participant_id,
            featured_statement_id=featured_statement_id,
            side=side,
        ).first()
        return bool(proposed or (state and state.skipped))

    if not contribution_done('pro') or not contribution_done('con'):
        raise ContributionGateClosed()
    visible_side_arguments = Argument.query.filter_by(
        featured_statement_id=featured_statement_id,
        side=argument.side,
        hidden=False,
    ).all()
    if len(visible_side_arguments) <= budget:
        raise PrioritizationUnavailable()
    side_argument_ids = [item.id for item in visible_side_arguments]
    selected_count = ArgumentVote.query.filter(
        ArgumentVote.participant_id == participation.participant_id,
        ArgumentVote.argument_id.in_(side_argument_ids),
    ).count()
    if existing is not None:
        return existing, selected_count, budget
    if selected_count >= budget:
        raise PriorityBudgetExceeded()
    vote = ArgumentVote(
        participant_id=participation.participant_id,
        argument_id=argument.id,
    )
    db.session.add(vote)
    touch(participation)
    db.session.commit()
    return vote, selected_count + 1, budget
