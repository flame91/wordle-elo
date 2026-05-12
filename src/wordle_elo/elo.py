"""Pairwise averaged field Elo for Wordle group play.

Per the design report:
- Active participants on a given puzzle compete against the field
- For each pair (i, j): S_ij = 1/0.5/0 by guesses, E_ij = standard Elo expected
- Δfield_i = (K / (n-1)) * Σ(S_ij - E_ij) over all j ≠ i
- Plus speed bonus, streak bonus, hard-mode bonus
- Final delta clamped to [-40, +40]
- Players who didn't submit get no change (handled by caller, not here)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

INITIAL = 1000
K = 24
SPEED = {1: 3, 2: 2, 3: 1, 4: 0, 5: -1, 6: -2, 7: -4}  # 7 = X (failed)
DELTA_CLAMP = 40


def expected(r_i: int, r_j: int) -> float:
    return 1.0 / (1.0 + 10 ** ((r_j - r_i) / 400.0))


def actual(g_i: int, g_j: int) -> float:
    if g_i < g_j:
        return 1.0
    if g_i > g_j:
        return 0.0
    return 0.5


def streak_bonus(streak_after_today: int, won: bool) -> int:
    if not won:
        return 0
    if streak_after_today >= 9:
        return 3
    if streak_after_today >= 6:
        return 2
    if streak_after_today >= 3:
        return 1
    return 0


@dataclass(frozen=True)
class DailyDelta:
    delta_field: float
    delta_speed: float
    delta_streak: float
    delta_hard: float
    delta_total: int


def compute_daily(
    subs: Sequence[tuple[int, int, bool]],
    ratings: Mapping[int, int],
    streaks_after: Mapping[int, int],
    k: int = K,
) -> dict[int, DailyDelta]:
    """Compute one day's Elo deltas for all participants.

    Args:
        subs: [(user_id, guesses, hard_mode), ...] for all submitters today
        ratings: {user_id: elo_before_today} for every submitter
        streaks_after: {user_id: current_streak_value_after_today's_result}
        k: K-factor (default 24)

    Returns:
        {user_id: DailyDelta}. Empty dict if fewer than 2 submitters
        (no comparison possible → no rating change).
    """
    n = len(subs)
    if n < 2:
        return {}
    out: dict[int, DailyDelta] = {}
    for uid_i, g_i, hard_i in subs:
        r_i = ratings[uid_i]
        s_sum = e_sum = 0.0
        for uid_j, g_j, _ in subs:
            if uid_j == uid_i:
                continue
            s_sum += actual(g_i, g_j)
            e_sum += expected(r_i, ratings[uid_j])
        d_field = (k / (n - 1)) * (s_sum - e_sum)
        d_speed = float(SPEED[g_i])
        won = g_i <= 6
        d_streak = float(streak_bonus(streaks_after[uid_i], won))
        d_hard = 1.0 if hard_i else 0.0
        raw = d_field + d_speed + d_streak + d_hard
        d_total = max(-DELTA_CLAMP, min(DELTA_CLAMP, round(raw)))
        out[uid_i] = DailyDelta(d_field, d_speed, d_streak, d_hard, d_total)
    return out
