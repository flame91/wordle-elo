"""ELO state rebuild from the Submission table.

This is the single source of truth for "given the current set of submissions,
what should every player's ELO + streak look like?". Used by both:

- `scripts/recompute_elo` — offline full rebuild after rule changes.
- `pipeline._reprocess` — edit-triggered rebuild after a puzzle's submissions
  were wiped and re-inserted.

The Submission table is treated as authoritative; EloHistory and Player
counters are derived state.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select

from .elo import INITIAL as ELO_INITIAL
from .elo import compute_daily
from .models import EloHistory, Player, Submission

ELO_FLOOR = 100


async def rebuild_from_submissions(sessionmaker) -> None:
    """Wipe EloHistory + reset Player counters, then replay every Submission
    in puzzle_no order so EloHistory and Player state are consistent with
    whatever is currently in the Submission table.
    """
    async with sessionmaker() as session:
        await session.execute(delete(EloHistory))
        for p in (await session.execute(select(Player))).scalars():
            p.elo = ELO_INITIAL
            p.games_played = 0
            p.games_won = 0
            p.current_streak = 0
            p.best_streak = 0
        await session.commit()

    async with sessionmaker() as session:
        puzzle_nos = [
            r for (r,) in await session.execute(
                select(Submission.puzzle_no).distinct().order_by(Submission.puzzle_no)
            )
        ]

    now = datetime.now(timezone.utc)
    for puzzle_no in puzzle_nos:
        async with sessionmaker() as session:
            await _replay_one(session, puzzle_no, now)
            await session.commit()


async def _replay_one(session, puzzle_no: int, now: datetime) -> None:
    subs = (
        await session.execute(
            select(Submission).where(Submission.puzzle_no == puzzle_no)
        )
    ).scalars().all()
    if not subs:
        return

    submitter_ids = [s.user_id for s in subs]
    players = {
        p.user_id: p
        for p in (
            await session.execute(
                select(Player).where(Player.user_id.in_(submitter_ids))
            )
        ).scalars().all()
    }
    ratings_before = {uid: players[uid].elo for uid in submitter_ids}
    gp_before = {uid: players[uid].games_played for uid in submitter_ids}

    streaks_after: dict[int, int] = {}
    for s in subs:
        prev = players[s.user_id].current_streak
        won = s.guesses <= 6
        streaks_after[s.user_id] = (prev + 1) if won else 0

    subs_tuple = [(s.user_id, s.guesses, bool(s.hard_mode)) for s in subs]
    deltas = compute_daily(
        subs_tuple,
        ratings_before,
        streaks_after,
        games_played_before=gp_before,
    )

    for s in subs:
        p = players[s.user_id]
        d = deltas.get(s.user_id)
        d_total = d.delta_total if d else 0
        elo_after = max(ELO_FLOOR, p.elo + d_total)

        if d is not None:
            session.add(
                EloHistory(
                    puzzle_no=puzzle_no,
                    user_id=s.user_id,
                    elo_before=p.elo,
                    elo_after=elo_after,
                    delta_field=d.delta_field,
                    delta_speed=d.delta_speed,
                    delta_streak=d.delta_streak,
                    delta_hard=d.delta_hard,
                    delta_total=d.delta_total,
                    computed_at=now,
                )
            )

        p.elo = elo_after
        p.games_played += 1
        if s.guesses <= 6:
            p.games_won += 1
        p.current_streak = streaks_after[s.user_id]
        if p.current_streak > p.best_streak:
            p.best_streak = p.current_streak
