"""Shared loader for the full leaderboard view.

Used both by the `/leaderboard` slash command and by the daily auto-reply, so
the two views always show identical data and any future fields are added in
one place.
"""

from __future__ import annotations

from sqlalchemy import desc, func, select

from .models import Player, Submission
from .tier import assign_tier


async def build_leaderboard_rows(sessionmaker) -> list[dict]:
    """Return one row dict per player, ordered by ELO desc.

    Same row shape consumed by `format_full_leaderboard` in `leaderboard.py`.
    """
    async with sessionmaker() as session:
        players = (
            await session.execute(select(Player).order_by(desc(Player.elo)))
        ).scalars().all()

        avg_rows = await session.execute(
            select(Submission.user_id, func.avg(Submission.guesses))
            .where(Submission.guesses <= 6)
            .group_by(Submission.user_id)
        )
        avg_by_user = {uid: float(avg) for uid, avg in avg_rows}

    all_ratings = [p.elo for p in players]
    return [
        {
            "user_id": p.user_id,
            "elo": p.elo,
            "tier": assign_tier(p.elo, all_ratings, p.games_played),
            "games_played": p.games_played,
            "games_won": p.games_won,
            "best_streak": p.best_streak,
            "current_streak": p.current_streak,
            "avg_winning_guesses": avg_by_user.get(p.user_id),
        }
        for p in players
    ]
