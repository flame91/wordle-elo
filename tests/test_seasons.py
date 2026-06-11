"""Season rollover service: boundary detection, archive, soft reset."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo import season
from wordle_elo.models import Base, Player, SeasonResult, SeasonState, Submission
from wordle_elo.seasons import maybe_rollover, normalize_season_label

WHEN = datetime(2026, 4, 1, tzinfo=timezone.utc)

# Boundary puzzle numbers (verified against the live DB / parser epoch).
Q1_FIRST = season.first_puzzle_no("2026-Q1")  # 1657
Q2_FIRST = season.first_puzzle_no("2026-Q2")  # 1747


@pytest.fixture(autouse=True)
def _fixed_season_config():
    season.configure(season_epoch=date(2026, 1, 1), carry=0.5, anchor=1000)
    yield


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(sessionmaker):
    """Two players who each played one Q1 puzzle, with set final ELOs."""
    async with sessionmaker() as session:
        session.add_all([
            Player(user_id=1, elo=1500, games_played=1, games_won=1,
                   best_streak=1, current_streak=1, first_seen_at=WHEN, last_played_at=WHEN),
            Player(user_id=2, elo=900, games_played=1, games_won=0,
                   best_streak=0, current_streak=0, first_seen_at=WHEN, last_played_at=WHEN),
            Submission(puzzle_no=Q1_FIRST, user_id=1, guesses=3, hard_mode=0, submitted_at=WHEN),
            Submission(puzzle_no=Q1_FIRST, user_id=2, guesses=7, hard_mode=0, submitted_at=WHEN),
        ])
        await session.commit()


def test_normalize_season_label_accepts_loose_input():
    assert normalize_season_label("1", 2026) == "2026-Q1"
    assert normalize_season_label("q1", 2026) == "2026-Q1"
    assert normalize_season_label("Q3", 2026) == "2026-Q3"
    assert normalize_season_label("2025-Q4", 2026) == "2025-Q4"
    assert normalize_season_label("2025q4", 2026) == "2025-Q4"
    assert normalize_season_label("2025 4", 2026) == "2025-Q4"
    assert normalize_season_label("garbage", 2026) is None
    assert normalize_season_label("5", 2026) is None  # only quarters 1-4


async def test_first_puzzle_initializes_state_without_reset(sessionmaker):
    await _seed(sessionmaker)
    async with sessionmaker() as session:
        finalized = await maybe_rollover(session, None, Q1_FIRST, when=WHEN, post=False)
        await session.commit()
    assert finalized is None
    async with sessionmaker() as session:
        state = await session.get(SeasonState, 1)
        assert state.current_season == "2026-Q1"
        # No reset applied
        p1 = await session.get(Player, 1)
        assert p1.elo == 1500


async def test_same_season_puzzle_is_noop(sessionmaker):
    await _seed(sessionmaker)
    async with sessionmaker() as session:
        await maybe_rollover(session, None, Q1_FIRST, when=WHEN, post=False)
        await session.commit()
    async with sessionmaker() as session:
        finalized = await maybe_rollover(session, None, Q1_FIRST + 1, when=WHEN, post=False)
        await session.commit()
    assert finalized is None


async def test_quarter_boundary_archives_and_soft_resets(sessionmaker):
    await _seed(sessionmaker)
    # Initialize into Q1
    async with sessionmaker() as session:
        await maybe_rollover(session, None, Q1_FIRST, when=WHEN, post=False)
        await session.commit()
    # First Q2 puzzle triggers rollover
    async with sessionmaker() as session:
        finalized = await maybe_rollover(session, None, Q2_FIRST, when=WHEN, post=False)
        await session.commit()

    assert finalized == "2026-Q1"
    async with sessionmaker() as session:
        results = (
            await session.execute(
                select(SeasonResult).where(SeasonResult.season == "2026-Q1").order_by(SeasonResult.rank)
            )
        ).scalars().all()
        assert [(r.rank, r.user_id, r.final_elo) for r in results] == [
            (1, 1, 1500),
            (2, 2, 900),
        ]
        # winner stats: 1 game, 1 win
        assert results[0].games_played == 1 and results[0].games_won == 1
        assert results[0].avg_winning_guesses == 3.0
        assert results[1].games_won == 0 and results[1].avg_winning_guesses is None

        # Soft reset: 1500 -> 1250, 900 -> 950
        assert (await session.get(Player, 1)).elo == 1250
        assert (await session.get(Player, 2)).elo == 950

        state = await session.get(SeasonState, 1)
        assert state.current_season == "2026-Q2"


async def test_preseason_to_first_season_seeds_without_reset(sessionmaker):
    """Crossing from a pre-SEASON_EPOCH quarter into the first tracked season
    advances state but does NOT archive or reset (warm-up seeds Q1)."""
    async with sessionmaker() as session:
        session.add(Player(user_id=1, elo=1300, games_played=1, games_won=1,
                           best_streak=1, current_streak=1, first_seen_at=WHEN, last_played_at=WHEN))
        await session.commit()
    q4_2025 = season.first_puzzle_no("2025-Q4")
    async with sessionmaker() as session:
        await maybe_rollover(session, None, q4_2025, when=WHEN, post=False)
        await session.commit()
    async with sessionmaker() as session:
        finalized = await maybe_rollover(session, None, Q1_FIRST, when=WHEN, post=False)
        await session.commit()
    assert finalized is None  # no archive of the pre-season quarter
    async with sessionmaker() as session:
        assert (await session.get(Player, 1)).elo == 1300  # untouched
        # nothing archived
        assert (await session.execute(select(SeasonResult))).scalars().first() is None
