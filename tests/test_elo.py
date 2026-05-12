"""ELO engine tests.

The 8 scenarios from the design report's preview table use a 1:1 simplification
(only 2 players). With n=2, the pairwise field reduces to the classical Elo
delta with no field-averaging effect, so we can verify against the report values.
"""

import pytest

from wordle_elo.elo import (
    DELTA_CLAMP,
    actual,
    compute_daily,
    expected,
    streak_bonus,
)


def test_expected_symmetry():
    assert expected(1000, 1000) == pytest.approx(0.5)
    assert expected(1000, 1100) + expected(1100, 1000) == pytest.approx(1.0)


def test_actual_lower_guesses_wins():
    assert actual(2, 4) == 1.0
    assert actual(4, 2) == 0.0
    assert actual(3, 3) == 0.5


@pytest.mark.parametrize(
    "streak,won,expected_bonus",
    [
        (0, True, 0),
        (2, True, 0),
        (3, True, 1),
        (5, True, 1),
        (6, True, 2),
        (8, True, 2),
        (9, True, 3),
        (100, True, 3),
        (10, False, 0),  # no bonus on loss
    ],
)
def test_streak_bonus(streak, won, expected_bonus):
    assert streak_bonus(streak, won) == expected_bonus


def test_n_lt_2_returns_empty():
    # only 1 submitter → no comparison possible → no Elo change
    out = compute_daily([(1, 3, False)], {1: 1000}, {1: 1})
    assert out == {}


# Report scenario table — 1:1 simplification with K=24, INITIAL=1000.
# n=2 ⇒ d_field reduces to K * (S - E).
# Format: (g_self, g_opp, r_self, r_opp, expected_delta_total)
REPORT_SCENARIOS = [
    # 동일 ELO, 2/6로 승: ΔELO +14 (12 field + 2 speed)
    (2, 4, 1000, 1000, +14),
    # 동일 ELO, 4/6 무승부
    (4, 4, 1000, 1000, 0),
    # 동일 ELO, 6/6로 승: 12 field - 2 speed = +10
    (6, 7, 1000, 1000, +10),  # opp X to make self win clear
    # 동일 ELO, X/6 패배: -12 field - 4 speed = -16
    (7, 4, 1000, 1000, -16),
    # 언더독 1000이 1100 상대로 4/6 동률: ~+3.36
    (4, 4, 1000, 1100, +3),
    # 상위권 1100이 1000 상대로 5/6 패배: ~-16.36
    (5, 4, 1100, 1000, -16),
]


@pytest.mark.parametrize("g_self,g_opp,r_self,r_opp,expected_total", REPORT_SCENARIOS)
def test_report_scenarios(g_self, g_opp, r_self, r_opp, expected_total):
    self_id, opp_id = 1, 2
    subs = [(self_id, g_self, False), (opp_id, g_opp, False)]
    ratings = {self_id: r_self, opp_id: r_opp}
    streaks = {self_id: 0, opp_id: 0}  # no streak bonus on these
    out = compute_daily(subs, ratings, streaks)
    assert out[self_id].delta_total == expected_total


def test_speed_and_streak_stack():
    # n=2, equal Elo, self wins 3/6 with 3-day streak after today
    out = compute_daily(
        [(1, 3, False), (2, 5, False)],
        {1: 1000, 2: 1000},
        {1: 3, 2: 0},
    )
    # field = 24 * (1 - 0.5) = +12, speed = +1, streak = +1, hard = 0 → +14
    assert out[1].delta_total == 14


def test_hard_mode_adds_one():
    out = compute_daily(
        [(1, 3, True), (2, 5, False)],
        {1: 1000, 2: 1000},
        {1: 0, 2: 0},
    )
    # field = +12, speed = +1, hard = +1 → +14
    assert out[1].delta_total == 14


def test_delta_stays_bounded_under_extreme_conditions():
    # With K=24 the natural max is ~31 (24 field + 3 speed + 3 streak + 1 hard);
    # the [-40, +40] clamp is a safety net for future K changes. Verify any
    # single day's delta stays within bounds for an extreme matchup.
    out = compute_daily(
        [(1, 1, True), (2, 7, False)],
        {1: 100, 2: 2000},
        {1: 100, 2: 0},
    )
    for delta in out.values():
        assert -DELTA_CLAMP <= delta.delta_total <= DELTA_CLAMP


def test_field_averaging_with_three_players():
    # n=3, equal Elo, one player wins outright
    subs = [(1, 2, False), (2, 4, False), (3, 5, False)]
    ratings = {1: 1000, 2: 1000, 3: 1000}
    streaks = {1: 0, 2: 0, 3: 0}
    out = compute_daily(subs, ratings, streaks)
    # Player 1: S=2 (beats both), E=1.0 (0.5 each), field = (24/2)*(2-1) = +12, speed=+2 → +14
    assert out[1].delta_total == 14
    # Player 3: S=0 (loses to both), E=1.0, field = (24/2)*(0-1) = -12, speed=-1 → -13
    assert out[3].delta_total == -13
