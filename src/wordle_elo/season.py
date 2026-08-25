"""Season helpers: map puzzles/dates to seasons, compute boundaries, and apply
the between-season soft reset.

Two cadences, one calendar. Up to ``MONTHLY_START`` a season is a calendar
quarter labelled ``YYYY-Qn`` (Q1 Jan–Mar … Q4 Oct–Dec); from ``MONTHLY_START``
on, a season is a single calendar month labelled ``YYYY-MM``. The quarter that
``MONTHLY_START`` falls inside is cut short at the switch — with the default
2026-09-01 anchor, ``2026-Q3`` runs Jul 1 → Aug 31 (two months) instead of
through September, and ``2026-09`` is the first monthly season.

A puzzle belongs to the season of its *puzzle date* (the Wordle day), which is
``WORDLE_EPOCH + puzzle_no`` days — the same mapping the parser uses when it
derives a puzzle number from a message date (see ``parser._puzzle_no_from_created_at``).
So the message that arrives on Sep 1 carries the Aug 31 puzzle and still scores
in ``2026-Q3``; the rollover fires on the Sep 1 puzzle, seen on Sep 2.

The season "clock" starts at ``SEASON_EPOCH`` (default 2026-01-01): the rollover
job only finalises / announces / soft-resets at boundaries on or after this
date. Earlier puzzles (the pre-season warm-up) seed the first season's ratings
without a reset.

This module is pure (no DB, no Discord) so it stays trivially testable.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# Module-level defaults; override at startup via `configure()`.
WORDLE_EPOCH = date(2021, 6, 19)  # puzzle 0's date; mirrors parser.EPOCH_DATE
SEASON_EPOCH = date(2026, 1, 1)   # first season boundary the rollover job acts on
MONTHLY_START = date(2026, 9, 1)  # quarterly before this date, monthly from it
SOFT_RESET_CARRY = 0.5            # fraction of (elo - anchor) kept across a season
RESET_ANCHOR = 1000              # ratings regress toward this on rollover


def configure(
    *,
    wordle_epoch: date | None = None,
    season_epoch: date | None = None,
    monthly_start: date | None = None,
    carry: float | None = None,
    anchor: int | None = None,
) -> None:
    """Override module-level season knobs from env / config. Idempotent.

    `monthly_start` must be the 1st of a month: every season from it on is a
    whole calendar month, and a mid-month anchor would leave a stub window no
    label could describe. Raising beats silently rounding — a wrong anchor
    misplaces every later boundary.
    """
    global WORDLE_EPOCH, SEASON_EPOCH, MONTHLY_START, SOFT_RESET_CARRY, RESET_ANCHOR
    if wordle_epoch is not None:
        WORDLE_EPOCH = wordle_epoch
    if season_epoch is not None:
        SEASON_EPOCH = season_epoch
    if monthly_start is not None:
        if monthly_start.day != 1:
            raise ValueError(
                f"monthly season anchor must be the 1st of a month, "
                f"got {monthly_start.isoformat()}"
            )
        MONTHLY_START = monthly_start
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
    """Label of the season a date falls in: '2026-Q2' before the monthly
    switch, '2026-09' from it on."""
    if d >= MONTHLY_START:
        return f"{d.year}-{d.month:02d}"
    return f"{d.year}-Q{quarter(d)}"


def season_of_puzzle(puzzle_no: int, epoch: date | None = None) -> str:
    return season_label(puzzle_date(puzzle_no, epoch))


QUARTER_LABEL_RE = re.compile(r"^(\d{4})-Q([1-4])$")
MONTH_LABEL_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def is_monthly_label(label: str) -> bool:
    return MONTH_LABEL_RE.match(label) is not None


def season_start_date(label: str) -> date:
    """First calendar day of a season label. Accepts both cadences."""
    m = QUARTER_LABEL_RE.match(label)
    if m:
        return date(int(m.group(1)), (int(m.group(2)) - 1) * 3 + 1, 1)
    m = MONTH_LABEL_RE.match(label)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    raise ValueError(f"unrecognised season label: {label!r}")


def _add_months(start: date, months: int) -> date:
    total = start.month - 1 + months
    return date(start.year + total // 12, total % 12 + 1, 1)


def next_season_start_date(label: str) -> date:
    """Start of the season that follows this one.

    The cadence switch truncates the quarter it lands inside: with the default
    anchor, 2026-Q3 hands over on 2026-09-01 rather than running to Oct 1.
    """
    start = season_start_date(label)
    natural = _add_months(start, 1 if is_monthly_label(label) else 3)
    if start < MONTHLY_START < natural:
        return MONTHLY_START
    return natural


def season_end_date(label: str) -> date:
    """Last calendar day (inclusive) of a season label."""
    return next_season_start_date(label) - timedelta(days=1)


def next_label(label: str) -> str:
    return season_label(next_season_start_date(label))


def prev_label(label: str) -> str:
    return season_label(season_start_date(label) - timedelta(days=1))


def first_puzzle_no(label: str, epoch: date | None = None) -> int:
    """Puzzle number of the first puzzle in a season (its start date)."""
    return (season_start_date(label) - (epoch or WORDLE_EPOCH)).days


_MONTH_NAMES = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def season_period(label: str) -> str:
    """Human month range for a season label: '2026-Q2' -> 'Apr–Jun',
    '2026-09' -> 'Sep', and a quarter cut short by the switch -> 'Jul–Aug'.

    Read off the season's real start and end rather than a per-quarter table,
    so a truncated season describes itself honestly.
    """
    start, end = season_start_date(label), season_end_date(label)
    if (start.year, start.month) == (end.year, end.month):
        return _MONTH_NAMES[start.month - 1]
    return f"{_MONTH_NAMES[start.month - 1]}–{_MONTH_NAMES[end.month - 1]}"


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
