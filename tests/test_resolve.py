"""Tests for plain-text @name -> user_id resolution.

Guild matching uses fake Member objects; nickname-history matching uses a real
in-memory SQLite session so the case-insensitive query is exercised for real.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from wordle_elo.models import Base, Nickname
from wordle_elo.parser import ParsedMessage, ParsedSubmission, UnresolvedSubmission
from wordle_elo.resolve import resolve_message, resolve_name


def _member(uid, *, display_name=None, global_name=None, name=None):
    return SimpleNamespace(
        id=uid, display_name=display_name, global_name=global_name, name=name
    )


def _guild(*members):
    return SimpleNamespace(members=list(members))


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_resolve_unique_guild_member_case_insensitive():
    guild = _guild(_member(295, display_name="flame91"))
    outcome = await resolve_name("FLAME91", guild, None)
    assert outcome.resolved
    assert outcome.user_id == 295
    assert outcome.source == "guild"


async def test_resolve_matches_global_name_and_username():
    guild = _guild(_member(1, global_name="Racing Andy", name="racingandy"))
    outcome = await resolve_name("racingandy", guild, None)
    assert outcome.user_id == 1


async def test_resolve_ambiguous_guild_match_is_skipped():
    guild = _guild(
        _member(1, display_name="leo"),
        _member(2, global_name="Leo"),
    )
    outcome = await resolve_name("leo", guild, None)
    assert not outcome.resolved
    assert outcome.source == "ambiguous"
    assert outcome.candidates == (1, 2)


async def test_resolve_no_match_returns_none_source():
    guild = _guild(_member(1, display_name="someone"))
    outcome = await resolve_name("nobody", guild, None)
    assert not outcome.resolved
    assert outcome.source == "none"


async def test_resolve_falls_back_to_nickname_history(sessionmaker):
    async with sessionmaker() as session:
        session.add(
            Nickname(
                user_id=999,
                display_name="OldHandle",
                source="channel_author_member",
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    async with sessionmaker() as session:
        # Not in the (empty) guild, but present in nickname history.
        outcome = await resolve_name("oldhandle", _guild(), session)
    assert outcome.user_id == 999
    assert outcome.source == "nickname"


async def test_resolve_guild_wins_over_nickname(sessionmaker):
    async with sessionmaker() as session:
        session.add(
            Nickname(
                user_id=111,
                display_name="dup",
                source="member",
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    guild = _guild(_member(222, display_name="dup"))
    async with sessionmaker() as session:
        outcome = await resolve_name("dup", guild, session)
    assert outcome.user_id == 222
    assert outcome.source == "guild"


async def test_resolve_message_merges_and_dedups():
    parsed = ParsedMessage(
        puzzle_no=1818,
        submissions=(ParsedSubmission(111, 3, False),),
        unresolved=(
            UnresolvedSubmission("flame91", 5, False),
            UnresolvedSubmission("ghost", 4, False),
        ),
    )
    guild = _guild(
        _member(295, display_name="flame91"),
        _member(111, display_name="alreadymentioned"),
    )
    submissions, skipped = await resolve_message(parsed, guild, None)
    ids = {s.user_id for s in submissions}
    assert ids == {111, 295}
    new = next(s for s in submissions if s.user_id == 295)
    assert new.guesses == 5
    assert [o.name for o in skipped] == ["ghost"]


async def test_resolve_message_skips_name_that_is_already_a_mention():
    # If a person appears both as a real mention and plain text, don't double-add.
    parsed = ParsedMessage(
        puzzle_no=1,
        submissions=(ParsedSubmission(295, 3, False),),
        unresolved=(UnresolvedSubmission("flame91", 5, False),),
    )
    guild = _guild(_member(295, display_name="flame91"))
    submissions, skipped = await resolve_message(parsed, guild, None)
    assert [s.user_id for s in submissions] == [295]
    assert submissions[0].guesses == 3  # the mention's value, not the plain one
    assert skipped == []
