# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `/version` slash command — surfaces recent release entries from this file,
  with the head entry highlighted. Accepts `count:N` (1..20, default 5).

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
