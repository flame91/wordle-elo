"""ELO engine tests for the day-relative absolute-scoring formula.

Each submitter's delta is base ± speed, where speed measures their guesses
against today's solver baseline (mean guesses among today's winners).
Streak and hard-mode bonuses no longer apply.
"""

import pytest

from wordle_elo.elo import (
    BASELINE_FALLBACK,
    DAMPING_ANCHOR,
    DELTA_CLAMP,
    K,
    K_NEW,
    NEW_PLAYER_GAMES,
    SPEED_FAIL,
    SPEED_SLOPE,
    compute_daily,
    damping_factor,
    day_baseline,
    k_factor,
    speed_bonus,
)


def test_speed_bonus_zero_when_player_matches_baseline():
    assert speed_bonus(4, day_baseline=4.0) == 0.0
    assert speed_bonus(3, day_baseline=3.0) == 0.0


def test_speed_bonus_scales_with_baseline_gap():
    # Group avg 5 (hard day), solving in 3 → +5
    assert speed_bonus(3, day_baseline=5.0) == SPEED_SLOPE * 2
    # Group avg 3 (easy day), solving in 3 → 0
    assert speed_bonus(3, day_baseline=3.0) == 0.0


def test_speed_fail_is_flat_independent_of_baseline():
    assert speed_bonus(7, day_baseline=2.0) == SPEED_FAIL
    assert speed_bonus(7, day_baseline=6.0) == SPEED_FAIL


def test_day_baseline_falls_back_when_nobody_solved():
    assert day_baseline([(1, 7, False), (2, 7, False)]) == BASELINE_FALLBACK


def test_day_baseline_averages_winners_only():
    # 3, 5, X — baseline averages 3 and 5 (winners only) = 4
    assert day_baseline([(1, 3, False), (2, 5, False), (3, 7, False)]) == 4.0


@pytest.mark.parametrize(
    "games_played,expected_k",
    [
        (0, K_NEW),
        (NEW_PLAYER_GAMES - 1, K_NEW),
        (NEW_PLAYER_GAMES, K),
        (50, K),
    ],
)
def test_k_factor_tiers(games_played, expected_k):
    assert k_factor(games_played) == expected_k


def test_solo_solver_gets_no_speed_bonus_only_base():
    # Solo → baseline = own guesses → speed = 0; just base +K/4.
    out = compute_daily(
        [(1, 3, False)],
        ratings={1: DAMPING_ANCHOR},
        games_played_before={1: 100},
    )
    assert out[1].delta_total == round(K / 4)
    assert out[1].delta_speed == 0.0


def test_solo_failure_takes_base_minus_speed_fail():
    out = compute_daily(
        [(1, 7, False)],
        ratings={1: DAMPING_ANCHOR},
        games_played_before={1: 100},
    )
    assert out[1].delta_total == round(-K / 4 + SPEED_FAIL)


def test_two_winners_get_symmetric_speed_bonus():
    # P1 solved in 3, P2 in 5 → baseline = 4. P1: +2.5, P2: -2.5.
    out = compute_daily(
        [(1, 3, False), (2, 5, False)],
        ratings={1: DAMPING_ANCHOR, 2: DAMPING_ANCHOR},
        games_played_before={1: 100, 2: 100},
    )
    assert out[1].delta_speed == SPEED_SLOPE
    assert out[2].delta_speed == -SPEED_SLOPE
    assert out[1].delta_total == round(K / 4 + SPEED_SLOPE)
    assert out[2].delta_total == round(K / 4 - SPEED_SLOPE)


def test_easy_day_gives_no_speed_bonus_to_average_player():
    # Everyone solved in 2. Baseline = 2, so everyone's speed bonus = 0.
    subs = [(1, 2, False), (2, 2, False), (3, 2, False)]
    out = compute_daily(
        subs,
        ratings={1: DAMPING_ANCHOR, 2: DAMPING_ANCHOR, 3: DAMPING_ANCHOR},
        games_played_before={i: 100 for i in (1, 2, 3)},
    )
    for d in out.values():
        assert d.delta_speed == 0.0
        assert d.delta_total == round(K / 4)


def test_hard_day_rewards_solvers_relative_to_field():
    # Two players failed (X/6), one solved in 5. Baseline = 5 (winners only).
    # Solver: speed = 2.5*(5-5) = 0. base = +6. → +6.
    # Failers: speed = -3, base = -6 → -9.
    subs = [(1, 5, False), (2, 7, False), (3, 7, False)]
    out = compute_daily(
        subs,
        ratings={i: DAMPING_ANCHOR for i in (1, 2, 3)},
        games_played_before={i: 100 for i in (1, 2, 3)},
    )
    assert out[1].delta_total == round(K / 4)
    assert out[2].delta_total == round(-K / 4 + SPEED_FAIL)
    assert out[3].delta_total == round(-K / 4 + SPEED_FAIL)


