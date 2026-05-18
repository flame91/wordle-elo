"""Glicko-2 (Glickman 2013) adapted for Wordle group play.

Standard Glicko-2 is pairwise (1v1). For Wordle we treat each day's puzzle as
a mini round-robin: every submitter plays every other submitter once, with
a per-pair score driven by guess counts:

- my guesses < their guesses → I win    (s = 1.0)
- my guesses > their guesses → I lose   (s = 0.0)
- same guesses (including X/6 vs X/6)   → draw (s = 0.5)
- X/6 (failure) loses to any solve

Each puzzle is one rating period. After all opponents' contributions are
collected, the player's (rating, RD, volatility) is updated per the standard
Glicko-2 equations.

Default constants follow Glickman's original paper:
    initial rating  = 1500
    initial RD      = 350
    initial sigma   = 0.06
    system tau      = 0.5

For a small friend-group the table sits around 1500 ± 200 after ~100 puzzles.
This is intentionally on a different scale than the absolute-ELO column so
users can see at a glance which algorithm produced a given number.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

GLICKO_INITIAL_RATING = 1000.0
GLICKO_INITIAL_RD = 350.0
GLICKO_INITIAL_SIGMA = 0.06
GLICKO_TAU = 0.5
GLICKO_SCALE = 173.7178  # converts between the user-visible scale and Glicko-2's mu/phi
GLICKO_FLOOR_RD = 30.0   # don't let RD shrink below this — fixes "too confident" trap


@dataclass(frozen=True)
class GlickoRating:
    rating: float = GLICKO_INITIAL_RATING
    rd: float = GLICKO_INITIAL_RD
    sigma: float = GLICKO_INITIAL_SIGMA


def score_pairwise(my_guesses: int, opp_guesses: int) -> float:
    """Wordle pairwise score: fewer guesses wins. X/6 (=7) loses to any solve.
    Same guess count (including X vs X) is a draw."""
    if my_guesses < opp_guesses:
        return 1.0
    if my_guesses > opp_guesses:
        return 0.0
    return 0.5


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _update_volatility(
    sigma: float,
    phi: float,
    v: float,
    delta: float,
    tau: float = GLICKO_TAU,
    eps: float = 1e-6,
) -> float:
    """Glickman 2013 Step 5 — Illinois (regula falsi) on f(x)."""
    a = math.log(sigma * sigma)

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta * delta - phi * phi - v - ex)
        den = 2.0 * (phi * phi + v + ex) ** 2
        return num / den - (x - a) / (tau * tau)

    A = a
    if delta * delta > phi * phi + v:
        B = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * tau) < 0 and k < 100:
            k += 1
        B = a - k * tau

    fA = f(A)
    fB = f(B)

    for _ in range(100):
        if abs(B - A) <= eps:
            break
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)
        if fC * fB <= 0:
            A, fA = B, fB
        else:
            fA /= 2.0
        B, fB = C, fC

    return math.exp(A / 2.0)


def update_one(
    player: GlickoRating,
    opponents: Sequence[tuple[GlickoRating, float]],
    tau: float = GLICKO_TAU,
) -> GlickoRating:
    """One Glicko-2 rating-period update.

    `opponents` is a list of (opponent_rating, my_score) where score is in
    {0.0, 0.5, 1.0}. Empty `opponents` is allowed (solo day) — only RD inflates
    via the volatility step, rating is unchanged.
    """
    if not opponents:
        phi = player.rd / GLICKO_SCALE
        new_phi = math.sqrt(phi * phi + player.sigma * player.sigma)
        new_rd = min(new_phi * GLICKO_SCALE, GLICKO_INITIAL_RD)
        return GlickoRating(rating=player.rating, rd=new_rd, sigma=player.sigma)

    mu = (player.rating - GLICKO_INITIAL_RATING) / GLICKO_SCALE
    phi = player.rd / GLICKO_SCALE

    opp_terms = []
    for opp, s in opponents:
        mu_j = (opp.rating - GLICKO_INITIAL_RATING) / GLICKO_SCALE
        phi_j = opp.rd / GLICKO_SCALE
        g_j = _g(phi_j)
        E_j = 1.0 / (1.0 + math.exp(-g_j * (mu - mu_j)))
        opp_terms.append((g_j, E_j, s))

    v_inv = sum(g * g * E * (1.0 - E) for g, E, _ in opp_terms)
    if v_inv <= 0:
        # All opponents are dominantly stronger or weaker — no information
        return player
    v = 1.0 / v_inv

    score_diff = sum(g * (s - E) for g, E, s in opp_terms)
    delta = v * score_diff

    new_sigma = _update_volatility(player.sigma, phi, v, delta, tau=tau)
    phi_star = math.sqrt(phi * phi + new_sigma * new_sigma)
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    new_mu = mu + new_phi * new_phi * score_diff

    new_rating = GLICKO_INITIAL_RATING + GLICKO_SCALE * new_mu
    new_rd = max(GLICKO_FLOOR_RD, GLICKO_SCALE * new_phi)
    return GlickoRating(rating=new_rating, rd=new_rd, sigma=new_sigma)


def apply_puzzle(
    ratings: Mapping[int, GlickoRating],
    submissions: Sequence[tuple[int, int]],
    tau: float = GLICKO_TAU,
) -> dict[int, GlickoRating]:
    """Apply one puzzle (one rating period) to the rating map.

    `submissions` is [(user_id, guesses), ...] — guesses 1..6 solve, 7 = X/6.
    Returns updated ratings for every submitter; non-submitters are unchanged
    in this period (caller can choose to inflate their RD separately if they
    want strict period semantics — we skip that for Wordle since most members
    play every day).
    """
    if not submissions:
        return {}

    out: dict[int, GlickoRating] = {}
    for uid, g in submissions:
        player = ratings.get(uid, GlickoRating())
        opponents = []
        for opp_uid, opp_g in submissions:
            if opp_uid == uid:
                continue
            opp = ratings.get(opp_uid, GlickoRating())
            opponents.append((opp, score_pairwise(g, opp_g)))
        out[uid] = update_one(player, opponents, tau=tau)
    return out
