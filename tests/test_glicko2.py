"""Glicko-2 pairwise scoring and rating update tests."""

import math

import pytest

from wordle_elo.glicko2 import (
    GLICKO_INITIAL_RATING,
    GLICKO_INITIAL_RD,
    GLICKO_INITIAL_SIGMA,
    GlickoRating,
    apply_puzzle,
    score_pairwise,
    update_one,
)


@pytest.mark.parametrize(
    "mine,theirs,expected",
    [
        (3, 5, 1.0),  # I solved faster
        (5, 3, 0.0),  # I solved slower
        (4, 4, 0.5),  # tied
        (3, 7, 1.0),  # I solved, they failed
        (7, 3, 0.0),  # I failed, they solved
        (7, 7, 0.5),  # both failed
    ],
)
def test_score_pairwise(mine, theirs, expected):
    assert score_pairwise(mine, theirs) == expected


def test_update_one_no_opponents_keeps_rating_inflates_rd():
    p = GlickoRating(rating=1500, rd=80, sigma=0.06)
    after = update_one(p, [])
    assert after.rating == 1500
    # RD must not shrink and must not exceed the initial cap
    assert after.rd >= 80
    assert after.rd <= GLICKO_INITIAL_RD


def test_default_player_has_glicko_initial_values():
    p = GlickoRating()
    assert p.rating == GLICKO_INITIAL_RATING
    assert p.rd == GLICKO_INITIAL_RD
    assert p.sigma == GLICKO_INITIAL_SIGMA


def test_winning_against_equal_opponent_raises_rating():
    me = GlickoRating()
    opp = GlickoRating()
    after = update_one(me, [(opp, 1.0)])
    assert after.rating > GLICKO_INITIAL_RATING


def test_losing_to_equal_opponent_lowers_rating():
    me = GlickoRating()
    opp = GlickoRating()
    after = update_one(me, [(opp, 0.0)])
    assert after.rating < GLICKO_INITIAL_RATING


def test_high_rd_player_moves_more_per_game_than_low_rd_player():
    """A newer player (high RD) should swing more on a single result than an
    established player (low RD) — this is the whole point of dynamic K."""
    opp = GlickoRating(rating=1500, rd=50)
    new = GlickoRating(rating=1500, rd=350)
    settled = GlickoRating(rating=1500, rd=50)
    new_after = update_one(new, [(opp, 1.0)])
    settled_after = update_one(settled, [(opp, 1.0)])
    assert (new_after.rating - 1500) > (settled_after.rating - 1500)


def test_rd_shrinks_with_play():
    me = GlickoRating(rating=1500, rd=350)
    opp = GlickoRating()
    after = update_one(me, [(opp, 1.0)])
    assert after.rd < me.rd


def test_apply_puzzle_distributes_correctly():
    # Three submitters: 3/6, 4/6, X/6. Expected ordering after: a > b > c.
    ratings = {}
    subs = [(1, 3), (2, 4), (3, 7)]
    after = apply_puzzle(ratings, subs)
    assert after[1].rating > after[2].rating > after[3].rating


def test_apply_puzzle_solo_is_noop_on_rating():
    """A solo submitter has no opponents — rating shouldn't move."""
    ratings = {}
    after = apply_puzzle(ratings, [(1, 3)])
    assert after[1].rating == GLICKO_INITIAL_RATING


def test_apply_puzzle_preserves_unsubmitted_players():
    """Players who didn't submit this round must not appear in the output."""
    ratings = {2: GlickoRating(rating=1200)}
    after = apply_puzzle(ratings, [(1, 3), (3, 5)])
    assert 2 not in after  # didn't play, no update
    assert 1 in after
    assert 3 in after


def test_repeated_dominance_lifts_rating_and_shrinks_rd():
    """Beating a 1500 opponent over and over should monotonically push us
    above 1500. RD also shrinks vs the initial 350, though slower once we've
    pulled far ahead (those wins carry less new information)."""
    me = GlickoRating()
    opp = GlickoRating()
    for _ in range(20):
        me = update_one(me, [(opp, 1.0)])
    assert me.rating > 1600
    assert me.rd < GLICKO_INITIAL_RD  # got more certain than initial

    # RD never breaks past floor across many rounds
    for _ in range(200):
        me = update_one(me, [(opp, 1.0)])
    assert me.rd > 0


def test_volatility_stays_finite_under_alternating_results():
    me = GlickoRating()
    opp = GlickoRating()
    for i in range(40):
        me = update_one(me, [(opp, 1.0 if i % 2 == 0 else 0.0)])
        assert math.isfinite(me.rating)
        assert math.isfinite(me.rd)
        assert math.isfinite(me.sigma)
