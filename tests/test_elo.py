"""ELO engine tests for the absolute-scoring formula.

Each submitter's delta depends only on their own (guesses, streak, hard_mode)
and their K-factor — no comparison with the rest of the field.
"""

import pytest

from wordle_elo.elo import (
    DAMPING_ANCHOR,
    DELTA_CLAMP,
    K,
    K_NEW,
    NEW_PLAYER_GAMES,
    compute_daily,
    damping_factor,
    k_factor,
    streak_bonus,
)


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


@pytest.mark.parametrize(
    "games_played,expected_k",
    [
        (0, K_NEW),
        (NEW_PLAYER_GAMES - 1, K_NEW),
        (NEW_PLAYER_GAMES, K),
        (50, K),
        (1000, K),
    ],
)
def test_k_factor_tiers(games_played, expected_k):
    assert k_factor(games_played) == expected_k


# Established player (K=24) without streak/hard bonuses.
# base = ±K/4 = ±6, speed = SPEED[g], total = round(base + speed) clamped.
ESTABLISHED_SCENARIOS = [
    (1, +9),   # solve 1/6: +6 + 3
    (2, +8),
    (3, +7),
    (4, +6),
    (5, +5),
    (6, +4),
    (7, -10),  # fail X/6: -6 - 4
]


@pytest.mark.parametrize("guesses,expected_total", ESTABLISHED_SCENARIOS)
def test_established_player_per_guesses(guesses, expected_total):
    out = compute_daily(
        [(1, guesses, False)],
        ratings={1: 1000},
        streaks_after={1: 0},
        games_played_before={1: 100},
    )
    assert out[1].delta_total == expected_total


# New player (K_NEW=40), base = ±10.
NEW_PLAYER_SCENARIOS = [
    (1, +13),
    (3, +11),
    (4, +10),
    (6, +8),
    (7, -14),
]


@pytest.mark.parametrize("guesses,expected_total", NEW_PLAYER_SCENARIOS)
def test_new_player_per_guesses(guesses, expected_total):
    out = compute_daily(
        [(1, guesses, False)],
        ratings={1: 1000},
        streaks_after={1: 0},
        games_played_before={1: 0},
    )
    assert out[1].delta_total == expected_total


def test_solo_submitter_still_scores():
    # No early return in the absolute formula — solo submitter gets a delta.
    out = compute_daily([(1, 3, False)], {1: 1000}, {1: 1})
    assert 1 in out
    assert out[1].delta_total > 0


def test_streak_stacks_with_solve():
    # K=24 (established), 3/6 win with 5-day streak after today
    out = compute_daily(
        [(1, 3, False)],
        {1: 1000},
        {1: 5},
        games_played_before={1: 100},
    )
    assert out[1].delta_total == 8


def test_hard_mode_adds_one_on_solve():
    out = compute_daily(
        [(1, 3, True)],
        {1: 1000},
        {1: 0},
        games_played_before={1: 100},
    )
    assert out[1].delta_total == 8


def test_hard_mode_does_not_apply_on_failure():
    out = compute_daily(
        [(1, 7, True)],
        {1: 1000},
        {1: 0},
        games_played_before={1: 100},
    )
    # base -6, speed -4, hard 0 (no hard bonus on fail) → -10
    assert out[1].delta_total == -10


def test_streak_does_not_apply_on_failure():
    out = compute_daily(
        [(1, 7, False)],
        {1: 1000},
        {1: 0},  # streak resets to 0 on fail
        games_played_before={1: 100},
    )
    assert out[1].delta_total == -10


def test_delta_stays_bounded_under_extreme_conditions():
    # Max conceivable: K=40, 1/6, 100-day streak, hard mode
    # base +10, speed +3, streak +3, hard +1 → +17 (well within clamp)
    # The clamp is a safety net for future K changes.
    out = compute_daily(
        [(1, 1, True)],
        {1: 100},
        {1: 100},
        games_played_before={1: 0},
    )
    for delta in out.values():
        assert -DELTA_CLAMP <= delta.delta_total <= DELTA_CLAMP


def test_each_players_k_is_independent():
    # P1 is new (K_NEW=40), P2 is established (K=24); same guesses.
    subs = [(1, 3, False), (2, 3, False)]
    out = compute_daily(
        subs,
        ratings={1: 1000, 2: 1000},
        streaks_after={1: 0, 2: 0},
        games_played_before={1: 0, 2: 200},
    )
    assert out[1].delta_total == 11
    assert out[2].delta_total == 7


def test_k_override_applies_to_all():
    out = compute_daily(
        [(1, 4, False), (2, 4, False)],
        {1: 1000, 2: 1000},
        {1: 0, 2: 0},
        games_played_before={1: 0, 2: 200},
        k=100,  # forced K
    )
    # base = 100/4 = +25, speed 0 → +25 for both, regardless of games_played
    assert out[1].delta_total == 25
    assert out[2].delta_total == 25


def test_default_no_gp_treats_as_established():
    out = compute_daily(
        [(1, 3, False)],
        {1: 1000},
        {1: 0},
    )
    # No games_played_before → falls back to NEW_PLAYER_GAMES, so K=K not K_NEW
    assert out[1].delta_total == 7


def test_damping_factor_is_unity_at_or_below_anchor():
    assert damping_factor(500, +10) == 1.0
    assert damping_factor(DAMPING_ANCHOR, +10) == 1.0
    assert damping_factor(DAMPING_ANCHOR, -10) == 1.0


def test_damping_shrinks_gains_above_anchor():
    # elo=2000 ⇒ gain factor = 1000/2000 = 0.5
    assert damping_factor(2000, +10) == 0.5
    assert damping_factor(1500, +10) == pytest.approx(1000 / 1500)


def test_damping_amplifies_losses_above_anchor():
    # elo=2000 ⇒ loss factor = 2000/1000 = 2.0
    assert damping_factor(2000, -10) == 2.0
    assert damping_factor(1500, -10) == 1.5


def test_high_elo_gain_is_damped():
    # Established player at elo=2000, 3/6 solve.
    # raw = base +6 + speed +1 = +7. damped = 7 * 0.5 = 3.5 → round +4.
    out = compute_daily(
        [(1, 3, False)],
        {1: 2000},
        {1: 0},
        games_played_before={1: 100},
    )
    assert out[1].delta_total == 4


def test_high_elo_loss_is_amplified():
    # Established player at elo=2000, X/6 fail.
    # raw = base -6 + speed -4 = -10. amplified = -10 * 2.0 = -20.
    out = compute_daily(
        [(1, 7, False)],
        {1: 2000},
        {1: 0},
        games_played_before={1: 100},
    )
    assert out[1].delta_total == -20
