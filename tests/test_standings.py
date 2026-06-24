"""Standings loader tests — ELO and Glicko-2 row builders share the player
query (no activity cut-off), nickname join, and avg-winning-guesses GROUP BY."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo import season
from wordle_elo.models import Base, Nickname, Player, SeasonState, Submission
from wordle_elo.standings import (
    build_elo_rows,
    build_glicko2_rows,
)


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed_four_players_one_idle(sessionmaker):
    now = datetime.now(timezone.utc)
    fresh = now - timedelta(hours=1)
    idle = now - timedelta(days=30)  # long break — no longer filtered out
    async with sessionmaker() as session:
        session.add_all([
            Player(user_id=1, elo=1200, games_played=10, games_won=8,
                   best_streak=3, current_streak=1, first_seen_at=now,
                   last_played_at=fresh),
            Player(user_id=2, elo=1400, games_played=12, games_won=11,
                   best_streak=4, current_streak=2, first_seen_at=now,
                   last_played_at=fresh),
            Player(user_id=3, elo=900,  games_played=5,  games_won=2,
                   best_streak=1, current_streak=0, first_seen_at=now,
                   last_played_at=fresh),
            Player(user_id=4, elo=1700, games_played=20, games_won=18,
                   best_streak=10, current_streak=0, first_seen_at=now,
                   last_played_at=idle),  # idle but still shown
        ])
        session.add_all([
            Nickname(user_id=1, display_name="alice", source="member", updated_at=now),
            Nickname(user_id=2, display_name="bob",   source="member", updated_at=now),
            # user 3 has no nickname row — exercises the None fallback
        ])
        session.add_all([
            Submission(puzzle_no=1, user_id=1, guesses=3, hard_mode=0, submitted_at=fresh),
            Submission(puzzle_no=1, user_id=2, guesses=4, hard_mode=0, submitted_at=fresh),
            Submission(puzzle_no=1, user_id=3, guesses=5, hard_mode=0, submitted_at=fresh),
            Submission(puzzle_no=2, user_id=1, guesses=2, hard_mode=0, submitted_at=fresh),
            Submission(puzzle_no=2, user_id=2, guesses=4, hard_mode=0, submitted_at=fresh),
            Submission(puzzle_no=2, user_id=3, guesses=7, hard_mode=0, submitted_at=fresh),  # X/6 → not in avg
            Submission(puzzle_no=3, user_id=4, guesses=3, hard_mode=0, submitted_at=idle),  # idle player
        ])
        await session.commit()


async def test_elo_rows_orders_by_stored_elo_and_includes_idle(sessionmaker):
    await _seed_four_players_one_idle(sessionmaker)
    rows = await build_elo_rows(sessionmaker)
    # Idle player 4 (highest ELO) is still on the board, ordered by ELO desc.
    assert [r["user_id"] for r in rows] == [4, 2, 1, 3]
    # Display name passthrough
    by_uid = {r["user_id"]: r for r in rows}
    assert by_uid[2]["display_name"] == "bob"
    assert by_uid[3]["display_name"] is None


async def test_elo_rows_avg_uses_only_winning_submissions(sessionmaker):
    await _seed_four_players_one_idle(sessionmaker)
    rows = await build_elo_rows(sessionmaker)
    by_uid = {r["user_id"]: r for r in rows}
    # User 1 wins: 3 and 2 → avg 2.5
    assert by_uid[1]["avg_winning_guesses"] == pytest.approx(2.5)
    # User 3 wins: 5 (X/6 excluded) → avg 5.0
    assert by_uid[3]["avg_winning_guesses"] == pytest.approx(5.0)


async def test_elo_rows_stats_scoped_to_current_season(sessionmaker):
    """With a SeasonState set, the displayed games/wins/streak/avg cover only
    the current season's puzzles — not the player's all-time totals."""
    now = datetime.now(timezone.utc)
    q2_lo = season.first_puzzle_no("2026-Q2")  # 1747
    q1 = q2_lo - 5  # a Q1 puzzle (previous season)
    async with sessionmaker() as session:
        session.add(SeasonState(id=1, current_season="2026-Q2", updated_at=now))
        # All-time Player counters are large, but only the in-season submissions
        # should drive the row.
        session.add(Player(user_id=1, elo=1200, games_played=99, games_won=99,
                           best_streak=50, current_streak=50, first_seen_at=now,
                           last_played_at=now))
        session.add_all([
            # Previous season — must be excluded
            Submission(puzzle_no=q1, user_id=1, guesses=2, hard_mode=0, submitted_at=now),
            # Current season — 2 wins (3,5) + 1 fail
            Submission(puzzle_no=q2_lo, user_id=1, guesses=3, hard_mode=0, submitted_at=now),
            Submission(puzzle_no=q2_lo + 1, user_id=1, guesses=5, hard_mode=0, submitted_at=now),
            Submission(puzzle_no=q2_lo + 2, user_id=1, guesses=7, hard_mode=0, submitted_at=now),
        ])
        await session.commit()

    rows = await build_elo_rows(sessionmaker)
    row = rows[0]
    assert row["games_played"] == 3      # not 99
    assert row["games_won"] == 2
    assert row["best_streak"] == 2       # 3,5 consecutive wins before the X
    assert row["current_streak"] == 0    # last game was a fail
    assert row["avg_winning_guesses"] == pytest.approx(4.0)  # (3+5)/2


async def test_glicko2_rows_orders_by_computed_rating_not_stored_elo(sessionmaker):
    """If stored ELO and Glicko-2 disagree on ordering, build_glicko2_rows must
    follow Glicko-2 — that's the whole point of selecting a different algorithm."""
    now = datetime.now(timezone.utc)
    fresh = now - timedelta(hours=1)
    async with sessionmaker() as session:
        # Stored ELO would put #2 first (1500 > 1100), but Glicko-2 replay should
        # crown #1 because #1 consistently beats #2 in head-to-head submissions.
        session.add_all([
            Player(user_id=1, elo=1100, games_played=5, games_won=5,
                   best_streak=5, current_streak=5, first_seen_at=now,
                   last_played_at=fresh),
            Player(user_id=2, elo=1500, games_played=5, games_won=5,
                   best_streak=5, current_streak=5, first_seen_at=now,
                   last_played_at=fresh),
        ])
        for puzzle_no in range(1, 6):
            session.add(Submission(puzzle_no=puzzle_no, user_id=1, guesses=2,
                                   hard_mode=0, submitted_at=fresh))
            session.add(Submission(puzzle_no=puzzle_no, user_id=2, guesses=5,
                                   hard_mode=0, submitted_at=fresh))
        await session.commit()

    rows = await build_glicko2_rows(sessionmaker)
    assert [r["user_id"] for r in rows] == [1, 2]
    assert rows[0]["rating"] > rows[1]["rating"]


async def test_glicko2_rows_include_rd(sessionmaker):
    await _seed_four_players_one_idle(sessionmaker)
    rows = await build_glicko2_rows(sessionmaker)
    assert rows  # not empty
    for r in rows:
        assert "rating_rd" in r
        assert r["rating_rd"] > 0


async def test_glicko2_rows_include_idle_players_with_submissions(sessionmaker):
    await _seed_four_players_one_idle(sessionmaker)
    rows = await build_glicko2_rows(sessionmaker)
    assert 4 in [r["user_id"] for r in rows]


async def test_both_loaders_empty_when_no_one_has_played(sessionmaker):
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        # Registered but never played (last_played_at is NULL, no submissions).
        session.add(
            Player(user_id=1, elo=1500, games_played=0, games_won=0,
                   best_streak=0, current_streak=0, first_seen_at=now,
                   last_played_at=None)
        )
        await session.commit()

    assert await build_elo_rows(sessionmaker) == []
    assert await build_glicko2_rows(sessionmaker) == []
