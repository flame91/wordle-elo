"""Daily catch-up: scan recent channel history for Wordle APP messages we
haven't processed yet. Safety net in case the bot was offline at posting time
or `on_message` was missed.
"""

from __future__ import annotations

import logging

from .models import ProcessedPuzzle
from .parser import parse_message
from .pipeline import process_message

log = logging.getLogger(__name__)
SCAN_LIMIT = 50


async def catch_up(bot) -> None:
    log.info("Catch-up: starting scan")
    channel = bot.get_channel(bot.cfg.wordle_channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(bot.cfg.wordle_channel_id)
        except Exception:
            log.exception("Catch-up: failed to fetch channel")
            return

    processed = 0
    async for msg in channel.history(limit=SCAN_LIMIT):
        if msg.author.id != bot.cfg.wordle_app_id:
            continue
        parsed = parse_message(msg)
        if parsed is None:
            continue
        async with bot.sessionmaker() as session:
            existing = await session.get(ProcessedPuzzle, parsed.puzzle_no)
        if existing is not None:
            continue
        try:
            await process_message(bot, msg)
            processed += 1
        except Exception:
            log.exception("Catch-up: failed on message %s", msg.id)

    log.info("Catch-up: done (processed %d new puzzles)", processed)
