"""Tier classification using hybrid percentile + absolute floor."""

from __future__ import annotations

from collections.abc import Sequence

# (name, top percentile cutoff, absolute floor)
TIERS: list[tuple[str, float, int]] = [
    ("Challenger", 0.01, 1300),
    ("Diamond",    0.10, 1180),
    ("Platinum",   0.25, 1080),
    ("Gold",       0.50, 1000),
    ("Silver",     0.75,  920),
    ("Bronze",     0.90,  850),
]
PROVISIONAL_GAMES = 14


def assign_tier(
    player_elo: int,
    all_ratings: Sequence[int],
    games_played: int,
    placement_games: int = PROVISIONAL_GAMES,
) -> str:
    if games_played < placement_games:
        return "Provisional"
    if not all_ratings:
        return "Bronze"
    n = len(all_ratings)
    # fraction of players strictly better than us; 0.0 = top
    pct_above = sum(1 for r in all_ratings if r > player_elo) / n
    for name, top_pct, floor in TIERS:
        if pct_above < top_pct and player_elo >= floor:
            return name
    return "Bronze"
