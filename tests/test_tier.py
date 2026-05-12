from wordle_elo.tier import assign_tier, base_tier, strip_provisional


def test_provisional_suffix_appended_under_placement_threshold():
    assert assign_tier(1500, [1500], games_played=10) == "Challenger(+)"
    # 5 players, dead last → pct_above=0.8 → Bronze, plus "(+)"
    assert assign_tier(700, [1500, 1200, 900, 800, 700], games_played=5) == "Bronze(+)"


def test_solo_player_is_challenger():
    assert assign_tier(1500, [1500], games_played=20) == "Challenger"


def test_top_player_gets_challenger_regardless_of_elo():
    assert assign_tier(1100, [1100, 900, 800, 700, 600], games_played=20) == "Challenger"


def test_tied_top_players_all_get_challenger():
    assert assign_tier(1200, [1200, 1200, 1000, 800], games_played=20) == "Challenger"


def test_diamond_threshold():
    # 11 players: rank-2 has pct_above = 1/11 ≈ 0.091 < 0.10 → Diamond
    ratings = [1500] + [1400] + [1000] * 9
    assert assign_tier(1400, ratings, games_played=20) == "Diamond"


def test_platinum_threshold():
    # 10 players, rank-2: pct_above = 0.1, not < 0.10 → Platinum (< 0.25)
    ratings = [1500, 1400] + [1000] * 8
    assert assign_tier(1400, ratings, games_played=20) == "Platinum"


def test_middle_of_pack_gets_gold():
    ratings = [1200, 1100, 1000, 900, 800]
    assert assign_tier(1000, ratings, games_played=20) == "Gold"


def test_silver_threshold():
    ratings = [1500, 1400, 1300, 1200, 1100, 1000, 900, 800]
    assert assign_tier(1000, ratings, games_played=20) == "Silver"


def test_low_player_gets_bronze():
    ratings = [1500, 1400, 1300, 1200, 1100, 1000, 900, 800, 700]
    assert assign_tier(700, ratings, games_played=20) == "Bronze"


def test_empty_ratings_returns_bronze():
    assert assign_tier(1000, [], games_played=20) == "Bronze"


def test_high_elo_but_not_top_doesnt_get_challenger():
    population = [1600] * 50 + [1400]
    assert assign_tier(1400, population, games_played=20) == "Bronze"


def test_base_tier_ignores_games_played():
    assert base_tier(1500, [1500]) == "Challenger"
    # 5 players, dead last → pct_above=0.8 → Bronze
    assert base_tier(700, [1500, 1200, 900, 800, 700]) == "Bronze"


def test_strip_provisional():
    assert strip_provisional("Bronze(+)") == "Bronze"
    assert strip_provisional("Challenger") == "Challenger"
