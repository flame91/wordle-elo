"""Unit tests for the nickname upsert logic in pipeline.

We exercise _resolve_display_name / _upsert_nickname directly with fakes for
bot / session / guild / member / user — no Discord, no real DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from wordle_elo.models import Nickname
from wordle_elo.pipeline import _resolve_display_name, _upsert_nickname


class FakeSession:
    """Captures session.add / session.get without a real DB."""

    def __init__(self, existing: dict[int, Nickname] | None = None):
        self._rows: dict[int, Nickname] = dict(existing or {})
        self.added: list[Nickname] = []

    async def get(self, model, key):
        assert model is Nickname
        return self._rows.get(key)

    def add(self, obj):
        assert isinstance(obj, Nickname)
        self.added.append(obj)
        self._rows[obj.user_id] = obj


def _bot(guild_id=None, members=None, users=None):
    """Build a fake bot whose get_guild / get_user / fetch_user are sync stubs."""
    members = members or {}
    users = users or {}

    if guild_id is not None:
        guild = SimpleNamespace(get_member=lambda uid: members.get(uid))
    else:
        guild = None

    cfg = SimpleNamespace(discord_guild_id=guild_id) if guild_id is not None else None

    async def fetch_user(uid):
        return users.get(uid)

    return SimpleNamespace(
        cfg=cfg,
        get_guild=lambda gid: guild if gid == guild_id else None,
        get_user=lambda uid: users.get(uid),
        fetch_user=fetch_user,
    )


async def test_resolve_prefers_member_over_user():
    bot = _bot(
        guild_id=1,
        members={42: SimpleNamespace(display_name="ServerNick")},
        users={42: SimpleNamespace(display_name="GlobalName")},
    )
    name, source = await _resolve_display_name(bot, 42)
    assert name == "ServerNick"
    assert source == "member"


async def test_resolve_falls_back_to_user_when_not_a_member():
    bot = _bot(
        guild_id=1,
        members={},  # not in guild cache
        users={42: SimpleNamespace(display_name="GlobalName")},
    )
    name, source = await _resolve_display_name(bot, 42)
    assert name == "GlobalName"
    assert source == "user"


async def test_resolve_returns_fallback_when_discord_unreachable():
    bot = _bot(guild_id=1, members={}, users={})  # neither cache nor fetch finds them
    name, source = await _resolve_display_name(bot, 42)
    assert name is None
    assert source == "fallback"


async def test_upsert_inserts_new_row():
    session = FakeSession()
    bot = _bot(guild_id=1, members={42: SimpleNamespace(display_name="ServerNick")})
    now = datetime.now(timezone.utc)
    await _upsert_nickname(session, bot, 42, now)
    assert len(session.added) == 1
    added = session.added[0]
    assert added.user_id == 42
    assert added.display_name == "ServerNick"
    assert added.source == "member"


async def test_upsert_updates_changed_name():
    existing = Nickname(
        user_id=42,
        display_name="OldName",
        source="member",
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    session = FakeSession(existing={42: existing})
    bot = _bot(guild_id=1, members={42: SimpleNamespace(display_name="NewName")})
    now = datetime.now(timezone.utc)
    await _upsert_nickname(session, bot, 42, now)
    assert existing.display_name == "NewName"
    assert existing.updated_at == now
    assert session.added == []  # no new row, in-place update


async def test_upsert_skips_when_unchanged():
    existing = Nickname(
        user_id=42,
        display_name="SameName",
        source="member",
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    session = FakeSession(existing={42: existing})
    bot = _bot(guild_id=1, members={42: SimpleNamespace(display_name="SameName")})
    new_when = datetime.now(timezone.utc)
    await _upsert_nickname(session, bot, 42, new_when)
    assert existing.updated_at == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert session.added == []


async def test_upsert_does_not_overwrite_existing_with_fallback():
    """Discord lookup failed → keep whatever good name we already had."""
    existing = Nickname(
        user_id=42,
        display_name="GoodName",
        source="member",
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    session = FakeSession(existing={42: existing})
    bot = _bot(guild_id=1, members={}, users={})  # fallback path
    await _upsert_nickname(session, bot, 42, datetime.now(timezone.utc))
    assert existing.display_name == "GoodName"
    assert session.added == []


async def test_upsert_skips_when_new_user_unresolvable():
    """First sight + Discord unreachable → no row written (no junk)."""
    session = FakeSession()
    bot = _bot(guild_id=1, members={}, users={})
    await _upsert_nickname(session, bot, 42, datetime.now(timezone.utc))
    assert session.added == []
