"""Quarterly-season helpers: map puzzles/dates to calendar-quarter seasons,
compute boundaries, and apply the between-season soft reset.

Calendar quarters: Q1 Jan–Mar, Q2 Apr–Jun, Q3 Jul–Sep, Q4 Oct–Dec. A puzzle
belongs to the season of its *puzzle date* (the Wordle day), which is
``WORDLE_EPOCH + puzzle_no`` days — the same mapping the parser uses when it
derives a puzzle number from a message date (see ``parser._puzzle_no_from_created_at``).

The season "clock" starts at ``SEASON_EPOCH`` (default 2026-01-01): the rollover
job only finalises / announces / soft-resets at quarter boundaries on or after
this date. Earlier puzzles (the pre-season warm-up) seed the first season's
ratings without a reset.

This module is pure (no DB, no Discord) so it stays trivially testable.
"""

from __future__ import annotations

from datetime import date, timedelta

# Module-level defaults; override at startup via `configure()`.
WORDLE_EPOCH = date(2021, 6, 19)  # puzzle 0's date; mirrors parser.EPOCH_DATE
SEASON_EPOCH = date(2026, 1, 1)   # first season boundary the rollover job acts on
SOFT_RESET_CARRY = 0.5            # fraction of (elo - anchor) kept across a season
RESET_ANCHOR = 1000              # ratings regress toward this on rollover


def configure(
    *,
    wordle_epoch: date | None = None,
    season_epoch: date | None = None,
    carry: float | None = None,
    anchor: int | None = None,
) -> None:
    """Override module-level season knobs from env / config. Idempotent."""
    global WORDLE_EPOCH, SEASON_EPOCH, SOFT_RESET_CARRY, RESET_ANCHOR
    if wordle_epoch is not None:
        WORDLE_EPOCH = wordle_epoch
    if season_epoch is not None:
        SEASON_EPOCH = season_epoch
    if carry is not None:
        SOFT_RESET_CARRY = carry
    if anchor is not None:
        RESET_ANCHOR = anchor


def puzzle_date(puzzle_no: int, epoch: date | None = None) -> date:
    """Calendar date of the Wordle puzzle with this number."""
    return (epoch or WORDLE_EPOCH) + timedelta(days=puzzle_no)


def quarter(d: date) -> int:
    return (d.month - 1) // 3 + 1


def season_label(d: date) -> str:
    """e.g. date(2026, 5, 1) -> '2026-Q2'."""
    return f"{d.year}-Q{quarter(d)}"


def season_of_puzzle(puzzle_no: int, epoch: date | None = None) -> str:
    return season_label(puzzle_date(puzzle_no, epoch))


def _parse_label(label: str) -> tuple[int, int]:
    year_s, q_s = label.split("-Q")
    return int(year_s), int(q_s)


def season_start_date(label: str) -> date:
    """First calendar day of a season label."""
    year, q = _parse_label(label)
    return date(year, (q - 1) * 3 + 1, 1)


def season_end_date(label: str) -> date:
    """Last calendar day (inclusive) of a season label."""
    return next_season_start_date(label) - timedelta(days=1)


def next_label(label: str) -> str:
    year, q = _parse_label(label)
    return f"{year + 1}-Q1" if q == 4 else f"{year}-Q{q + 1}"


def prev_label(label: str) -> str:
    year, q = _parse_label(label)
    return f"{year - 1}-Q4" if q == 1 else f"{year}-Q{q - 1}"


def next_season_start_date(label: str) -> date:
    return season_start_date(next_label(label))


def first_puzzle_no(label: str, epoch: date | None = None) -> int:
    """Puzzle number of the first puzzle in a season (its start date)."""
    return (season_start_date(label) - (epoch or WORDLE_EPOCH)).days


_QUARTER_MONTHS = {1: "Jan–Mar", 2: "Apr–Jun", 3: "Jul–Sep", 4: "Oct–Dec"}


def season_period(label: str) -> str:
    """Human month range for a season label, e.g. '2026-Q2' -> 'Apr–Jun'."""
    _year, q = _parse_label(label)
    return _QUARTER_MONTHS[q]


def label_with_period(label: str) -> str:
    """Season label annotated with its months, e.g. '2026-Q2 (Apr–Jun)'."""
    return f"{label} ({season_period(label)})"


def soft_reset(elo: int, carry: float | None = None, anchor: int | None = None) -> int:
    """Regress a rating toward the anchor for the next season.

    new = anchor + (elo - anchor) * carry. With carry=0.5, anchor=1000 a 1500
    becomes 1250 and an 800 becomes 900 — skill order is preserved but the
    field is pulled back together so a new season is competitive from day one.
    """
    c = SOFT_RESET_CARRY if carry is None else carry
    a = RESET_ANCHOR if anchor is None else anchor
    return round(a + (elo - a) * c)
