"""The /leaderboard board has no activity cut-off: every player who has ever
played is shown, no matter how long ago, ordered by ELO. Players who have
never played (last_played_at is NULL) are still excluded.

Exercises the same query the cog runs against an in-memory SQLite session.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo.models import Base, Player


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _board_query():
    return (
        select(Player)
        .where(Player.last_played_at.is_not(None))
        .order_by(desc(Player.elo))
    )


async def test_long_inactive_player_still_shown(sessionmaker):
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        session.add_all([
            Player(user_id=1, elo=1500, first_seen_at=now,
                   last_played_at=now - timedelta(days=1)),
            Player(user_id=2, elo=1300, first_seen_at=now,
                   last_played_at=now - timedelta(days=90)),  # long break
            Player(user_id=3, elo=1100, first_seen_at=now,
                   last_played_at=None),  # never played → excluded
        ])
        await session.commit()

    async with sessionmaker() as session:
        rows = (await session.execute(_board_query())).scalars().all()

    # The 90-days-idle player is still on the board; only never-played is gone.
    assert [p.user_id for p in rows] == [1, 2]


async def test_board_preserves_elo_ordering(sessionmaker):
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        session.add_all([
            Player(user_id=1, elo=1200, first_seen_at=now,
                   last_played_at=now - timedelta(hours=2)),
            Player(user_id=2, elo=1800, first_seen_at=now,
                   last_played_at=now - timedelta(days=200)),
            Player(user_id=3, elo=900,  first_seen_at=now,
                   last_played_at=now - timedelta(days=1)),
        ])
        await session.commit()

    async with sessionmaker() as session:
        rows = (await session.execute(_board_query())).scalars().all()

    assert [p.user_id for p in rows] == [2, 1, 3]
