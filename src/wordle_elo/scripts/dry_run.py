"""Preview what backfill would produce — DB-untouched, channel-untouched.

Fetches Wordle APP messages from the channel, runs them through the same parser
and ELO engine in memory, prints a leaderboard plus a summary so you can sanity-
check the algorithm before committing.

Run with:
    docker compose run --rm bot python -m wordle_elo.scripts.dry_run
        [--channel-id <id>] [--since-puzzle N] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import discord

from ..config import load_config
from ..dryrun import simulate
from ..leaderboard import format_leaderboard_console
from ..parser import parse_message

log = logging.getLogger(__name__)


class DryRunClient(discord.Client):
    def __init__(self, cfg, channel_id: int, since_puzzle: int | None, limit: int | None):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.cfg = cfg
        self.channel_id = channel_id
        self.since_puzzle = since_puzzle
        self.limit = limit

    async def on_ready(self):
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            print(f"# DRY-RUN from #{channel.name} — DB and channel untouched\n", flush=True)

            parsed_msgs = []
            user_ids: set[int] = set()
            scan_failures = 0
            scanned = 0

            async for msg in channel.history(limit=self.limit, oldest_first=True):
                scanned += 1
                if msg.author.id != self.cfg.wordle_app_id:
                    continue
                parsed = parse_message(msg)
                if parsed is None:
                    scan_failures += 1
                    continue
                if self.since_puzzle is not None and parsed.puzzle_no < self.since_puzzle:
                    continue
                parsed_msgs.append(parsed)
                for s in parsed.submissions:
                    user_ids.add(s.user_id)

            print(
                f"# Scanned {scanned} messages → "
                f"{len(parsed_msgs)} Wordle results, {scan_failures} parse failures",
                flush=True,
            )

            display_names: dict[int, str] = {}
            for uid in user_ids:
                user = self.get_user(uid)
                if user is None:
                    try:
                        user = await self.fetch_user(uid)
                    except Exception:
                        user = None
                display_names[uid] = user.display_name if user else f"user_{uid}"

            report = simulate(parsed_msgs, display_names)

            print(
                f"\n# Replayed {report.puzzles_processed} puzzles, "
                f"{len(report.players)} unique players\n"
            )
            rows = report.leaderboard_rows(placement_games=self.cfg.placement_games)
            print(format_leaderboard_console(rows))

            if report.biggest_swings:
                print("\n# Biggest single-day ELO swings:")
                for puz, uid, delta, elo_after in report.biggest_swings:
                    sign = "+" if delta > 0 else ""
                    nick = display_names.get(uid, f"user_{uid}")
                    print(f"  Wordle {puz:>5}  {nick:<20} {sign}{delta:>+4}  → {elo_after}")
            print()
        finally:
            await self.close()


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument("--channel-id", type=int)
    p.add_argument("--since-puzzle", type=int, default=None)
    p.add_argument("--limit", type=int, default=None,
                   help="Max messages to scan (default: all channel history)")
    args = p.parse_args()

    cfg = load_config()
    channel_id = args.channel_id or cfg.wordle_channel_id
    client = DryRunClient(cfg, channel_id, args.since_puzzle, args.limit)
    asyncio.run(client.start(cfg.discord_bot_token))


if __name__ == "__main__":
    main()
