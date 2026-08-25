from datetime import date

import pytest

from wordle_elo import season


@pytest.fixture(autouse=True)
def _restore_anchors():
    """configure() writes module globals; keep tests isolated from each other."""
    saved = (season.SEASON_EPOCH, season.MONTHLY_START, season.WORDLE_EPOCH)
    yield
    season.SEASON_EPOCH, season.MONTHLY_START, season.WORDLE_EPOCH = saved


def test_puzzle_date_matches_parser_epoch():
    # puzzle 1586 is the 2025-10-22 Wordle (matches SEASON_START_DATE default)
    assert season.puzzle_date(1586) == date(2025, 10, 22)
    assert season.puzzle_date(0) == date(2021, 6, 19)


def test_season_label_is_quarterly_before_the_monthly_switch():
    assert season.season_label(date(2026, 1, 1)) == "2026-Q1"
    assert season.season_label(date(2026, 3, 31)) == "2026-Q1"
    assert season.season_label(date(2026, 4, 1)) == "2026-Q2"
    assert season.season_label(date(2025, 12, 31)) == "2025-Q4"


def test_season_label_is_monthly_from_the_switch_on():
    assert season.season_label(date(2026, 9, 1)) == "2026-09"
    assert season.season_label(date(2026, 9, 30)) == "2026-09"
    assert season.season_label(date(2026, 10, 1)) == "2026-10"
    assert season.season_label(date(2026, 12, 31)) == "2026-12"
    assert season.season_label(date(2027, 1, 1)) == "2027-01"


def test_the_switch_cuts_its_own_quarter_short():
    """2026-Q3 covers July and August only — September opens the monthly era."""
    assert season.season_label(date(2026, 7, 1)) == "2026-Q3"
    assert season.season_label(date(2026, 8, 31)) == "2026-Q3"
    assert season.season_start_date("2026-Q3") == date(2026, 7, 1)
    assert season.season_end_date("2026-Q3") == date(2026, 8, 31)
    assert season.season_period("2026-Q3") == "Jul–Aug"


def test_season_of_puzzle_boundaries():
    assert season.season_of_puzzle(1656) == "2025-Q4"  # 2025-12-31
    assert season.season_of_puzzle(1657) == "2026-Q1"  # 2026-01-01
    assert season.season_of_puzzle(1746) == "2026-Q1"  # 2026-03-31
    assert season.season_of_puzzle(1747) == "2026-Q2"  # 2026-04-01


def test_the_puzzle_that_opens_the_monthly_era():
    """The message posted on Sep 1 carries puzzle 1899 (Aug 31), so the rollover
    lands on 1900 — seen a day later."""
    assert season.puzzle_date(1899) == date(2026, 8, 31)
    assert season.season_of_puzzle(1899) == "2026-Q3"
    assert season.puzzle_date(1900) == date(2026, 9, 1)
    assert season.season_of_puzzle(1900) == "2026-09"
    assert season.season_of_puzzle(1929) == "2026-09"  # 2026-09-30
    assert season.season_of_puzzle(1930) == "2026-10"  # 2026-10-01


def test_first_puzzle_no_round_trips():
    assert season.first_puzzle_no("2026-Q1") == 1657
    assert season.first_puzzle_no("2026-Q2") == 1747
    assert season.first_puzzle_no("2026-Q3") == 1838
    assert season.first_puzzle_no("2026-09") == 1900
    assert season.first_puzzle_no("2026-10") == 1930


def test_label_navigation_within_the_quarterly_era():
    assert season.next_label("2026-Q1") == "2026-Q2"
    assert season.prev_label("2026-Q1") == "2025-Q4"
    assert season.season_start_date("2026-Q2") == date(2026, 4, 1)
    assert season.season_end_date("2026-Q1") == date(2026, 3, 31)


def test_label_navigation_across_the_switch():
    assert season.next_label("2026-Q2") == "2026-Q3"
    assert season.next_label("2026-Q3") == "2026-09"
    assert season.prev_label("2026-09") == "2026-Q3"
    assert season.next_label("2026-09") == "2026-10"
    assert season.prev_label("2026-10") == "2026-09"
    assert season.next_label("2026-12") == "2027-01"
    assert season.prev_label("2027-01") == "2026-12"


def test_monthly_seasons_end_on_the_real_month_end():
    assert season.season_end_date("2026-09") == date(2026, 9, 30)
    assert season.season_end_date("2026-02") == date(2026, 2, 28)
    assert season.season_end_date("2028-02") == date(2028, 2, 29)  # leap year


def test_season_period_and_label_with_period():
    assert season.season_period("2026-Q1") == "Jan–Mar"
    assert season.season_period("2026-Q2") == "Apr–Jun"
    assert season.season_period("2025-Q4") == "Oct–Dec"
    assert season.season_period("2026-09") == "Sep"
    assert season.label_with_period("2026-Q2") == "2026-Q2 (Apr–Jun)"
    assert season.label_with_period("2026-Q3") == "2026-Q3 (Jul–Aug)"
    assert season.label_with_period("2026-09") == "2026-09 (Sep)"


def test_is_monthly_label():
    assert season.is_monthly_label("2026-09")
    assert not season.is_monthly_label("2026-Q3")


def test_unrecognised_labels_raise():
    for bad in ("2026-Q5", "2026-13", "2026-9", "Q3", "", "nonsense"):
        with pytest.raises(ValueError):
            season.season_start_date(bad)


def test_configure_can_move_the_switch():
    season.configure(monthly_start=date(2026, 4, 1))
    assert season.season_label(date(2026, 3, 31)) == "2026-Q1"
    assert season.season_label(date(2026, 4, 1)) == "2026-04"
    assert season.next_label("2026-Q1") == "2026-04"


def test_configure_rejects_a_mid_month_switch():
    with pytest.raises(ValueError, match="1st of a month"):
        season.configure(monthly_start=date(2026, 9, 15))
    assert season.MONTHLY_START == date(2026, 9, 1)  # unchanged


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
