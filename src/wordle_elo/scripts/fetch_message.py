"""Diagnostic helper: fetch specific messages by ID and dump everything that
could explain why a user is or isn't counted into ELO on a given day.

For each message we print:
  - raw content (to see `N/6: <@id>` lines vs plain-text names)
  - the resolved `mentions:` list (discord.py's parsed user mentions)
  - every embed text field (results lines might live in an embed, not content)

Run with:
    docker compose run --rm bot python -m wordle_elo.scripts.fetch_message \
        --channel-id <channel_id> <message_id> [<message_id> ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json

import discord

from ..config import bootstrap
from ..parser import collect_embed_texts, parse_message
from ..resolve import resolve_name


class FetchMessageClient(discord.Client):
    def __init__(self, cfg, channel_id: int, message_ids: list[int], raw: bool):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.cfg = cfg
        self.channel_id = channel_id
        self.message_ids = message_ids
        self.raw = raw

    async def on_ready(self):
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(
                self.channel_id
            )
            guild = self.get_guild(self.cfg.discord_guild_id)
            print(f"# Channel: #{channel.name} (id={channel.id})", flush=True)
            print(
                f"# Guild: {getattr(guild, 'name', None)} "
                f"({len(guild.members) if guild else 0} members cached)",
                flush=True,
            )
            for mid in self.message_ids:
                print("=" * 72)
                try:
                    msg = await channel.fetch_message(mid)
                except Exception as e:
                    print(f"id: {mid}  -> FETCH FAILED: {e!r}")
                    continue
                print(f"id:         {msg.id}")
                print(
                    f"author:     {msg.author} (id={msg.author.id}, bot={msg.author.bot})"
                )
                print(f"created_at: {msg.created_at.isoformat()}")
                print(f"content:    {msg.content!r}")

                mentions = [(u.id, str(u)) for u in msg.mentions]
                print(f"mentions:   {mentions}")

                embed_texts = collect_embed_texts(msg)
                print(f"embed_texts ({len(embed_texts)}):")
                for t in embed_texts:
                    print(f"  - {t!r}")

                if self.raw:
                    print("embeds (raw):")
                    print(
                        json.dumps(
                            [e.to_dict() for e in msg.embeds], indent=2, default=str
                        )
                    )

                parsed = parse_message(msg)
                if parsed is None:
                    print("parsed:     None (no submissions extracted)")
                else:
                    print(f"parsed:     puzzle_no={parsed.puzzle_no}")
                    for s in parsed.submissions:
                        print(
                            f"  mention   uid={s.user_id} guesses={s.guesses} "
                            f"hard={s.hard_mode}"
                        )
                    for u in parsed.unresolved:
                        outcome = await resolve_name(u.name, guild, None)
                        print(
                            f"  plaintext @{u.name} guesses={u.guesses} "
                            f"hard={u.hard_mode} -> {outcome.source} "
                            f"uid={outcome.user_id} candidates={outcome.candidates}"
                        )
        finally:
            await self.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--channel-id", type=int)
    p.add_argument("--raw", action="store_true", help="Dump full embed JSON")
    p.add_argument("message_ids", type=int, nargs="+")
    args = p.parse_args()

    cfg = bootstrap()
    channel_id = args.channel_id or cfg.wordle_channel_id
    client = FetchMessageClient(cfg, channel_id, args.message_ids, args.raw)
    asyncio.run(client.start(cfg.discord_bot_token))


if __name__ == "__main__":
    main()
