"""Day 1 helper. Login as the bot, fetch the most recent N messages from the
Wordle channel, and dump everything we'd need to calibrate the parser:
  - author id (to confirm WORDLE_APP_ID)
  - raw content (to see the exact format of `N/6: <@id>` lines)
  - all embed text fields (to find the puzzle number)

Run with: docker compose run --rm bot python -m wordle_elo.scripts.fetch_sample
         [--channel-id <id>] [--limit 10] [--raw]
"""

from __future__ import annotations

import argparse
import asyncio
import json

import discord

from ..config import load_config


class FetchClient(discord.Client):
    def __init__(self, channel_id: int, limit: int, raw: bool):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.limit = limit
        self.raw = raw

    async def on_ready(self):
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            print(f"# Channel: #{channel.name} (id={channel.id})", flush=True)
            count = 0
            async for msg in channel.history(limit=self.limit):
                count += 1
                print("---")
                print(f"id:         {msg.id}")
                print(f"author:     {msg.author} (id={msg.author.id}, bot={msg.author.bot})")
                print(f"created_at: {msg.created_at.isoformat()}")
                print(f"content:    {msg.content!r}")
                if self.raw:
                    embeds = [e.to_dict() for e in msg.embeds]
                    print("embeds:")
                    print(json.dumps(embeds, indent=2, default=str))
                else:
                    for i, e in enumerate(msg.embeds):
                        print(
                            f"embed[{i}]: title={e.title!r} desc={e.description!r}"
                            f" image={getattr(e.image, 'url', None) if e.image else None}"
                        )
            print(f"\n# Total: {count} messages")
        finally:
            await self.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--channel-id", type=int)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--raw", action="store_true", help="Dump full embed JSON")
    args = p.parse_args()

    cfg = load_config()
    channel_id = args.channel_id or cfg.wordle_channel_id
    client = FetchClient(channel_id, args.limit, args.raw)
    asyncio.run(client.start(cfg.discord_bot_token))


if __name__ == "__main__":
    main()
