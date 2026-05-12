"""In-memory ELO simulator. Pure logic, zero I/O.

Used by the `scripts/dry_run.py` script to preview what backfill would produce
without touching the database or posting to Discord.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .elo import INITIAL as ELO_INITIAL
from .elo import compute_daily
from .parser import ParsedMessage
from .tier import assign_tier

ELO_FLOOR = 100


@dataclass
class DryPlayerState:
    user_id: int
    display_name: str
    elo: int = ELO_INITIAL
    games_played: int = 0
    games_won: int = 0
    current_streak: int = 0
    best_streak: int = 0
    winning_guess_total: int = 0  # sum of guesses on wins → divide by games_won

    @property
    def win_pct(self) -> float:
        return (self.games_won / self.games_played * 100) if self.games_played else 0.0

    @property
    def avg_winning_guesses(self) -> float | None:
        return (self.winning_guess_total / self.games_won) if self.games_won else None


@dataclass
class DryRunReport:
    players: dict[int, DryPlayerState]
    puzzles_processed: int
    biggest_swings: list[tuple[int, int, int, int]] = field(default_factory=list)
    # (puzzle_no, user_id, delta_total, elo_after) — top swings during simulation

    def leaderboard_rows(self, placement_games: int = 14) -> list[dict]:
        ratings = [p.elo for p in self.players.values()]
        sorted_players = sorted(self.players.values(), key=lambda p: -p.elo)
        out = []
        for p in sorted_players:
            out.append(
                {
                    "user_id": p.user_id,
                    "display_name": p.display_name,
                    "elo": p.elo,
                    "games_played": p.games_played,
                    "games_won": p.games_won,
                    "current_streak": p.current_streak,
                    "best_streak": p.best_streak,
                    "avg_winning_guesses": p.avg_winning_guesses,
                    "tier": assign_tier(p.elo, ratings, p.games_played, placement_games),
                }
            )
        return out


def simulate(
    parsed_messages: Iterable[ParsedMessage],
    display_names: dict[int, str] | None = None,
    *,
    track_swings_top: int = 10,
) -> DryRunReport:
    """Replay parsed messages chronologically against an in-memory ledger."""
    display_names = display_names or {}
    state: dict[int, DryPlayerState] = {}
    swings: list[tuple[int, int, int, int]] = []

    msgs = sorted(parsed_messages, key=lambda m: m.puzzle_no)
    for parsed in msgs:
        for s in parsed.submissions:
            if s.user_id not in state:
                state[s.user_id] = DryPlayerState(
                    user_id=s.user_id,
                    display_name=display_names.get(s.user_id, f"user_{s.user_id}"),
                )

        ratings = {s.user_id: state[s.user_id].elo for s in parsed.submissions}
        streaks_after: dict[int, int] = {}
        for s in parsed.submissions:
            prev = state[s.user_id].current_streak
            streaks_after[s.user_id] = (prev + 1) if s.won else 0

        deltas = compute_daily(
            [(s.user_id, s.guesses, s.hard_mode) for s in parsed.submissions],
            ratings,
            streaks_after,
        )

        for s in parsed.submissions:
            p = state[s.user_id]
            d = deltas.get(s.user_id)
            d_total = d.delta_total if d else 0
            p.elo = max(ELO_FLOOR, p.elo + d_total)
            p.games_played += 1
            if s.won:
                p.games_won += 1
                p.winning_guess_total += s.guesses
            p.current_streak = streaks_after[s.user_id]
            if p.current_streak > p.best_streak:
                p.best_streak = p.current_streak
            if d_total != 0:
                swings.append((parsed.puzzle_no, s.user_id, d_total, p.elo))

    swings.sort(key=lambda t: -abs(t[2]))
    return DryRunReport(
        players=state,
        puzzles_processed=len(msgs),
        biggest_swings=swings[:track_swings_top],
    )
