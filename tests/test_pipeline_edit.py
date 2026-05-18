"""End-to-end test for edit-triggered reprocess.

Simulates the real flow: bot processes an initial daily report with a partial
roster, then the Wordle APP edits the message to add late finishers. The
reprocess path should pick up the new submitters and rebuild ELO so the
leaderboard reflects the full field.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo.models import Base, EloHistory, Player, ProcessedPuzzle, Submission
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
    sent_messages: list = None
    last_id: int = 1000

    def __post_init__(self):
        if self.sent_messages is None:
            self.sent_messages = []

    async def fetch_message(self, mid: int):
        for m in self.sent_messages:
            if m.id == mid:
                return m
        raise LookupError(mid)


@dataclass
class _FakeReply:
    id: int
    channel: _FakeChannel
    edited_embed: object = None

    async def edit(self, embed=None):
        self.edited_embed = embed


@dataclass
class _FakeMessage:
    id: int
    content: str
    created_at: datetime
    channel: _FakeChannel
    embeds: list = None

    def __post_init__(self):
        if self.embeds is None:
            self.embeds = []

    async def reply(self, embed=None, mention_author=False):
        self.channel.last_id += 1
        rep = _FakeReply(id=self.channel.last_id, channel=self.channel)
        self.channel.sent_messages.append(rep)
        return rep


@dataclass
class _FakeBot:
    sessionmaker: object
    cfg: object = None

    def get_guild(self, _gid):
        return None

    def get_user(self, _uid):
        return None

    async def fetch_user(self, _uid):
        return None


@pytest.fixture
def initial_message():
    return _FakeMessage(
        id=42,
        content=(
            "Your group is on a 156 day streak!\nHere are yesterday's results:\n"
            "3/6: <@1>\n"
            "5/6: <@2>\n"
        ),
        created_at=datetime(2026, 5, 14, 0, 5, tzinfo=timezone.utc),
        channel=_FakeChannel(),
    )


async def test_edit_adds_missing_players_and_rebuilds(sessionmaker, initial_message):
    bot = _FakeBot(sessionmaker=sessionmaker)
    await process_message(bot, initial_message)

    async with sessionmaker() as session:
        initial_subs = (await session.execute(select(Submission))).scalars().all()
    assert {s.user_id for s in initial_subs} == {1, 2}

    # The Wordle APP edits the same message to add 2 more finishers.
    initial_message.content = (
        "Your group is on a 156 day streak!\nHere are yesterday's results:\n"
        "3/6: <@1>\n"
        "5/6: <@2> <@3>\n"
        "X/6: <@4>\n"
    )
    await process_message(bot, initial_message, force_reprocess=True)

    async with sessionmaker() as session:
        subs = (await session.execute(select(Submission))).scalars().all()
        history = (await session.execute(select(EloHistory))).scalars().all()
        pp_rows = (await session.execute(select(ProcessedPuzzle))).scalars().all()
        players = (await session.execute(select(Player))).scalars().all()

    # All four submitters now present
    assert {s.user_id for s in subs} == {1, 2, 3, 4}
    # EloHistory has one row per submitter for this single puzzle
    assert {h.user_id for h in history} == {1, 2, 3, 4}
    # Still only one ProcessedPuzzle row (same puzzle_no)
    assert len(pp_rows) == 1
    # All four Player rows exist
    assert {p.user_id for p in players} == {1, 2, 3, 4}


async def test_edit_updates_bot_reply_in_place(sessionmaker, initial_message):
    bot = _FakeBot(sessionmaker=sessionmaker)
    await process_message(bot, initial_message)
    first_reply = initial_message.channel.sent_messages[0]

    initial_message.content = (
        "Your group is on a 156 day streak!\nHere are yesterday's results:\n"
        "3/6: <@1>\n"
        "5/6: <@2> <@3>\n"
    )
    await process_message(bot, initial_message, force_reprocess=True)

    # No new reply was posted — the original was edited
    assert len(initial_message.channel.sent_messages) == 1
    assert first_reply.edited_embed is not None
    # And ProcessedPuzzle.leaderboard_message_id still points at it
    async with sessionmaker() as session:
        pp = (await session.execute(select(ProcessedPuzzle))).scalar_one()
    assert pp.leaderboard_message_id == first_reply.id


async def test_edit_with_no_new_players_still_succeeds(sessionmaker, initial_message):
    """Editing an unchanged message (or one with cosmetic-only changes) should
    not crash or duplicate rows."""
    bot = _FakeBot(sessionmaker=sessionmaker)
    await process_message(bot, initial_message)
    await process_message(bot, initial_message, force_reprocess=True)

    async with sessionmaker() as session:
        subs = (await session.execute(select(Submission))).scalars().all()
        pp_rows = (await session.execute(select(ProcessedPuzzle))).scalars().all()
    assert len(subs) == 2  # exactly the original two
    assert len(pp_rows) == 1


async def test_processed_puzzle_blocks_reprocess_when_flag_off(
    sessionmaker, initial_message
):
    """The pre-existing idempotency guard still applies on plain on_message
    re-deliveries — only `force_reprocess=True` may rebuild."""
    bot = _FakeBot(sessionmaker=sessionmaker)
    await process_message(bot, initial_message)

    initial_message.content = (
        "Your group is on a 156 day streak!\nHere are yesterday's results:\n"
        "3/6: <@1>\n"
        "5/6: <@2> <@3>\n"
        "X/6: <@4>\n"
    )
    result = await process_message(bot, initial_message)  # no force flag
    assert result is None  # skipped

    async with sessionmaker() as session:
        subs = (await session.execute(select(Submission))).scalars().all()
    # Original 2 submissions only; the edit was ignored
    assert {s.user_id for s in subs} == {1, 2}
