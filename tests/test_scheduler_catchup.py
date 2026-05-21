"""Catch-up scheduler: when several puzzles are missing at once, process them
all but post a leaderboard only for the most recent one."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo import scheduler
from wordle_elo.models import Base, ProcessedPuzzle, Submission


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@dataclass
class _FakeChannel:
    msgs: list
    name: str = "wordle"

    def history(self, limit=None):
        async def _gen():
            for m in self.msgs[:limit] if limit else self.msgs:
                yield m
        return _gen()


@dataclass
class _FakeReply:
    id: int = 999


@dataclass
class _FakeMessage:
    id: int
    content: str
    created_at: datetime
    author_id: int
    posted: bool = False

    @property
    def author(self):
        return type("A", (), {"id": self.author_id})()

    async def reply(self, embeds=None, embed=None, mention_author=False):
        self.posted = True
        return _FakeReply(id=self.id + 10000)


@dataclass
class _Cfg:
    wordle_channel_id: int = 1
    wordle_app_id: int = 42
    discord_guild_id: int = 7


@dataclass
class _FakeBot:
    sessionmaker: object
    cfg: _Cfg = field(default_factory=_Cfg)
    _channel: object = None

    def get_channel(self, _cid):
        return self._channel

    def get_guild(self, _gid):
        return None

    def get_user(self, _uid):
        return None

    async def fetch_user(self, _uid):
        return None


def _msg(puzzle_no: int, app_id: int = 42) -> _FakeMessage:
    # Puzzle number is parsed from "Wordle No. N" in content.
    return _FakeMessage(
        id=puzzle_no,
        content=f"Wordle No. {puzzle_no}\nHere are yesterday's results:\n3/6: <@1>\n5/6: <@2>\n",
        created_at=datetime(2026, 5, 20, 0, 5, tzinfo=timezone.utc),
        author_id=app_id,
    )


async def test_catchup_posts_only_newest_when_multiple_missing(sessionmaker):
    # History returns newest-first, like Discord.
    msgs = [_msg(p) for p in (1795, 1794, 1793, 1792, 1791)]
    bot = _FakeBot(sessionmaker=sessionmaker)
    bot._channel = _FakeChannel(msgs=msgs)

    await scheduler.catch_up(bot)

    posted = {m.id for m in msgs if m.posted}
    assert posted == {1795}  # only the newest puzzle posted a leaderboard

    # All five were still processed (recorded in processed_puzzles)
    async with sessionmaker() as session:
        pps = (await session.execute(select(ProcessedPuzzle))).scalars().all()
        subs = (await session.execute(select(Submission))).scalars().all()
    assert {pp.puzzle_no for pp in pps} == {1791, 1792, 1793, 1794, 1795}
    assert len(subs) == 10  # 2 submitters × 5 puzzles


async def test_catchup_single_missing_posts_it(sessionmaker):
    msgs = [_msg(1795)]
    bot = _FakeBot(sessionmaker=sessionmaker)
    bot._channel = _FakeChannel(msgs=msgs)

    await scheduler.catch_up(bot)
    assert msgs[0].posted is True


async def test_catchup_skips_already_processed(sessionmaker):
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        session.add(ProcessedPuzzle(puzzle_no=1795, source_message_id=1, processed_at=now))
        await session.commit()

    msgs = [_msg(1795)]
    bot = _FakeBot(sessionmaker=sessionmaker)
    bot._channel = _FakeChannel(msgs=msgs)

    await scheduler.catch_up(bot)
    assert msgs[0].posted is False  # already processed → nothing posted
