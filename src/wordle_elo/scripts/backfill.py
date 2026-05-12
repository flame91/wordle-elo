"""Process the entire channel history through the same pipeline used at runtime.

- Idempotent: skips puzzles already in `processed_puzzles`.
- Silent: doesn't post leaderboards (would otherwise spam the channel).
- Failed parses: dumped to {LOG_DIR}/backfill_failures.jsonl for inspection.
- Re-runnable safely after fixing the parser.

Run with:
    docker compose run --rm bot python -m wordle_elo.scripts.backfill
        [--channel-id <id>] [--since-puzzle N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

import discord

from ..config import bootstrap
from ..db import init_db, make_engine, make_sessionmaker
from ..models import ProcessedPuzzle
from ..parser import parse_message
from ..pipeline import process_message

log = logging.getLogger(__name__)


class BackfillClient(discord.Client):
    def __init__(self, cfg, channel_id: int, since_puzzle: int | None):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # preload guild members so nickname resolution doesn't hammer fetch_user
        super().__init__(intents=intents)
        self.cfg = cfg
        self.channel_id = channel_id
        self.since_puzzle = since_puzzle
        self.engine = make_engine(cfg.db_path)
        self.sessionmaker = make_sessionmaker(self.engine)
        self.failures_path = cfg.log_dir / "backfill_failures.jsonl"
        self.failures_path.parent.mkdir(parents=True, exist_ok=True)

    async def on_ready(self):
        try:
            await init_db(self.engine)
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            print(f"# Backfilling from #{channel.name}", flush=True)

            collected: list = []
            scan_failures = 0
            async for msg in channel.history(limit=None, oldest_first=True):
                if msg.author.id != self.cfg.wordle_app_id:
                    continue
                parsed = parse_message(msg)
                if parsed is None:
                    self._log_failure(msg, "parse_returned_none")
                    scan_failures += 1
                    continue
                if self.since_puzzle is not None and parsed.puzzle_no < self.since_puzzle:
                    continue
                collected.append((msg, parsed))

            collected.sort(key=lambda x: x[1].puzzle_no)
            print(f"# Found {len(collected)} parseable Wordle APP messages "
                  f"(scan failures: {scan_failures})", flush=True)

            processed = skipped = process_failures = 0
            for msg, parsed in collected:
                async with self.sessionmaker() as session:
                    existing = await session.get(ProcessedPuzzle, parsed.puzzle_no)
                if existing is not None:
                    skipped += 1
                    continue
                try:
                    await process_message(self, msg, silent=True)
                    processed += 1
                    if processed % 25 == 0:
                        print(f"  …processed {processed} puzzles", flush=True)
                except Exception as e:
                    log.exception("Failed to process puzzle %s", parsed.puzzle_no)
                    self._log_failure(msg, f"process_error: {e}")
                    process_failures += 1

            print(
                f"\n# Done. processed={processed} skipped={skipped} "
                f"scan_failures={scan_failures} process_failures={process_failures}"
            )
            if scan_failures or process_failures:
                print(f"# See {self.failures_path}")
        finally:
            await self.close()

    def _log_failure(self, msg, reason: str):
        rec = {
            "message_id": msg.id,
            "created_at": msg.created_at.isoformat(),
            "reason": reason,
            "content": msg.content,
            "embeds": [e.to_dict() for e in msg.embeds],
        }
        with open(self.failures_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str, ensure_ascii=False) + "\n")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--channel-id", type=int)
    p.add_argument("--since-puzzle", type=int, default=None,
                   help="Only process puzzles with no >= this value")
    args = p.parse_args()

    cfg = bootstrap()
    channel_id = args.channel_id or cfg.wordle_channel_id
    client = BackfillClient(cfg, channel_id, args.since_puzzle)
    asyncio.run(client.start(cfg.discord_bot_token))


if __name__ == "__main__":
    main()
