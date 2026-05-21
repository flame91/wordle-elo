"""The daily auto-post should attach the full /leaderboard standings (active
players) as a second embed, not just today's submitters."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo.models import Base
from wordle_elo.pipeline import process_message


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@dataclass
class _FakeChannel:
    id: int = 1


@dataclass
class _FakeReply:
    id: int
    embeds: list


@dataclass
class _FakeMessage:
    id: int
    content: str
    created_at: datetime
    channel: _FakeChannel = field(default_factory=_FakeChannel)
    embeds: list = field(default_factory=list)
    captured: list = field(default_factory=list)

    async def reply(self, embeds=None, embed=None, mention_author=False):
        sent = embeds if embeds is not None else [embed]
        self.captured = sent
        return _FakeReply(id=self.id + 1, embeds=sent)


@dataclass
class _Cfg:
    discord_guild_id: int = 7
    wordle_channel_id: int = 1
    wordle_app_id: int = 42


@dataclass
class _FakeBot:
    sessionmaker: object
    cfg: _Cfg = field(default_factory=_Cfg)

    def get_guild(self, _gid):
        return None

    def get_user(self, _uid):
        return None

    async def fetch_user(self, _uid):
        return None


def _daily_msg(puzzle_no: int) -> _FakeMessage:
    return _FakeMessage(
        id=500,
        content=(
            f"Wordle No. {puzzle_no}\nHere are yesterday's results:\n"
            "3/6: <@1>\n5/6: <@2>\nX/6: <@3>\n"
        ),
        created_at=datetime(2026, 5, 20, 0, 5, tzinfo=timezone.utc),
    )


async def test_daily_post_attaches_full_leaderboard_embed(sessionmaker):
    bot = _FakeBot(sessionmaker=sessionmaker)
    msg = _daily_msg(1795)
    await process_message(bot, msg)

    # Two embeds: [0] daily summary, [1] full standings
    assert len(msg.captured) == 2
    daily, board = msg.captured
    assert "Wordle No. 1795" in (daily.title or "")
    assert "Leaderboard" in (board.title or "")
    # The standings embed lists all active players (3 submitters today)
    desc = board.description or ""
    assert desc.count("`#") == 3  # ranks #1..#3 rendered


async def test_silent_processing_posts_nothing(sessionmaker):
    bot = _FakeBot(sessionmaker=sessionmaker)
    msg = _daily_msg(1795)
    await process_message(bot, msg, silent=True)
    assert msg.captured == []
