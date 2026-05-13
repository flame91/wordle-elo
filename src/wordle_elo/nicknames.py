"""Nickname maintenance — shared by the refresh_nicknames script and the
runtime leaderboard cog so both call the same code path."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import discord

from .models import Nickname

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefreshResult:
    scanned: int
    inserted: int
    updated: int
    unchanged: int


async def refresh_from_channel_history(
    client: discord.Client,
    sessionmaker,
    channel_id: int,
    limit: int | None = None,
) -> RefreshResult:
    """Walk channel history on the given client connection and upsert each
    author's display name into the nicknames table.

    Caller owns the discord connection — this function neither starts nor
    closes the client. Safe to invoke from a running bot.
    """
    channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)

    latest: dict[int, tuple[str, str]] = {}
    scanned = 0
    async for msg in channel.history(limit=limit):
        scanned += 1
        author = msg.author
        if author.id in latest:
            continue
        source = (
            "channel_author_member"
            if isinstance(author, discord.Member)
            else "channel_author_user"
        )
        latest[author.id] = (author.display_name, source)

    now = datetime.now(timezone.utc)
    inserted = updated = unchanged = 0
    async with sessionmaker() as session:
        for uid, (name, source) in latest.items():
            existing = await session.get(Nickname, uid)
            if existing is None:
                session.add(
                    Nickname(
                        user_id=uid,
                        display_name=name,
                        source=source,
                        updated_at=now,
                    )
                )
                inserted += 1
            elif existing.display_name != name or existing.source != source:
                existing.display_name = name
                existing.source = source
                existing.updated_at = now
                updated += 1
            else:
                unchanged += 1
        await session.commit()

    return RefreshResult(
        scanned=scanned,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
    )
