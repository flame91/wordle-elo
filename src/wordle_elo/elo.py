"""Per-player absolute Elo for Wordle group play.

Each submitter's delta depends only on their own result — not on what other
players did that day. Components:

- Base: +K/4 on solve, -K/4 on failure (X/6). K is the per-player K-factor.
- Speed: bonus by guesses (1/6 best, 6/6 slow, X/6 worst).
- Streak: bonus when the player's current streak crosses 3/6/9-day thresholds.
- Hard mode: +1 on solve when played in hard mode.

Above DAMPING_ANCHOR (default 1000), gains scale by ANCHOR/elo and losses by
elo/ANCHOR — high-rated players grow slowly and lose more on a bad day, so
ELO converges to an equilibrium determined by win rate instead of drifting up
forever.

Final delta is rounded and clamped to [-DELTA_CLAMP, +DELTA_CLAMP].
Players who didn't submit get no change (handled by caller, not here).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Module-level defaults. Override at startup via `configure()` (called from
# `config.bootstrap()`); all callers reading these constants will see the
# updated values automatically.
INITIAL = 1000
K = 24                 # regular K-factor (FIDE-style "established" rating)
K_NEW = 40             # K for new players in their first NEW_PLAYER_GAMES games
NEW_PLAYER_GAMES = 10  # threshold below which K_NEW applies
DELTA_CLAMP = 40
DAMPING_ANCHOR = 1000  # ELO above this anchor sees diminishing gains / amplified losses
SPEED = {1: 3, 2: 2, 3: 1, 4: 0, 5: -1, 6: -2, 7: -4}  # 7 = X (failed)


def configure(
    *,
    initial: int | None = None,
    k: int | None = None,
    k_new: int | None = None,
    new_player_games: int | None = None,
    delta_clamp: int | None = None,
    damping_anchor: int | None = None,
) -> None:
    """Override module-level ELO knobs from env / config. Idempotent."""
    global INITIAL, K, K_NEW, NEW_PLAYER_GAMES, DELTA_CLAMP, DAMPING_ANCHOR
    if initial is not None:
        INITIAL = initial
    if k is not None:
        K = k
    if k_new is not None:
        K_NEW = k_new
    if new_player_games is not None:
        NEW_PLAYER_GAMES = new_player_games
    if delta_clamp is not None:
        DELTA_CLAMP = delta_clamp
    if damping_anchor is not None:
        DAMPING_ANCHOR = damping_anchor


def damping_factor(elo: int, raw_delta: float) -> float:
    """Multiplier applied to raw_delta to dampen gains / amplify losses above
    the anchor. Returns 1.0 at or below the anchor. Above the anchor:
    - gains shrink by anchor/elo (1500 ⇒ 0.67×, 2000 ⇒ 0.5×)
    - losses grow by elo/anchor (1500 ⇒ 1.5×, 2000 ⇒ 2.0×)
    """
    if elo <= DAMPING_ANCHOR:
        return 1.0
    if raw_delta > 0:
        return DAMPING_ANCHOR / elo
    if raw_delta < 0:
        return elo / DAMPING_ANCHOR
    return 1.0


def k_factor(games_played_before: int) -> int:
    """Per-player K. New players (< NEW_PLAYER_GAMES) move faster so they
    converge to their true rating in ~10 games instead of months.
    """
    return K_NEW if games_played_before < NEW_PLAYER_GAMES else K


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
    delta_field: float   # base solve/fail amount (+K/4 or -K/4)
    delta_speed: float
    delta_streak: float
    delta_hard: float
    delta_total: int


def compute_daily(
    subs: Sequence[tuple[int, int, bool]],
    ratings: Mapping[int, int],
    streaks_after: Mapping[int, int],
    games_played_before: Mapping[int, int] | None = None,
    k: int | None = None,
) -> dict[int, DailyDelta]:
    """Compute one day's Elo deltas for all submitters.

    Args:
        subs: [(user_id, guesses, hard_mode), ...] for all submitters today
        ratings: {user_id: elo_before_today}. Drives the diminishing-returns
            damping above DAMPING_ANCHOR.
        streaks_after: {user_id: current_streak_value_after_today}
        games_played_before: {user_id: games_played_before_today}. Drives the
            per-player K (K_NEW for first NEW_PLAYER_GAMES, K thereafter). If
            omitted, every player is treated as established (K=24).
        k: optional override; if set, used as a single K for all players
            (handy for tests).

    Returns:
        {user_id: DailyDelta} for every submitter. Raw components are stored
        pre-damping; delta_total is the final post-damping, post-clamp value.
    """
    gp_before = games_played_before or {}
    out: dict[int, DailyDelta] = {}
    for uid_i, g_i, hard_i in subs:
        k_i = k if k is not None else k_factor(gp_before.get(uid_i, NEW_PLAYER_GAMES))
        won = g_i <= 6
        d_base = (k_i / 4.0) if won else -(k_i / 4.0)
        d_speed = float(SPEED[g_i])
        d_streak = float(streak_bonus(streaks_after[uid_i], won))
        d_hard = 1.0 if (hard_i and won) else 0.0
        raw = d_base + d_speed + d_streak + d_hard
        scaled = raw * damping_factor(ratings[uid_i], raw)
        d_total = max(-DELTA_CLAMP, min(DELTA_CLAMP, round(scaled)))
        out[uid_i] = DailyDelta(d_base, d_speed, d_streak, d_hard, d_total)
    return out
