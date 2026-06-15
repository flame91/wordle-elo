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
from .models import EloHistory, Nickname, Player, ProcessedPuzzle, Submission
from .parser import parse_message
from .resolve import resolve_message
from .seasons import current_season_label, maybe_rollover
from .standings import build_elo_rows, render_leaderboard_embed
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
        # Daily summary (who played + delta) first, then the full standings —
        # identical to /leaderboard (active-7-day ELO board), so the daily post
        # shows everyone's current rank, not just today's submitters.
        embeds = [format_daily_embed(parsed.puzzle_no, result["entries"])]
        try:
            rows = await build_elo_rows(sm)
            if rows:
                label = await current_season_label(sm)
                embeds.append(render_leaderboard_embed(rows, "elo", season_label=label))
        except Exception:
            log.exception("Failed to build standings for puzzle %s", parsed.puzzle_no)
        try:
            posted = await message.reply(embeds=embeds, mention_author=False)
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

    # Season boundary check runs before scoring so the first puzzle of a new
    # quarter is rated against soft-reset standings (and only existing players
    # are reset — this puzzle's newcomers start fresh below).
    await maybe_rollover(session, bot, parsed.puzzle_no, when=when)

    # Wordle Activity sometimes renders a user as plain text (@name) instead of a
    # real mention (<@id>); fold those back in by resolving names against the
    # guild member cache / nickname history. Names we can't resolve uniquely are
    # skipped (never guessed) and logged.
    guild = _guild_from_bot(bot)
    submissions, skipped = await resolve_message(parsed, guild, session)
    for outcome in skipped:
        log.warning(
            "Puzzle %s: unresolved plain-text name @%s (%s, candidates=%s) — skipped",
            parsed.puzzle_no, outcome.name, outcome.source, outcome.candidates,
        )

    submitter_ids = [s.user_id for s in submissions]

    # Ensure player rows exist + refresh nicknames from the live cache
    for s in submissions:
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
    for s in submissions:
        prev = players[s.user_id].current_streak
        streaks_after[s.user_id] = (prev + 1) if s.won else 0

    subs_tuple = [(s.user_id, s.guesses, s.hard_mode) for s in submissions]
    deltas = compute_daily(
        subs_tuple, ratings_before, streaks_after,
        games_played_before=games_played_before,
    )

    entries = []
    for s in submissions:
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


def _guild_from_bot(bot):
    """The configured guild from the live cache, or None if unavailable."""
    if bot is None:
        return None
    guild_id = getattr(getattr(bot, "cfg", None), "discord_guild_id", None)
    if guild_id is None:
        return None
    return bot.get_guild(guild_id)


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
