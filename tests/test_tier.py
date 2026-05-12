import pytest

from wordle_elo.tier import assign_tier


def test_provisional_under_placement_threshold():
    assert assign_tier(1500, [1500, 1000, 800], games_played=10) == "Provisional"


def test_solo_high_elo_player_gets_challenger():
    # 1 player at 1500, no one above → top 0% AND elo >= 1300
    assert assign_tier(1500, [1500], games_played=20) == "Challenger"


def test_top_player_with_low_population_falls_to_floor():
    # Top of group, but ELO doesn't meet Diamond floor → Platinum
    assert assign_tier(1100, [1100, 900, 800, 700, 600], games_played=20) == "Platinum"


def test_middle_of_pack_gets_gold():
    ratings = [1200, 1100, 1000, 900, 800]
    # Player at 1000, 2 above → pct_above = 0.4 → Gold (top 50%, elo >= 1000)
    assert assign_tier(1000, ratings, games_played=20) == "Gold"


def test_low_player_gets_bronze():
    ratings = [1500, 1400, 1300, 1200, 1100, 1000, 900, 800, 700]
    # Player at 700 is last → fails all percentile cutoffs except fallback
    assert assign_tier(700, ratings, games_played=20) == "Bronze"


def test_high_elo_alone_at_top():
    ratings = [1400, 1100, 1000, 900, 800]
    # Top of 5, pct_above = 0.0 → Challenger (1300 floor) since elo 1400 >= 1300
    assert assign_tier(1400, ratings, games_played=20) == "Challenger"


def test_empty_ratings_returns_bronze():
    assert assign_tier(1000, [], games_played=20) == "Bronze"


def test_top_player_below_challenger_floor_falls_to_diamond():
    # Top of group, pct_above=0 ✓, but ELO 1200 < Challenger floor 1300 → Diamond
    assert assign_tier(1200, [1200, 1100, 1000, 900], games_played=20) == "Diamond"


def test_top_player_below_diamond_floor_falls_to_platinum():
    assert assign_tier(1100, [1100, 1000, 900, 800], games_played=20) == "Platinum"


def test_high_elo_but_not_top_percentile_doesnt_get_challenger():
    # ELO well above 1300, but lots of even-higher players → not top 1% → Diamond
    population = [1600] * 50 + [1400]  # 1400 is rank 51 of 51
    # pct_above for 1400 = 50/51 ≈ 0.98 → fails all percentile cutoffs
    assert assign_tier(1400, population, games_played=20) == "Bronze"