def test_hard_mode_flag_does_not_affect_delta():
    """The hard-mode marker is a per-player game-setting flag, not a difficulty
    signal — it must not change a player's delta."""
    plain = compute_daily(
        [(1, 3, False), (2, 5, False)],  # baseline = 4
        ratings={1: DAMPING_ANCHOR, 2: DAMPING_ANCHOR},
        games_played_before={1: 100, 2: 100},
    )[1].delta_total
    hard = compute_daily(
        [(1, 3, True), (2, 5, False)],   # same baseline
        ratings={1: DAMPING_ANCHOR, 2: DAMPING_ANCHOR},
        games_played_before={1: 100, 2: 100},
    )[1].delta_total
    assert plain == hard


def test_streak_argument_is_ignored():
    no_streak = compute_daily(
        [(1, 3, False), (2, 5, False)],
        ratings={1: DAMPING_ANCHOR, 2: DAMPING_ANCHOR},
        streaks_after={1: 0, 2: 0},
        games_played_before={1: 100, 2: 100},
    )
    huge_streak = compute_daily(
        [(1, 3, False), (2, 5, False)],
        ratings={1: DAMPING_ANCHOR, 2: DAMPING_ANCHOR},
        streaks_after={1: 100, 2: 100},
        games_played_before={1: 100, 2: 100},
    )
    assert no_streak[1].delta_total == huge_streak[1].delta_total
    assert no_streak[1].delta_streak == 0.0


def test_delta_stays_bounded_under_extreme_conditions():
    # K=40, solo solve. base +10, speed 0 → +10 (well within clamp).
    out = compute_daily(
        [(1, 1, True)],
        {1: DAMPING_ANCHOR},
        games_played_before={1: 0},
    )
    for delta in out.values():
        assert -DELTA_CLAMP <= delta.delta_total <= DELTA_CLAMP


def test_each_players_k_is_independent():
    # P1 new (K=40), P2 established (K=24); same guesses → baseline = both guess
    # → speed = 0 for both; deltas differ only by base.
    out = compute_daily(
        [(1, 3, False), (2, 3, False)],
        ratings={1: DAMPING_ANCHOR, 2: DAMPING_ANCHOR},
        games_played_before={1: 0, 2: 200},
    )
    assert out[1].delta_total == round(K_NEW / 4)
    assert out[2].delta_total == round(K / 4)


def test_k_override_applies_to_all():
    out = compute_daily(
        [(1, 4, False), (2, 4, False)],
        {1: DAMPING_ANCHOR, 2: DAMPING_ANCHOR},
        games_played_before={1: 0, 2: 200},
        k=100,
    )
    assert out[1].delta_total == 25
    assert out[2].delta_total == 25


def test_default_no_gp_treats_as_established():
    out = compute_daily([(1, 3, False)], {1: DAMPING_ANCHOR})
    assert out[1].delta_total == round(K / 4)


def test_damping_factor_is_unity_at_or_below_anchor():
    assert damping_factor(DAMPING_ANCHOR // 2, +10) == 1.0
    assert damping_factor(DAMPING_ANCHOR, +10) == 1.0
    assert damping_factor(DAMPING_ANCHOR, -10) == 1.0


def test_damping_shrinks_gains_above_anchor():
    assert damping_factor(DAMPING_ANCHOR * 2, +10) == 0.5
    assert damping_factor(DAMPING_ANCHOR * 3 // 2, +10) == pytest.approx(2 / 3)


def test_damping_amplifies_losses_above_anchor():
    assert damping_factor(DAMPING_ANCHOR * 2, -10) == 2.0
    assert damping_factor(DAMPING_ANCHOR * 3 // 2, -10) == pytest.approx(1.5)


def test_high_elo_gain_is_damped():
    # 2× anchor, two solvers (3, 5) → baseline 4. P1 raw = 6 + 2.5 = 8.5 → ×0.5 = 4.25 → 4.
    out = compute_daily(
        [(1, 3, False), (2, 5, False)],
        ratings={1: DAMPING_ANCHOR * 2, 2: DAMPING_ANCHOR * 2},
        games_played_before={1: 100, 2: 100},
    )
    assert out[1].delta_total == round((K / 4 + SPEED_SLOPE) * 0.5)


def test_high_elo_loss_is_amplified():
    # 2× anchor, X/6 amid two solvers. raw = -6 - 3 = -9, amplified ×2 = -18.
    out = compute_daily(
        [(1, 7, False), (2, 3, False), (3, 5, False)],
        ratings={1: DAMPING_ANCHOR * 2, 2: DAMPING_ANCHOR, 3: DAMPING_ANCHOR},
        games_played_before={i: 100 for i in (1, 2, 3)},
    )
    assert out[1].delta_total == round((-K / 4 + SPEED_FAIL) * 2.0)
