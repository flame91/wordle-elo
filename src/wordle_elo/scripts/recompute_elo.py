"""Drop and rebuild the elo_history + reset player counters, then replay all
submissions in puzzle_no order. Use after changing K, scoring rules, or fixing
the parser. Does NOT touch Discord.

Run with:
    docker compose run --rm bot python -m wordle_elo.scripts.recompute_elo
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select

from ..config import load_config
from ..db import init_db, make_engine, make_sessionmaker
from ..elo import INITIAL as ELO_INITIAL
from ..elo import compute_daily
from ..models import EloHistory, Player, Submission

log = logging.getLogger(__name__)
ELO_FLOOR = 100


async def recompute(cfg) -> None:
    engine = make_engine(cfg.db_path)
    await init_db(engine)
    sm = make_sessionmaker(engine)

    async with sm() as session:
        await session.execute(delete(EloHistory))
        for p in (await session.execute(select(Player))).scalars():
            p.elo = ELO_INITIAL
            p.games_played = 0
            p.games_won = 0
            p.current_streak = 0
            p.best_streak = 0
        await session.commit()

    async with sm() as session:
        puzzle_nos = [
            r for (r,) in await session.execute(
                select(Submission.puzzle_no).distinct().order_by(Submission.puzzle_no)
            )
        ]

    print(f"# Replaying {len(puzzle_nos)} puzzles from scratch")
    now = datetime.now(timezone.utc)

    for puzzle_no in puzzle_nos:
        async with sm() as session:
            subs = (
                await session.execute(
                    select(Submission).where(Submission.puzzle_no == puzzle_no)
                )
            ).scalars().all()
            if not subs:
                continue

            submitter_ids = [s.user_id for s in subs]
            players = {
                p.user_id: p for p in (
                    await session.execute(
                        select(Player).where(Player.user_id.in_(submitter_ids))
                    )
                ).scalars().all()
            }
            ratings_before = {uid: players[uid].elo for uid in submitter_ids}
            gp_before = {uid: players[uid].games_played for uid in submitter_ids}

            streaks_after = {}
            for s in subs:
                prev = players[s.user_id].current_streak
                won = s.guesses <= 6
                streaks_after[s.user_id] = (prev + 1) if won else 0

            subs_tuple = [(s.user_id, s.guesses, bool(s.hard_mode)) for s in subs]
            deltas = compute_daily(
                subs_tuple, ratings_before, streaks_after,
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

            await session.commit()

    print("# Done")


def main():
    logging.basicConfig(level=logging.INFO)
    argparse.ArgumentParser().parse_args()  # accept no args; placeholder
    cfg = load_config()
    asyncio.run(recompute(cfg))


if __name__ == "__main__":
    main()
