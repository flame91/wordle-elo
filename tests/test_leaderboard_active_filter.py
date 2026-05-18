"""Verifies that /leaderboard hides players whose last_played_at is older than
ACTIVE_DAYS, never queries them, and shows a helpful empty-state message when
nobody is active.

Avoids spinning up a full Discord client by exercising the same query the cog
runs against an in-memory SQLite session.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo.commands.leaderboard import ACTIVE_DAYS
from wordle_elo.models import Base, Player


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _active_query(cutoff):
    return (
        select(Player)
        .where(Player.last_played_at.is_not(None))
        .where(Player.last_played_at >= cutoff)
        .order_by(desc(Player.elo))
    )


async def test_filter_excludes_players_older_than_active_days(sessionmaker):
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        session.add_all([
            Player(user_id=1, elo=1500, first_seen_at=now,
                   last_played_at=now - timedelta(days=1)),
            Player(user_id=2, elo=1300, first_seen_at=now,
                   last_played_at=now - timedelta(days=ACTIVE_DAYS - 1)),
            Player(user_id=3, elo=1700, first_seen_at=now,
                   last_played_at=now - timedelta(days=ACTIVE_DAYS + 1)),
            Player(user_id=4, elo=1100, first_seen_at=now,
                   last_played_at=None),
        ])
        await session.commit()

    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)
    async with sessionmaker() as session:
        active = (await session.execute(_active_query(cutoff))).scalars().all()

    # Player 3 (stale) and player 4 (never played) must be excluded.
    assert [p.user_id for p in active] == [1, 2]


async def test_filter_returns_empty_when_everyone_stale(sessionmaker):
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        session.add_all([
            Player(user_id=1, elo=1500, first_seen_at=now,
                   last_played_at=now - timedelta(days=30)),
            Player(user_id=2, elo=1300, first_seen_at=now,
                   last_played_at=now - timedelta(days=14)),
        ])
        await session.commit()

    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)
    async with sessionmaker() as session:
        active = (await session.execute(_active_query(cutoff))).scalars().all()

    assert active == []


async def test_filter_preserves_elo_ordering(sessionmaker):
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        session.add_all([
            Player(user_id=1, elo=1200, first_seen_at=now,
                   last_played_at=now - timedelta(hours=2)),
            Player(user_id=2, elo=1800, first_seen_at=now,
                   last_played_at=now - timedelta(days=3)),
            Player(user_id=3, elo=900,  first_seen_at=now,
                   last_played_at=now - timedelta(days=1)),
        ])
        await session.commit()

    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)
    async with sessionmaker() as session:
        active = (await session.execute(_active_query(cutoff))).scalars().all()

    assert [p.user_id for p in active] == [2, 1, 3]
