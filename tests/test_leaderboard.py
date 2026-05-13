"""Smoke tests for tier emoji rendering with provisional suffix."""

from wordle_elo.leaderboard import TIER_EMOJI, _tier_emoji


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
