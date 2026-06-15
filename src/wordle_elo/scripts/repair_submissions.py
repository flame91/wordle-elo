"""Backfill submission rows that were dropped because Wordle Activity rendered a
user as plain text (@name) instead of a real mention (<@id>).

Unlike `backfill`, this does NOT skip already-processed puzzles and does NOT
recompute ELO. It only *inserts missing submission rows* into the immutable
`submissions` log (idempotent on the (puzzle_no, user_id) unique key), resolving
plain-text names via the guild member cache / nickname history. Run the
season-aware `recompute_elo` afterwards to rebuild ELO + season archives from the
now-complete log.

Defaults to a preview; pass --apply to actually write.

Run with:
    docker compose run --rm bot python -m wordle_elo.scripts.repair_submissions \
        [--channel-id <id>] [--apply]
    docker compose run --rm bot python -m wordle_elo.scripts.recompute_elo   # then this
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import discord
from sqlalchemy import select

from ..config import bootstrap
from ..db import init_db, make_engine, make_sessionmaker
from ..elo import INITIAL as ELO_INITIAL
from ..models import Player, Submission
from ..parser import parse_message
from ..resolve import resolve_message

log = logging.getLogger(__name__)


class RepairClient(discord.Client):
    def __init__(self, cfg, channel_id: int, apply: bool):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # preload guild members for plain-text name resolution
        super().__init__(intents=intents)
        self.cfg = cfg
        self.channel_id = channel_id
        self.apply = apply
        self.engine = make_engine(cfg.db_path)
        self.sessionmaker = make_sessionmaker(self.engine)

    async def on_ready(self):
        try:
            await init_db(self.engine)
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(
                self.channel_id
            )
            guild = self.get_guild(self.cfg.discord_guild_id)
            mode = "APPLY" if self.apply else "PREVIEW"
            print(
                f"# Repair submissions from #{channel.name} [{mode}] — "
                f"guild={getattr(guild, 'name', None)} "
                f"({len(guild.members) if guild else 0} members cached)",
                flush=True,
            )

            # Existing (puzzle_no, user_id) pairs and known players, loaded once.
            async with self.sessionmaker() as session:
                existing_pairs = {
                    (p, u)
                    for (p, u) in await session.execute(
                        select(Submission.puzzle_no, Submission.user_id)
                    )
                }
                known_players = {
                    r for (r,) in await session.execute(select(Player.user_id))
                }

            to_insert: list[tuple] = []  # (puzzle_no, user_id, guesses, hard, msg)
            new_players: dict[int, object] = {}  # user_id -> earliest msg
            skipped_total = 0

            async for msg in channel.history(limit=None, oldest_first=True):
                if msg.author.id != self.cfg.wordle_app_id:
                    continue
                parsed = parse_message(msg)
                if parsed is None:
                    continue
                async with self.sessionmaker() as session:
                    submissions, skipped = await resolve_message(parsed, guild, session)
                for outcome in skipped:
                    skipped_total += 1
                    print(
                        f"  ! puzzle {parsed.puzzle_no}: unresolved @{outcome.name} "
                        f"({outcome.source}, candidates={outcome.candidates})",
                        flush=True,
                    )
                for s in submissions:
                    if (parsed.puzzle_no, s.user_id) in existing_pairs:
                        continue
                    existing_pairs.add((parsed.puzzle_no, s.user_id))
                    to_insert.append(
                        (parsed.puzzle_no, s.user_id, s.guesses, s.hard_mode, msg)
                    )
                    if s.user_id not in known_players and s.user_id not in new_players:
                        new_players[s.user_id] = msg

            print(
                f"\n# Missing submissions to insert: {len(to_insert)} "
                f"(new players: {len(new_players)}, unresolved skipped: {skipped_total})",
                flush=True,
            )
            for puzzle_no, user_id, guesses, hard, _ in to_insert:
                print(f"  + puzzle {puzzle_no}: user {user_id} guesses={guesses} hard={hard}")

            if not self.apply:
                print("\n# PREVIEW only — re-run with --apply to write, then recompute_elo.")
                return

            async with self.sessionmaker() as session:
                for uid, msg in new_players.items():
                    if await session.get(Player, uid) is None:
                        session.add(
                            Player(user_id=uid, elo=ELO_INITIAL, first_seen_at=msg.created_at)
                        )
                for puzzle_no, user_id, guesses, hard, msg in to_insert:
                    session.add(
                        Submission(
                            puzzle_no=puzzle_no,
                            user_id=user_id,
                            guesses=guesses,
                            hard_mode=int(hard),
                            source_message_id=msg.id,
                            submitted_at=msg.created_at,
                        )
                    )
                await session.commit()

            print(
                f"\n# Done. Inserted {len(to_insert)} submissions, "
                f"created {len(new_players)} players."
            )
            print("# Next: python -m wordle_elo.scripts.recompute_elo")
        finally:
            await self.close()


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument("--channel-id", type=int)
    p.add_argument("--apply", action="store_true", help="Write to the DB (default: preview)")
    args = p.parse_args()

    cfg = bootstrap()
    channel_id = args.channel_id or cfg.wordle_channel_id
    client = RepairClient(cfg, channel_id, args.apply)
    asyncio.run(client.start(cfg.discord_bot_token))


if __name__ == "__main__":
    main()
