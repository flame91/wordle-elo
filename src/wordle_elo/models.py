from datetime import datetime

from sqlalchemy import BigInteger, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    elo: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    games_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    games_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(nullable=False)
    last_played_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Nickname(Base):
    """Display name for a user, refreshed from channel messages and live lookups.

    Decoupled from `Player` so identity refresh has no bearing on ELO state and
    so the backfill script can populate names from `msg.author` without touching
    rating rows.
    """

    __tablename__ = "nicknames"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    # 'member' (guild nickname or member.display_name) | 'user' (global display)
    # | 'channel_author' (refresh_nicknames script)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("puzzle_no", "user_id", name="uq_puzzle_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    puzzle_no: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    guesses: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..6 win, 7 = X fail
    hard_mode: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(nullable=False)


class EloHistory(Base):
    __tablename__ = "elo_history"
    __table_args__ = (UniqueConstraint("puzzle_no", "user_id", name="uq_elohist_puzzle_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    puzzle_no: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    elo_before: Mapped[int] = mapped_column(Integer, nullable=False)
    elo_after: Mapped[int] = mapped_column(Integer, nullable=False)
    delta_field: Mapped[float] = mapped_column(Float, nullable=False)
    delta_speed: Mapped[float] = mapped_column(Float, nullable=False)
    delta_streak: Mapped[float] = mapped_column(Float, nullable=False)
    delta_hard: Mapped[float] = mapped_column(Float, nullable=False)
    delta_total: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(nullable=False)


class ProcessedPuzzle(Base):
    __tablename__ = "processed_puzzles"

    puzzle_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(nullable=False)
    leaderboard_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class SeasonResult(Base):
    """Final standings of a finished quarterly season, one row per player.

    Written by the rollover job (or the one-time seasonize script) right before
    `Player.elo` is soft-reset for the next season, so the archive preserves
    each season's outcome independently of the live, ever-changing player rows.
    """

    __tablename__ = "season_results"
    __table_args__ = (UniqueConstraint("season", "user_id", name="uq_season_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[str] = mapped_column(String, nullable=False, index=True)  # "2026-Q1"
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    final_elo: Mapped[int] = mapped_column(Integer, nullable=False)
    games_played: Mapped[int] = mapped_column(Integer, nullable=False)  # within the season
    games_won: Mapped[int] = mapped_column(Integer, nullable=False)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_winning_guesses: Mapped[float | None] = mapped_column(Float, nullable=True)
    finalized_at: Mapped[datetime] = mapped_column(nullable=False)


class SeasonState(Base):
    """Single-row marker of the season currently in progress. The rollover job
    compares today's season against this to detect a quarter boundary."""

    __tablename__ = "season_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    current_season: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
