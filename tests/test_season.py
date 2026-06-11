from datetime import date

from wordle_elo import season


def test_puzzle_date_matches_parser_epoch():
    # puzzle 1586 is the 2025-10-22 Wordle (matches SEASON_START_DATE default)
    assert season.puzzle_date(1586) == date(2025, 10, 22)
    assert season.puzzle_date(0) == date(2021, 6, 19)


def test_season_label():
    assert season.season_label(date(2026, 1, 1)) == "2026-Q1"
    assert season.season_label(date(2026, 3, 31)) == "2026-Q1"
    assert season.season_label(date(2026, 4, 1)) == "2026-Q2"
    assert season.season_label(date(2026, 12, 31)) == "2026-Q4"


def test_season_of_puzzle_boundaries():
    assert season.season_of_puzzle(1656) == "2025-Q4"  # 2025-12-31
    assert season.season_of_puzzle(1657) == "2026-Q1"  # 2026-01-01
    assert season.season_of_puzzle(1746) == "2026-Q1"  # 2026-03-31
    assert season.season_of_puzzle(1747) == "2026-Q2"  # 2026-04-01


def test_first_puzzle_no_round_trips():
    assert season.first_puzzle_no("2026-Q1") == 1657
    assert season.first_puzzle_no("2026-Q2") == 1747
    assert season.first_puzzle_no("2026-Q3") == 1838


def test_label_navigation():
    assert season.next_label("2026-Q1") == "2026-Q2"
    assert season.next_label("2026-Q4") == "2027-Q1"
    assert season.prev_label("2026-Q1") == "2025-Q4"
    assert season.season_start_date("2026-Q2") == date(2026, 4, 1)
    assert season.season_end_date("2026-Q1") == date(2026, 3, 31)
    assert season.season_end_date("2026-Q4") == date(2026, 12, 31)


def test_soft_reset_partial_carry_preserves_order_and_pulls_to_anchor():
    assert season.soft_reset(1500, carry=0.5, anchor=1000) == 1250
    assert season.soft_reset(800, carry=0.5, anchor=1000) == 900
    assert season.soft_reset(1000, carry=0.5, anchor=1000) == 1000
    # a positive carry preserves skill order
    assert (
        season.soft_reset(1500, carry=0.5)
        > season.soft_reset(1200, carry=0.5)
        > season.soft_reset(1000, carry=0.5)
    )


def test_soft_reset_zero_carry_is_hard_reset_to_anchor():
    # carry=0 collapses everyone to the anchor — the default hard reset.
    assert season.soft_reset(1500, carry=0.0, anchor=1000) == 1000
    assert season.soft_reset(800, carry=0.0, anchor=1000) == 1000
