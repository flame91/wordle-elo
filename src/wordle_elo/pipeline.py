"""Glue layer: discord message → parse → DB → ELO → leaderboard post.

The same `process_message` is used by both the live `on_message` handler and the
backfill / catch-up scripts. Idempotency is guaranteed by the
`processed_puzzles` table (puzzle_no PK).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from .elo import INITIAL as ELO_INITIAL
from .elo import compute_daily
from .leaderboard import format_daily_embed
from .models import EloHistory, Player, ProcessedPuzzle, Submission
from .parser import parse_message
from .tier import assign_tier

log = logging.getLogger(__name__)
ELO_FLOOR = 100


async def process_message(bot, message, *, silent: bool = False):
    """Top-level entry. Returns result dict or None if skipped."""
    parsed = parse_message(message)
    if parsed is None:
        log.debug("Skip unparseable message %s", message.id)
        return None

    sm = bot.sessionmaker
    async with sm() as session:
        if await session.get(ProcessedPuzzle, parsed.puzzle_no) is not None:
            log.info("Puzzle %s already processed, skipping", parsed.puzzle_no)
            return None
        result = await _apply(session, bot, parsed, message)
        await session.commit()

    if not silent:
        try:
            posted = await message.reply(
                embed=format_daily_embed(parsed.puzzle_no, result["entries"]),
                mention_author=False,
            )
        except Exception:
            log.exception("Failed to post leaderboard for puzzle %s", parsed.puzzle_no)
        else:
            async with sm() as session:
                pp = await session.get(ProcessedPuzzle, parsed.puzzle_no)
                if pp is not None:
                    pp.leaderboard_message_id = posted.id
                    await session.commit()
    return result


async def _apply(session, bot, parsed, source_msg):
    now = datetime.now(timezone.utc)
    when = source_msg.created_at if source_msg is not None else now

    submitter_ids = [s.user_id for s in parsed.submissions]

    # Ensure player rows exist
    for s in parsed.submissions:
        existing = await session.get(Player, s.user_id)
        if existing is None:
            display_name = await _resolve_display_name(bot, s.user_id)
            session.add(
                Player(
                    user_id=s.user_id,
                    display_name=display_name,
                    elo=ELO_INITIAL,
                    first_seen_at=when,
                )
            )
    await session.flush()

    rows = (
        await session.execute(select(Player).where(Player.user_id.in_(submitter_ids)))
    ).scalars().all()
    players = {p.user_id: p for p in rows}

    ratings_before = {uid: players[uid].elo for uid in submitter_ids}
    games_played_before = {uid: players[uid].games_played for uid in submitter_ids}
    streaks_after: dict[int, int] = {}
    for s in parsed.submissions:
        prev = players[s.user_id].current_streak
        streaks_after[s.user_id] = (prev + 1) if s.won else 0

    subs_tuple = [(s.user_id, s.guesses, s.hard_mode) for s in parsed.submissions]
    deltas = compute_daily(
        subs_tuple, ratings_before, streaks_after,
        games_played_before=games_played_before,
    )

    entries = []
    for s in parsed.submissions:
        p = players[s.user_id]
        elo_before = p.elo
        d = deltas.get(s.user_id)
        d_total = d.delta_total if d else 0
        elo_after = max(ELO_FLOOR, elo_before + d_total)

        # Update player row
        p.elo = elo_after
        p.games_played += 1
        if s.won:
            p.games_won += 1
        p.current_streak = streaks_after[s.user_id]
        if p.current_streak > p.best_streak:
            p.best_streak = p.current_streak
        p.last_played_at = when

        session.add(
            Submission(
                puzzle_no=parsed.puzzle_no,
                user_id=s.user_id,
                guesses=s.guesses,
                hard_mode=int(s.hard_mode),
                source_message_id=source_msg.id if source_msg is not None else None,
                submitted_at=when,
            )
        )

        if d is not None:
            session.add(
                EloHistory(
                    puzzle_no=parsed.puzzle_no,
                    user_id=s.user_id,
                    elo_before=elo_before,
                    elo_after=elo_after,
                    delta_field=d.delta_field,
                    delta_speed=d.delta_speed,
                    delta_streak=d.delta_streak,
                    delta_hard=d.delta_hard,
                    delta_total=d.delta_total,
                    computed_at=now,
                )
            )

        entries.append(
            {
                "user_id": s.user_id,
                "display_name": p.display_name,
                "guesses": s.guesses,
                "hard_mode": s.hard_mode,
                "elo_before": elo_before,
                "elo_after": elo_after,
                "delta_total": d_total,
            }
        )

    session.add(
        ProcessedPuzzle(
            puzzle_no=parsed.puzzle_no,
            source_message_id=source_msg.id if source_msg is not None else 0,
            processed_at=now,
        )
    )

    entries.sort(key=lambda e: (e["guesses"], -e["delta_total"]))

    all_ratings = [r for (r,) in (await session.execute(select(Player.elo)))]
    for entry in entries:
        p = players[entry["user_id"]]
        entry["tier"] = assign_tier(entry["elo_after"], all_ratings, p.games_played)

    return {"puzzle_no": parsed.puzzle_no, "entries": entries}


async def _resolve_display_name(bot, user_id: int) -> str:
    user = bot.get_user(user_id) if bot is not None else None
    if user is None and bot is not None:
        try:
            user = await bot.fetch_user(user_id)
        except Exception:
            user = None
    return user.display_name if user is not None else f"user_{user_id}"
