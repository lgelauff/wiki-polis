"""The reporting rules for opinion numbers, enforced on the server (#233).

Every opinion number the app serves goes through here, so a payload never carries more
than its page shows and the client receives values, never thresholds. Decided by the
owner on 2026-10-30/31 (DECISIONS.md, D1-D10); the names match polis_report and
METHODOLOGY, although polis_report keeps its own rule (exact counts).

- ``min_total`` (10): a number is shown only if its own base is at least this. The base of
  a "% of responses" is all responses; of an agreement share, agree + disagree; of a shift,
  each round's responses (both must pass).
- ``label_share`` (0.7): agree share of agree + disagree at which a statement is marked.
- ``min_cell`` (5): not used yet. A table that crosses opinion with a subgroup (opinion
  group, role answer, a participant's own group) shows counts 1-4 as "<5", plus
  complementary suppression. No app surface prints a count in such a cell today; the first
  one (#228/#229) adds it here.

Percentages are whole numbers, rounded half up once, from integers.

Named exception: the moderation Statements page shows exact agree/pass/disagree counts
(owner, 2026-10-30, D6); see ``services.admin_statements``.
"""

from fractions import Fraction

from flask import current_app, has_app_context

MIN_TOTAL = 10
LABEL_SHARE = 0.7


def min_total() -> int:
    """REPORTING_MIN_TOTAL, default 10; never below 1."""
    value = current_app.config.get('REPORTING_MIN_TOTAL', MIN_TOTAL) if has_app_context() else MIN_TOTAL
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return MIN_TOTAL


def label_share() -> float:
    """REPORTING_LABEL_SHARE, default 0.7, clamped to 0..1."""
    value = current_app.config.get('REPORTING_LABEL_SHARE', LABEL_SHARE) if has_app_context() else LABEL_SHARE
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return LABEL_SHARE


def _round_half_away(value: Fraction) -> int:
    """Round to the nearest integer; halves go away from zero, so a shift of -12.5 and
    +12.5 round to the same size."""
    magnitude = (2 * abs(value.numerator) + value.denominator) // (2 * value.denominator)
    return magnitude if value >= 0 else -magnitude


def percent(n: int, base: int) -> int | None:
    """``n`` of ``base`` as a whole percent, rounded half up once. None for an empty base."""
    if base <= 0:
        return None
    return _round_half_away(Fraction(100 * int(n), int(base)))


def shift(n_before: int, base_before: int, n_after: int, base_after: int,
          *, floor: int | None = None) -> int | None:
    """Change in share between two rounds, in whole points.

    Computed from the exact shares and rounded once, never as a difference of rounded
    values. Withheld (None) unless both rounds have at least ``floor`` responses.
    """
    floor = min_total() if floor is None else floor
    if base_before < floor or base_after < floor:
        return None
    return _round_half_away(
        Fraction(100 * int(n_after), int(base_after))
        - Fraction(100 * int(n_before), int(base_before))
    )


def tally(counts: dict | None, *, exact_counts: bool, floor: int | None = None) -> dict | None:
    """A statement's agree/pass/disagree for the results API.

    ``counts`` holds n_agree, n_pass, n_disagree and n_voters. Below ``floor`` responses the
    tally is withheld: counts and percentages are null and ``belowFloor`` is true, so the
    page says "fewer than 10 responses" and nothing can be worked back. ``exact_counts``
    is false for the public, who see percentages only (decision 4, D8).
    """
    if counts is None:
        return None
    floor = min_total() if floor is None else floor
    agree = int(counts.get('n_agree') or 0)
    pass_ = int(counts.get('n_pass') or 0)
    disagree = int(counts.get('n_disagree') or 0)
    voters = int(counts.get('n_voters') or 0)
    if voters < floor:
        return {'counts': None, 'percentages': None, 'belowFloor': True}
    return {
        'counts': (
            {'agree': agree, 'pass': pass_, 'disagree': disagree, 'voters': voters}
            if exact_counts else None
        ),
        'percentages': {
            'agree': percent(agree, voters),
            'pass': percent(pass_, voters),
            'disagree': percent(disagree, voters),
        },
        'belowFloor': False,
    }


def agreement(agree: int, disagree: int, *, floor: int | None = None,
              mark_share: float | None = None) -> tuple[int | None, bool]:
    """Agreement share of agree + disagree as a whole percent, and whether it is marked.

    Withheld (None, False) below ``floor`` agree + disagree responses. Marked when the exact
    share is at least ``mark_share``.
    """
    floor = min_total() if floor is None else max(1, floor)
    mark_share = label_share() if mark_share is None else mark_share
    position = agree + disagree
    if position < floor:
        return None, False
    return percent(agree, position), Fraction(agree, position) >= Fraction(str(mark_share))
