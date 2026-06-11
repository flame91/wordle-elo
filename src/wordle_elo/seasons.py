"""Season rollover service (DB + Discord side of `season.py`).

A quarterly boundary is detected from the *puzzle being processed*, not the wall
clock: the puzzle posted at 00:00 KST is the previous day's Wordle, and catch-up
may backfill puzzles from across a boundary. Keying off `puzzle_no` makes the
reset land on the exact puzzle that opens a new season, however late it's seen.

On a boundary we: archive the ending season's standings (`SeasonResult`),
announce the winner to the channel, then soft-reset every `Player.elo` toward
the anchor so the new season starts competitive. Seasons that start before
`season.SEASON_EPOCH` are pre-season warm-up — they seed the first tracked
season's ratings but are never archived or reset (see `season` module docstring).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select

from . import season
from .models import Player, SeasonResult, SeasonState, Submission

log = logging.getLogger(__name__)


def _finalizes(prev_label: str) -> bool:
    """A rollover archives + resets only when the *ending* season is itself a
    tracked season (starts on/after the season clock). Pre-season → first
    season carries ratings in untouched."""
    return season.season_start_date(prev_label) >= season.SEASON_EPOCH


async def season_player_stats(session, label: str) -> dict[int, dict]:
    """Per-player stats scoped to one season, derived from the immutable
    Submission log: games, wins, mean winning guesses, and best win streak."""
    lo = season.first_puzzle_no(label)
    hi = season.first_puzzle_no(season.next_label(label)) - 1
    rows = (
        await session.execute(
            select(Submission.user_id, Submission.puzzle_no, Submission.guesses)
            .where(Submission.puzzle_no >= lo, Submission.puzzle_no <= hi)
            .order_by(Submission.user_id, Submission.puzzle_no)
        )
    ).all()

    stats: dict[int, dict] = {}
    for uid, _pz, guesses in rows:
        s = stats.setdefault(
            uid, {"games": 0, "won": 0, "win_total": 0, "streak": 0, "best_streak": 0}
        )
        s["games"] += 1
        if guesses <= 6:
            s["won"] += 1
            s["win_total"] += guesses
            s["streak"] += 1
            s["best_streak"] = max(s["best_streak"], s["streak"])
        else:
            s["streak"] = 0
    for s in stats.values():
        s["avg"] = (s["win_total"] / s["won"]) if s["won"] else None
    return stats


async def finalize_season(session, label: str, *, when: datetime) -> list[dict]:
    """Write SeasonResult rows for `label` from current standings and return the
    ranked rows (rank 1 first). Ranking uses live `Player.elo`, which still holds
    the season-final running rating at the moment of rollover (before reset)."""
    stats = await season_player_stats(session, label)
    if not stats:
        return []

    players = {
        p.user_id: p
        for p in (await session.execute(select(Player))).scalars().all()
    }
    # Rank everyone who played this season by their season-final ELO.
    ordered = sorted(
        stats.keys(),
        key=lambda uid: -(players[uid].elo if uid in players else 0),
    )
    ranked: list[dict] = []
    for rank, uid in enumerate(ordered, start=1):
        st = stats[uid]
        final_elo = players[uid].elo if uid in players else season.RESET_ANCHOR
        session.add(
            SeasonResult(
                season=label,
                user_id=uid,
                rank=rank,
                final_elo=final_elo,
                games_played=st["games"],
                games_won=st["won"],
                best_streak=st["best_streak"],
                avg_winning_guesses=st["avg"],
                finalized_at=when,
            )
        )
        ranked.append(
            {
                "rank": rank,
                "user_id": uid,
                "final_elo": final_elo,
                "games_played": st["games"],
                "games_won": st["won"],
                "best_streak": st["best_streak"],
                "avg_winning_guesses": st["avg"],
            }
        )
    return ranked


async def soft_reset_players(session) -> None:
    """Regress every player's ELO toward the anchor for the next season."""
    players = (await session.execute(select(Player))).scalars().all()
    for p in players:
        p.elo = season.soft_reset(p.elo)


async def maybe_rollover(session, bot, puzzle_no: int, *, when: datetime, post: bool = True):
    """Run *before* scoring `puzzle_no`. If it opens a new season, finalise the
    ending one (archive + announce + soft-reset). Returns the finalised season
    label, or None. The caller commits the session.
    """
    pz_season = season.season_of_puzzle(puzzle_no)
    state = await session.get(SeasonState, 1)

    if state is None:
        session.add(SeasonState(id=1, current_season=pz_season, updated_at=when))
        return None
    if state.current_season == pz_season:
        return None

    prev = state.current_season
    finalized: str | None = None
    ranked: list[dict] = []
    if _finalizes(prev):
        ranked = await finalize_season(session, prev, when=when)
        await soft_reset_players(session)
        finalized = prev

    state.current_season = pz_season
    state.updated_at = when

    if finalized and ranked and post and bot is not None:
        try:
            await _announce(bot, finalized, ranked)
        except Exception:
            log.exception("Failed to announce season finale for %s", finalized)
    if finalized:
        log.info("Season %s finalised (%d players); rolled into %s", finalized, len(ranked), pz_season)
    return finalized


async def _announce(bot, label: str, ranked: list[dict]) -> None:
    from .leaderboard import format_season_finale_embed
    from .standings import resolve_names  # late import: avoids cycle

    names = await resolve_names(bot.sessionmaker, [r["user_id"] for r in ranked])
    embed = format_season_finale_embed(label, ranked, names)
    channel = bot.get_channel(bot.cfg.wordle_channel_id)
    if channel is None:
        channel = await bot.fetch_channel(bot.cfg.wordle_channel_id)
    await channel.send(embed=embed)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def current_season_label(sessionmaker) -> str | None:
    """The season the live standings belong to, per SeasonState. None until the
    first puzzle is processed."""
    async with sessionmaker() as session:
        state = await session.get(SeasonState, 1)
        return state.current_season if state else None


async def list_archived_seasons(sessionmaker) -> list[str]:
    """Distinct season labels that have been finalised, newest first."""
    async with sessionmaker() as session:
        labels = [
            r for (r,) in await session.execute(
                select(SeasonResult.season).distinct()
            )
        ]
    return sorted(labels, reverse=True)


def normalize_season_label(raw: str, default_year: int) -> str | None:
    """Accept loose user input for a season and return a canonical `YYYY-Qn`,
    or None if it can't be parsed. Handles `2026-Q1`, `2026q1`, `2026 1`,
    `Q1`, and bare `1` (which assumes `default_year`)."""
    s = raw.strip().upper().replace(" ", "").replace("-", "")
    m = re.fullmatch(r"(\d{4})Q?([1-4])", s)
    if m:
        return f"{m.group(1)}-Q{m.group(2)}"
    m = re.fullmatch(r"Q?([1-4])", s)
    if m:
        return f"{default_year}-Q{m.group(1)}"
    return None


async def load_season_archive(sessionmaker, label: str) -> list[dict]:
    """Ranked rows for a finished season (same shape finalize_season returns)."""
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(SeasonResult)
                .where(SeasonResult.season == label)
                .order_by(SeasonResult.rank)
            )
        ).scalars().all()
    return [
        {
            "rank": r.rank,
            "user_id": r.user_id,
            "final_elo": r.final_elo,
            "games_played": r.games_played,
            "games_won": r.games_won,
            "best_streak": r.best_streak,
            "avg_winning_guesses": r.avg_winning_guesses,
        }
        for r in rows
    ]
