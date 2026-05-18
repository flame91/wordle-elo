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

from ..config import bootstrap
from ..db import init_db, make_engine, make_sessionmaker
from ..replay import rebuild_from_submissions

log = logging.getLogger(__name__)


async def recompute(cfg) -> None:
    engine = make_engine(cfg.db_path)
    await init_db(engine)
    sm = make_sessionmaker(engine)
    print("# Rebuilding ELO state from submissions")
    await rebuild_from_submissions(sm)
    print("# Done")


def main():
    logging.basicConfig(level=logging.INFO)
    argparse.ArgumentParser().parse_args()
    cfg = bootstrap()
    asyncio.run(recompute(cfg))


if __name__ == "__main__":
    main()
