"""Scan channel history and refresh the nicknames table from msg.author.

Each Discord message carries author info — for current guild members that's a
Member with the live server nickname, for ex-members it's a User. Walking
recent channel history therefore gives us an authoritative snapshot of every
participant's channel-visible name without needing privileged intents.

Run with:
    docker compose run --rm bot python -m wordle_elo.scripts.refresh_nicknames
        [--channel-id <id>] [--limit N]

Idempotent — re-running just refreshes any names that have drifted since the
last pass.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import discord

from ..config import bootstrap
from ..db import init_db, make_engine, make_sessionmaker
from ..nicknames import refresh_from_channel_history

log = logging.getLogger(__name__)


class RefreshClient(discord.Client):
    def __init__(self, cfg, channel_id: int, limit: int | None):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.cfg = cfg
        self.channel_id = channel_id
        self.limit = limit
        self.engine = make_engine(cfg.db_path)
        self.sessionmaker = make_sessionmaker(self.engine)

    async def on_ready(self):
        try:
            await init_db(self.engine)
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            print(f"# Scanning #{channel.name} for author display names", flush=True)

            result = await refresh_from_channel_history(
                self, self.sessionmaker, self.channel_id, self.limit
            )

            print(
                f"# Scanned {result.scanned} messages, "
                f"inserted={result.inserted} updated={result.updated} "
                f"unchanged={result.unchanged}",
                flush=True,
            )
        finally:
            await self.close()


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument("--channel-id", type=int)
    p.add_argument("--limit", type=int, default=None,
                   help="Max messages to scan (default: all channel history)")
    args = p.parse_args()

    cfg = bootstrap()
    channel_id = args.channel_id or cfg.wordle_channel_id
    client = RefreshClient(cfg, channel_id, args.limit)
    asyncio.run(client.start(cfg.discord_bot_token))


if __name__ == "__main__":
    main()
