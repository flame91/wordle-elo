# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- ELO scoring switched to a **day-relative** speed bonus. Instead of a fixed
  4-guess baseline, `speed_bonus = SPEED_SLOPE * (day_baseline - guesses)`
  where `day_baseline` is the mean guesses of today's solvers. On an easy day
  where everyone solves in 2, no one earns a speed bonus; on a brutal day
  where most fail, the few solvers are rewarded against the field.
- **Streak bonus removed.** Win rate already encodes streakiness; the
  separate bonus double-counted that signal (consistent with Glicko-2,
  TrueSkill, and modern LoL).
- **Hard-mode bonus removed.** The Wordle Activity `*` marker is a per-player
  game-setting toggle, not a puzzle-difficulty signal — rewarding it with a
  flat constant had no principled basis. The day-relative speed bonus
  naturally accounts for any aggregate effect.
- `DAMPING_ANCHOR` default lowered from 1000 to 800, tightening the ceiling
  on high-win-rate players (e.g. ~95% solver equilibrium drops from ~3400
  to ~2700).
- `/leaderboard` renders stored `Nickname.display_name` instead of relying
  solely on `<@id>` mention resolution, so ex-members and uncached users no
  longer show up as raw IDs. The `<@id>` form is kept as a fallback.
- When `/leaderboard` finds a player without a `Nickname` row, it now auto-
  triggers `refresh_from_channel_history` (the shared core of the
  `refresh_nicknames` script) over the most recent 2000 messages on the
  live bot connection before rendering.

### Added
- `wordle_elo.nicknames` module exposing `refresh_from_channel_history`,
  reused by both the standalone refresh script and the leaderboard cog.
- `/rank` now includes a **Last 7 days** window (W/G, win%, and average
  guesses) alongside the existing all-time and last-14-puzzles stats, so
  short-term form is visible.
- `docs/elo.md` — scoring reference with formulas (base, day-relative
  speed, damping), an equilibrium table by win rate, and a worked example.

## [1.0.0] - 2026-05-13

### Added
- `/version` slash command — surfaces recent release entries from this file,
  with the head entry highlighted. Accepts `count:N` (1..20, default 5).
- `/help` slash command — lists every registered slash command with its
  description and parameters. The list is built from the live command tree,
  so adding, removing, or renaming a command updates `/help` automatically.

### Changed
- Tier system simplified to Diamond / Gold / Silver / Bronze / Iron.
  Diamond covers rank-1 and the top 5%; Iron is reserved for the rank-last
  player(s). Platinum and Challenger are gone.

## [0.3.0] - 2026-05-13

### Changed
- Switched to absolute ELO with diminishing returns at high ratings.
- Translated user-facing leaderboard labels to English.

### Fixed
- Enabled the Members privileged intent so nickname lookups hit the cache.

## [0.2.0] - 2026-05-12

### Added
- Aggressive catch-up scheduler with WAL mode for concurrent reads.
- Date-based puzzle-number fallback when the Wordle APP message omits it.
- Dedicated `nicknames` table split out from `players`.

### Changed
- All ELO knobs (K_FACTOR, INITIAL_ELO, NEW_PLAYER_GAMES, …) are env-configurable.

## [0.1.0] - 2026-05-12

### Added
- Initial Discord Wordle Activity ELO bot: message parser, ELO engine, leaderboard.
- Dry-run preview script and console leaderboard with CJK-aware alignment.
- Tiered K-factor: K=40 for the first 10 games, K=24 thereafter.
- `/rank`, `/leaderboard`, `/history` slash commands.
