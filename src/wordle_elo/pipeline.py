"""Glue layer: discord message → parse → DB → ELO → leaderboard post.

The same `process_message` is used by both the live `on_message` handler and the
backfill / catch-up scripts. Idempotency is guaranteed by the
`processed_puzzles` table (puzzle_no PK).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select

from .elo import INITIAL as ELO_INITIAL
from .elo import compute_daily
from .leaderboard import format_daily_embed
from .models import EloHistory, Nickname, Player, ProcessedPuzzle, Submission
from .parser import parse_message
from .replay import rebuild_from_submissions
from .tier import assign_tier

log = logging.getLogger(__name__)
ELO_FLOOR = 100


async def process_message(
    bot, message, *, silent: bool = False, force_reprocess: bool = False
):
    """Top-level entry. Returns result dict or None if skipped.

    When `force_reprocess` is True and a ProcessedPuzzle row already exists,
    the puzzle's submissions/elo_history/processed_puzzles rows are wiped,
    re-inserted from the (possibly edited) message, and the full ELO state is
    rebuilt from the Submission table. The bot's original reply (if any) is
    edited in place rather than posting a new one.
    """
    parsed = parse_message(message)
    if parsed is None:
        log.debug("Skip unparseable message %s", message.id)
        return None

    sm = bot.sessionmaker
    async with sm() as session:
        existing = await session.get(ProcessedPuzzle, parsed.puzzle_no)

    if existing is not None and not force_reprocess:
        log.info("Puzzle %s already processed, skipping", parsed.puzzle_no)
        return None

    old_reply_id: int | None = None
    if existing is not None and force_reprocess:
        log.info("Reprocessing puzzle %s (edit detected)", parsed.puzzle_no)
        old_reply_id = existing.leaderboard_message_id
        result = await _reprocess(sm, bot, parsed, message)
    else:
        async with sm() as session:
            result = await _apply(session, bot, parsed, message)
            await session.commit()

    if silent:
        return result

    embed = format_daily_embed(parsed.puzzle_no, result["entries"])
    posted = await _post_or_edit_reply(message, embed, old_reply_id)
    if posted is not None:
        async with sm() as session:
            pp = await session.get(ProcessedPuzzle, parsed.puzzle_no)
            if pp is not None and pp.leaderboard_message_id != posted.id:
                pp.leaderboard_message_id = posted.id
                await session.commit()
    return result


async def _post_or_edit_reply(message, embed, old_reply_id: int | None):
    """If old_reply_id is set, try to edit that message in place; fall back to
    posting a new reply if the old message is missing or editing fails."""
    if old_reply_id is not None:
        try:
            old = await message.channel.fetch_message(old_reply_id)
            await old.edit(embed=embed)
            return old
        except Exception:
            log.warning(
                "Failed to edit prior leaderboard reply %s; posting new",
                old_reply_id,
            )
    try:
        return await message.reply(embed=embed, mention_author=False)
    except Exception:
        log.exception("Failed to post leaderboard reply")
        return None


async def _reprocess(sm, bot, parsed, source_msg):
    """Wipe this puzzle's data, re-insert from the parsed (edited) message,
    and rebuild ELO state from the full Submission table.
    """
    now = datetime.now(timezone.utc)
    when = source_msg.created_at if source_msg is not None else now

    async with sm() as session:
        await session.execute(
            delete(Submission).where(Submission.puzzle_no == parsed.puzzle_no)
        )
        await session.execute(
            delete(EloHistory).where(EloHistory.puzzle_no == parsed.puzzle_no)
        )
        await session.execute(
            delete(ProcessedPuzzle).where(
                ProcessedPuzzle.puzzle_no == parsed.puzzle_no
            )
        )

        for s in parsed.submissions:
            if await session.get(Player, s.user_id) is None:
                session.add(
                    Player(user_id=s.user_id, elo=ELO_INITIAL, first_seen_at=when)
                )
            await _upsert_nickname(session, bot, s.user_id, when)
        await session.flush()

        for s in parsed.submissions:
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
        await session.commit()

    await rebuild_from_submissions(sm)

    async with sm() as session:
        session.add(
            ProcessedPuzzle(
                puzzle_no=parsed.puzzle_no,
                source_message_id=source_msg.id if source_msg is not None else 0,
                processed_at=now,
            )
        )
        await session.commit()

    return await _build_entries_for_reply(sm, parsed.puzzle_no)


async def _build_entries_for_reply(sm, puzzle_no: int) -> dict:
    """Read EloHistory+Submission+Player and assemble the entry list the daily
    embed renderer expects."""
    async with sm() as session:
        history = (
            await session.execute(
                select(EloHistory).where(EloHistory.puzzle_no == puzzle_no)
            )
        ).scalars().all()
        subs = (
            await session.execute(
                select(Submission).where(Submission.puzzle_no == puzzle_no)
            )
        ).scalars().all()
        submitter_ids = [h.user_id for h in history]
        players = {
            p.user_id: p
            for p in (
                await session.execute(
                    select(Player).where(Player.user_id.in_(submitter_ids))
                )
            ).scalars().all()
        }
        all_ratings = [r for (r,) in (await session.execute(select(Player.elo)))]

    subs_by_uid = {s.user_id: s for s in subs}
    entries = []
    for h in history:
        sub = subs_by_uid.get(h.user_id)
        if sub is None:
            continue
        entries.append(
            {
                "user_id": h.user_id,
                "guesses": sub.guesses,
                "hard_mode": bool(sub.hard_mode),
                "elo_before": h.elo_before,
                "elo_after": h.elo_after,
                "delta_total": h.delta_total,
            }
        )
    entries.sort(key=lambda e: (e["guesses"], -e["delta_total"]))
    for e in entries:
        p = players.get(e["user_id"])
        if p is not None:
            e["tier"] = assign_tier(e["elo_after"], all_ratings, p.games_played)
    return {"puzzle_no": puzzle_no, "entries": entries}


async def _apply(session, bot, parsed, source_msg):
    now = datetime.now(timezone.utc)
    when = source_msg.created_at if source_msg is not None else now

    submitter_ids = [s.user_id for s in parsed.submissions]

    # Ensure player rows exist + refresh nicknames from the live cache
    for s in parsed.submissions:
        existing = await session.get(Player, s.user_id)
        if existing is None:
            session.add(Player(user_id=s.user_id, elo=ELO_INITIAL, first_seen_at=when))
        await _upsert_nickname(session, bot, s.user_id, now)
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


async def _resolve_display_name(bot, user_id: int) -> tuple[str | None, str]:
    """Lookup the channel-visible name without making extra HTTP calls.

    Returns (name, source). Source is 'member' if we got Member.display_name
    (server nickname or global display), 'user' if only a global User was
    available, or 'fallback' (with name=None) so callers can decide whether to
    overwrite an existing nickname row.
    """
    if bot is None:
        return None, "fallback"
    guild_id = getattr(getattr(bot, "cfg", None), "discord_guild_id", None)
    if guild_id is not None:
        guild = bot.get_guild(guild_id)
        if guild is not None:
            member = guild.get_member(user_id)
            if member is not None:
                return member.display_name, "member"
    user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except Exception:
            user = None
    if user is not None:
        return user.display_name, "user"
    return None, "fallback"


async def _upsert_nickname(session, bot, user_id: int, when: datetime) -> None:
    """Refresh the user's display name from live Discord state.

    On a 'fallback' resolution (couldn't reach Discord at all) we leave any
    existing Nickname row untouched — better stale than overwritten with garbage.
    The refresh_nicknames script handles bulk repair from channel author history.
    """
    name, source = await _resolve_display_name(bot, user_id)
    existing = await session.get(Nickname, user_id)
    if name is None:
        return
    if existing is None:
        session.add(
            Nickname(
                user_id=user_id,
                display_name=name,
                source=source,
                updated_at=when,
            )
        )
        return
    if existing.display_name != name or existing.source != source:
        existing.display_name = name
        existing.source = source
        existing.updated_at = when
