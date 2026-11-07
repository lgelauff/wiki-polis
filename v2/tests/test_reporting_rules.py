"""The shared reporting rules (#233): floor on the base, half-up rounding once."""

from services import reporting_rules as rules


def test_percent_is_whole_and_rounds_half_up_once():
    assert rules.percent(1, 8) == 13        # 12.5 -> 13, not banker's 12
    assert rules.percent(3, 8) == 38        # 37.5 -> 38
    assert rules.percent(1, 3) == 33
    assert rules.percent(2, 3) == 67
    assert rules.percent(0, 10) == 0
    assert rules.percent(10, 10) == 100
    assert rules.percent(5, 0) is None


def test_shift_comes_from_exact_shares_and_rounds_once():
    # 1/8 = 12.5% and 1/3 = 33.33%: the exact difference is 20.83 -> 21. Rounding each
    # share first (13 and 33) would give 20.
    assert rules.shift(1 * 10, 8 * 10, 1 * 10, 3 * 10) == 21
    # Halves go away from zero in both directions, so a fall and a rise of the same size match.
    assert rules.shift(0, 16, 2, 16) == 13
    assert rules.shift(2, 16, 0, 16) == -13


def test_shift_needs_the_floor_in_both_rounds():
    assert rules.shift(5, 9, 8, 20) is None
    assert rules.shift(5, 20, 8, 9) is None
    assert rules.shift(5, 10, 8, 10) == 30


def _counts(agree, pass_, disagree):
    return {'n_agree': agree, 'n_pass': pass_, 'n_disagree': disagree,
            'n_voters': agree + pass_ + disagree}


def test_tally_below_the_floor_carries_no_number():
    withheld = rules.tally(_counts(6, 1, 2), exact_counts=True)
    assert withheld == {'counts': None, 'percentages': None, 'belowFloor': True}


def test_tally_at_the_floor_shows_whole_percentages():
    shown = rules.tally(_counts(5, 2, 3), exact_counts=True)
    assert shown == {
        'counts': {'agree': 5, 'pass': 2, 'disagree': 3, 'voters': 10},
        'percentages': {'agree': 50, 'pass': 20, 'disagree': 30},
        'belowFloor': False,
    }


def test_public_tally_has_percentages_but_no_counts():
    public = rules.tally(_counts(5, 2, 3), exact_counts=False)
    assert public['counts'] is None
    assert public['percentages'] == {'agree': 50, 'pass': 20, 'disagree': 30}


def test_tally_of_nothing_stays_nothing():
    assert rules.tally(None, exact_counts=True) is None


def test_agreement_floors_on_agree_plus_disagree_not_on_all_responses():
    # 9 agree or disagree plus 30 passes: the share rests on 9, so it is withheld.
    assert rules.agreement(6, 3, floor=10, mark_share=0.7) == (None, False)
    assert rules.agreement(7, 3, floor=10, mark_share=0.7) == (70, True)
    assert rules.agreement(6, 4, floor=10, mark_share=0.7) == (60, False)


def test_settings_change_the_floor_and_share(app):
    app.config['REPORTING_MIN_TOTAL'] = 4
    app.config['REPORTING_LABEL_SHARE'] = 0.75
    try:
        with app.app_context():
            assert rules.min_total() == 4
            assert rules.label_share() == 0.75
            assert rules.tally(_counts(2, 1, 1), exact_counts=True)['belowFloor'] is False
    finally:
        app.config.pop('REPORTING_MIN_TOTAL')
        app.config.pop('REPORTING_LABEL_SHARE')


def test_defaults_outside_an_app():
    assert rules.min_total() == 10
    assert rules.label_share() == 0.7
