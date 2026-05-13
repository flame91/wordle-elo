"""Per-player absolute Elo for Wordle group play.

Each submitter's delta depends on their own result plus how the rest of the
field did that day. Components:

- Base: +K/4 on solve, -K/4 on failure (X/6). K is the per-player K-factor.
- Speed (day-relative): bonus = SPEED_SLOPE * (day_baseline - guesses) on a
  solve, where day_baseline is the mean guesses of today's solvers. So a 3/6
  is rewarded only if today's field averaged worse than 3 — on an easy day
  where everyone got 3/6, no one gets a speed bonus. X/6 is a flat SPEED_FAIL.
- Hard-mode bonus: removed. The Wordle Activity's hard-mode marker is just a
  per-player game-setting toggle, not a difficulty signal. If hard mode makes
  a player slower, the day-relative speed bonus penalizes that automatically.

Above DAMPING_ANCHOR, gains scale by ANCHOR/elo and losses by elo/ANCHOR —
high-rated players grow slowly and lose more on a bad day, so ELO converges
to an equilibrium determined by win rate and solve speed relative to peers.

Final delta is rounded and clamped to [-DELTA_CLAMP, +DELTA_CLAMP].
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
DAMPING_ANCHOR = 800   # ELO above this anchor sees diminishing gains / amplified losses
SPEED_SLOPE = 2.5      # speed_bonus = SPEED_SLOPE * (day_baseline - guesses)
SPEED_FAIL = -3.0      # speed_bonus for X/6 (guesses == 7)
BASELINE_FALLBACK = 4.0  # used when no one solved today (everyone X/6)


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


def speed_bonus(guesses: int, day_baseline: float = BASELINE_FALLBACK) -> float:
    """Day-relative speed bonus. Faster than today's solvers earns +, slower −.
    X/6 (guesses == 7) is a flat penalty independent of the day."""
    if guesses == 7:
        return SPEED_FAIL
    return SPEED_SLOPE * (day_baseline - guesses)


def damping_factor(elo: int, raw_delta: float) -> float:
    """Multiplier applied to raw_delta to dampen gains / amplify losses above
    the anchor. Returns 1.0 at or below the anchor."""
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


def day_baseline(subs: Sequence[tuple[int, int, bool]]) -> float:
    """Mean guesses across today's solvers; BASELINE_FALLBACK if no one solved."""
    winning = [g for (_uid, g, _hm) in subs if g <= 6]
    return (sum(winning) / len(winning)) if winning else BASELINE_FALLBACK


@dataclass(frozen=True)
class DailyDelta:
    delta_field: float    # base solve/fail amount (+K/4 or -K/4)
    delta_speed: float
    delta_streak: float   # always 0.0 — kept for EloHistory schema compatibility
    delta_hard: float     # always 0.0 — kept for EloHistory schema compatibility
    delta_total: int


def compute_daily(
    subs: Sequence[tuple[int, int, bool]],
    ratings: Mapping[int, int],
    streaks_after: Mapping[int, int] | None = None,
    games_played_before: Mapping[int, int] | None = None,
    k: int | None = None,
) -> dict[int, DailyDelta]:
    """Compute one day's Elo deltas for all submitters.

    Args:
        subs: [(user_id, guesses, hard_mode), ...] for all submitters today
        ratings: {user_id: elo_before_today}. Drives the diminishing-returns
            damping above DAMPING_ANCHOR.
        streaks_after: unused by the scoring formula (kept for caller
            compatibility — win rate already encodes streakiness).
        games_played_before: {user_id: games_played_before_today}. Drives the
            per-player K (K_NEW for first NEW_PLAYER_GAMES, K thereafter).
        k: optional override; if set, used as a single K for all players
            (handy for tests).

    Returns:
        {user_id: DailyDelta} for every submitter. Raw components are stored
        pre-damping; delta_total is the final post-damping, post-clamp value.
    """
    _ = streaks_after  # reserved; no longer affects the formula
    gp_before = games_played_before or {}
    baseline = day_baseline(subs)

    out: dict[int, DailyDelta] = {}
    for uid_i, g_i, _hard_i in subs:
        k_i = k if k is not None else k_factor(gp_before.get(uid_i, NEW_PLAYER_GAMES))
        won = g_i <= 6
        d_base = (k_i / 4.0) if won else -(k_i / 4.0)
        d_speed = speed_bonus(g_i, baseline)
        raw = d_base + d_speed
        scaled = raw * damping_factor(ratings[uid_i], raw)
        d_total = max(-DELTA_CLAMP, min(DELTA_CLAMP, round(scaled)))
        out[uid_i] = DailyDelta(d_base, d_speed, 0.0, 0.0, d_total)
    return out
