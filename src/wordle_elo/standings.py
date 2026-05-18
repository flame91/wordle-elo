"""Shared standings loaders.

The /leaderboard cog asks for "current leaderboard rows by algorithm X". This
module hides the data wiring so the cog stays focused on Discord glue.

- ELO rows come straight from Player.elo (updated incrementally by pipeline).
- Glicko-2 rows are replayed from the Submission table on demand, since we
  don't persist Glicko state — it's a small group and 200 puzzles replay in
  well under a second.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select

from .glicko2 import GlickoRating, apply_puzzle
from .models import Nickname, Player, Submission
from .tier import assign_tier

ACTIVE_DAYS = 7


async def _common_lookups(sessionmaker):
    """Filtered player rows + nickname map + per-user winning-avg dict."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)
    async with sessionmaker() as session:
        players = (
            await session.execute(
                select(Player)
                .where(Player.last_played_at.is_not(None))
                .where(Player.last_played_at >= cutoff)
                .order_by(desc(Player.elo))
            )
        ).scalars().all()
        nick_rows = (await session.execute(select(Nickname))).scalars().all()
        nicks = {n.user_id: n.display_name for n in nick_rows}
        avg_rows = await session.execute(
            select(Submission.user_id, func.avg(Submission.guesses))
            .where(Submission.guesses <= 6)
            .group_by(Submission.user_id)
        )
        avg_by_user = {uid: float(avg) for uid, avg in avg_rows}
    return players, nicks, avg_by_user


async def build_elo_rows(sessionmaker) -> list[dict]:
    """Active players ordered by stored ELO."""
    players, nicks, avg_by_user = await _common_lookups(sessionmaker)
    all_ratings = [p.elo for p in players]
    return [
        {
            "user_id": p.user_id,
            "display_name": nicks.get(p.user_id),
            "rating": p.elo,
            "tier": assign_tier(p.elo, all_ratings, p.games_played),
            "games_played": p.games_played,
            "games_won": p.games_won,
            "best_streak": p.best_streak,
            "current_streak": p.current_streak,
            "avg_winning_guesses": avg_by_user.get(p.user_id),
        }
        for p in players
    ]


async def build_glicko2_rows(sessionmaker) -> list[dict]:
    """Replay all puzzles to compute current Glicko-2 ratings, then filter
    to recently-active players (matches /leaderboard's ACTIVE_DAYS scope)."""
    ratings: dict[int, GlickoRating] = {}

    async with sessionmaker() as session:
        puzzle_nos = [
            r for (r,) in await session.execute(
                select(Submission.puzzle_no).distinct().order_by(Submission.puzzle_no)
            )
        ]

    for puzzle_no in puzzle_nos:
        async with sessionmaker() as session:
            subs = (
                await session.execute(
                    select(Submission.user_id, Submission.guesses)
                    .where(Submission.puzzle_no == puzzle_no)
                )
            ).all()
        if not subs:
            continue
        submissions_tuple = [(uid, g) for uid, g in subs]
        new = apply_puzzle(ratings, submissions_tuple)
        ratings.update(new)

    players, nicks, avg_by_user = await _common_lookups(sessionmaker)
    active_ids = {p.user_id for p in players}
    active_ratings = {uid: r for uid, r in ratings.items() if uid in active_ids}
    # Stable ordering: rating desc
    ordered_ids = sorted(active_ratings, key=lambda uid: -active_ratings[uid].rating)

    by_uid = {p.user_id: p for p in players}
    all_rating_values = [int(round(r.rating)) for r in active_ratings.values()]
    rows: list[dict] = []
    for uid in ordered_ids:
        p = by_uid.get(uid)
        if p is None:
            continue
        r = active_ratings[uid]
        rating_int = int(round(r.rating))
        rows.append(
            {
                "user_id": uid,
                "display_name": nicks.get(uid),
                "rating": rating_int,
                "rating_rd": int(round(r.rd)),
                "tier": assign_tier(rating_int, all_rating_values, p.games_played),
                "games_played": p.games_played,
                "games_won": p.games_won,
                "best_streak": p.best_streak,
                "current_streak": p.current_streak,
                "avg_winning_guesses": avg_by_user.get(uid),
            }
        )
    return rows
