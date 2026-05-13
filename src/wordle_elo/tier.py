"""Tier classification — top-1 Diamond, bottom-1 Iron, percentile for the rest.

Players who haven't reached PROVISIONAL_GAMES yet still get a tier label, but
suffixed with "(+)" to indicate the ranking is preliminary.
"""

from __future__ import annotations

from collections.abc import Sequence

# (name, top percentile cutoff). Diamond also catches rank-1; Iron is reserved
# for the rank-last player(s). Both are handled separately below.
TIERS: list[tuple[str, float]] = [
    ("Diamond", 0.05),
    ("Gold",    0.20),
    ("Silver",  0.50),
]
PROVISIONAL_GAMES = 14
PROVISIONAL_SUFFIX = "(+)"


def base_tier(player_elo: int, all_ratings: Sequence[int]) -> str:
    """Tier name without the provisional suffix."""
    if not all_ratings:
        return "Bronze"
    if player_elo == max(all_ratings):
        return "Diamond"
    if player_elo == min(all_ratings):
        return "Iron"
    n = len(all_ratings)
    pct_above = sum(1 for r in all_ratings if r > player_elo) / n
    for name, top_pct in TIERS:
        if pct_above < top_pct:
            return name
    return "Bronze"


def assign_tier(
    player_elo: int,
    all_ratings: Sequence[int],
    games_played: int,
    placement_games: int = PROVISIONAL_GAMES,
) -> str:
    base = base_tier(player_elo, all_ratings)
    if games_played < placement_games:
        return f"{base}{PROVISIONAL_SUFFIX}"
    return base


def strip_provisional(tier: str) -> str:
    """Return the base tier name without the "(+)" suffix, for emoji lookup."""
    if tier.endswith(PROVISIONAL_SUFFIX):
        return tier[: -len(PROVISIONAL_SUFFIX)]
    return tier
