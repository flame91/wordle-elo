"""Smoke test for the shared standings loader."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo.models import Base, Player, Submission
from wordle_elo.standings import build_leaderboard_rows


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_returns_empty_when_no_players(sessionmaker):
    rows = await build_leaderboard_rows(sessionmaker)
    assert rows == []


async def test_orders_by_elo_descending_and_includes_avg(sessionmaker):
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        session.add_all([
            Player(user_id=1, elo=1200, games_played=10, games_won=8, first_seen_at=now),
            Player(user_id=2, elo=1500, games_played=20, games_won=18, first_seen_at=now),
            Player(user_id=3, elo=900,  games_played=5,  games_won=2,  first_seen_at=now),
        ])
        session.add_all([
            Submission(puzzle_no=1, user_id=2, guesses=3, hard_mode=0, submitted_at=now),
            Submission(puzzle_no=2, user_id=2, guesses=5, hard_mode=0, submitted_at=now),
            Submission(puzzle_no=1, user_id=1, guesses=4, hard_mode=0, submitted_at=now),
            Submission(puzzle_no=1, user_id=3, guesses=7, hard_mode=0, submitted_at=now),  # X/6, excluded from avg
        ])
        await session.commit()

    rows = await build_leaderboard_rows(sessionmaker)
    assert [r["user_id"] for r in rows] == [2, 1, 3]
    assert rows[0]["avg_winning_guesses"] == pytest.approx(4.0)   # (3 + 5) / 2
    assert rows[1]["avg_winning_guesses"] == pytest.approx(4.0)   # just 4
    assert rows[2]["avg_winning_guesses"] is None                  # X/6 only → no winning avg
    # tier names are computed against the full ratings list
    assert all("tier" in r for r in rows)
