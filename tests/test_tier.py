from wordle_elo.tier import assign_tier, base_tier, strip_provisional


def test_provisional_suffix_appended_under_placement_threshold():
    assert assign_tier(1500, [1500], games_played=10) == "Diamond(+)"
    # 5 players, dead last → Iron, plus "(+)"
    assert assign_tier(700, [1500, 1200, 900, 800, 700], games_played=5) == "Iron(+)"


def test_solo_player_is_diamond():
    assert assign_tier(1500, [1500], games_played=20) == "Diamond"


def test_top_player_gets_diamond_regardless_of_elo():
    assert assign_tier(1100, [1100, 900, 800, 700, 600], games_played=20) == "Diamond"


def test_tied_top_players_all_get_diamond():
    assert assign_tier(1200, [1200, 1200, 1000, 800], games_played=20) == "Diamond"


def test_diamond_percentile_threshold():
    # 21 players: rank-2 has pct_above = 1/21 ≈ 0.048 < 0.05 → Diamond
    ratings = [1500, 1400] + [1000] * 18 + [500]
    assert assign_tier(1400, ratings, games_played=20) == "Diamond"


def test_gold_threshold():
    # 20 players, rank-2: pct_above = 1/20 = 0.05, not < 0.05 → Gold (< 0.20)
    ratings = [1500, 1400] + [1000] * 17 + [500]
    assert assign_tier(1400, ratings, games_played=20) == "Gold"


def test_middle_of_pack_gets_silver():
    # 5 players, player at rank 3: pct_above = 2/5 = 0.40 < 0.50 → Silver
    ratings = [1200, 1100, 1000, 900, 800]
    assert assign_tier(1000, ratings, games_played=20) == "Silver"


def test_bronze_threshold():
    # 10 players, player at rank 8: pct_above = 7/10 = 0.70 → Bronze (not last → not Iron)
    ratings = [1500, 1400, 1300, 1200, 1100, 1000, 900, 800, 700, 600]
    assert assign_tier(800, ratings, games_played=20) == "Bronze"


def test_bottom_player_gets_iron():
    ratings = [1500, 1400, 1300, 1200, 1100, 1000, 900, 800, 700]
    assert assign_tier(700, ratings, games_played=20) == "Iron"


def test_empty_ratings_returns_bronze():
    assert assign_tier(1000, [], games_played=20) == "Bronze"


def test_lowest_elo_in_population_gets_iron():
    population = [1600] * 50 + [1400]
    assert assign_tier(1400, population, games_played=20) == "Iron"


def test_base_tier_ignores_games_played():
    assert base_tier(1500, [1500]) == "Diamond"
    # 5 players, dead last → Iron
    assert base_tier(700, [1500, 1200, 900, 800, 700]) == "Iron"


def test_strip_provisional():
    assert strip_provisional("Bronze(+)") == "Bronze"
    assert strip_provisional("Diamond") == "Diamond"
    assert strip_provisional("Iron(+)") == "Iron"
