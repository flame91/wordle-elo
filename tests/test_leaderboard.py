"""Smoke tests for tier emoji rendering and full-leaderboard formatting."""

from wordle_elo.leaderboard import TIER_EMOJI, _tier_emoji, format_full_leaderboard


def test_tier_emoji_for_established_tier():
    assert _tier_emoji("Bronze") == TIER_EMOJI["Bronze"]
    assert _tier_emoji("Diamond") == TIER_EMOJI["Diamond"]
    assert _tier_emoji("Iron") == TIER_EMOJI["Iron"]


def test_tier_emoji_strips_provisional_suffix():
    assert _tier_emoji("Bronze(+)") == TIER_EMOJI["Bronze"]
    assert _tier_emoji("Diamond(+)") == TIER_EMOJI["Diamond"]
    assert _tier_emoji("Iron(+)") == TIER_EMOJI["Iron"]


def test_tier_emoji_unknown_returns_empty():
    assert _tier_emoji("Unranked") == ""


def _row(**overrides):
    base = {
        "user_id": 111,
        "elo": 1200,
        "tier": "Gold",
        "games_played": 10,
        "games_won": 8,
        "best_streak": 3,
        "avg_winning_guesses": 4.0,
    }
    base.update(overrides)
    return base


def test_full_leaderboard_uses_display_name_when_present():
    embed = format_full_leaderboard([_row(display_name="flame91")])
    assert "**flame91**" in (embed.description or "")
    assert "<@111>" not in (embed.description or "")


def test_full_leaderboard_falls_back_to_mention_when_name_missing():
    embed = format_full_leaderboard([_row(user_id=999)])
    assert "<@999>" in (embed.description or "")
