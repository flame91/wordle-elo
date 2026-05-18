"""Smoke tests for rebuild_from_submissions — the shared replay loop."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo.models import Base, EloHistory, Player, Submission
from wordle_elo.replay import rebuild_from_submissions


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(sessionmaker, players: list[int], subs: list[tuple[int, int, int]]):
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        for uid in players:
            session.add(Player(user_id=uid, elo=1000, first_seen_at=now))
        for puzzle_no, user_id, guesses in subs:
            session.add(
                Submission(
                    puzzle_no=puzzle_no,
                    user_id=user_id,
                    guesses=guesses,
                    hard_mode=0,
                    submitted_at=now,
                )
            )
        await session.commit()


async def test_rebuild_replays_in_puzzle_order_and_counts_games(sessionmaker):
    await _seed(
        sessionmaker,
        players=[1, 2],
        subs=[(1, 1, 3), (1, 2, 5), (2, 1, 4), (2, 2, 7)],
    )
    await rebuild_from_submissions(sessionmaker)

    async with sessionmaker() as session:
        players = {
            p.user_id: p
            for p in (await session.execute(_select_all_players())).scalars().all()
        }
        history = (await session.execute(_select_all_history())).scalars().all()

    # 2 puzzles × 2 players = 4 EloHistory rows
    assert len(history) == 4
    # Player 1 played 2 games, won both (3/6 then 4/6)
    assert players[1].games_played == 2
    assert players[1].games_won == 2
    # Player 2 played 2, won 1 (5/6 win, X/6 loss)
    assert players[2].games_played == 2
    assert players[2].games_won == 1


async def test_rebuild_is_idempotent(sessionmaker):
    await _seed(sessionmaker, players=[1], subs=[(1, 1, 3), (2, 1, 4)])
    await rebuild_from_submissions(sessionmaker)
    async with sessionmaker() as session:
        elo1 = (await session.get(Player, 1)).elo

    await rebuild_from_submissions(sessionmaker)
    async with sessionmaker() as session:
        elo2 = (await session.get(Player, 1)).elo

    assert elo1 == elo2


async def test_rebuild_clears_orphan_elo_history(sessionmaker):
    """EloHistory rows for puzzles with no Submissions should be wiped."""
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        session.add(Player(user_id=1, elo=1000, first_seen_at=now))
        session.add(
            EloHistory(
                puzzle_no=99,
                user_id=1,
                elo_before=1000,
                elo_after=1010,
                delta_field=6,
                delta_speed=0,
                delta_streak=0,
                delta_hard=0,
                delta_total=10,
                computed_at=now,
            )
        )
        await session.commit()

    await rebuild_from_submissions(sessionmaker)

    async with sessionmaker() as session:
        history = (await session.execute(_select_all_history())).scalars().all()
    assert history == []


def _select_all_players():
    from sqlalchemy import select
    return select(Player)


def _select_all_history():
    from sqlalchemy import select
    return select(EloHistory)
