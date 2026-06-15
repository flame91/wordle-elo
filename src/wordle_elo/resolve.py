"""Resolve plain-text @names to Discord user_ids.

Wordle Activity sometimes renders a result-line user as a real mention
(`<@123>`) and sometimes as plain text (`@displayname`). Plain-text users carry
no snowflake in the raw message, so they silently fall out of ELO scoring. This
module recovers them by matching the plain name against Discord identity, with a
strict unique-or-skip policy so we never guess or invent a Player.

Match order (each step requires exactly one candidate):
  1. live guild member cache — current nickname / global_name / username
  2. nickname history in the DB — the `nicknames.display_name` column

0 or >1 candidates → skip (reported, never resolved). We never create a new
Player from a plain-text name: there's no stable key, and if that person later
appears as a real mention their ELO would be double-counted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import func, select

from .models import Nickname
from .parser import ParsedSubmission

log = logging.getLogger(__name__)


def _norm(name: str) -> str:
    """Casefold + strip a leading @ and surrounding whitespace for comparison."""
    return name.strip().lstrip("@").strip().casefold()


@dataclass(frozen=True)
class ResolveOutcome:
    name: str
    user_id: int | None
    source: str  # 'guild' | 'nickname' | 'none' | 'ambiguous'
    candidates: tuple[int, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.user_id is not None


def candidates_in_guild(guild, name: str) -> set[int]:
    """All guild member ids whose nickname / global_name / username equals `name`
    (case-insensitive). discord.Member.display_name already prefers the server
    nickname then global_name; we also check the raw username for safety."""
    if guild is None:
        return set()
    target = _norm(name)
    hits: set[int] = set()
    for m in guild.members:
        for cand in (
            getattr(m, "display_name", None),
            getattr(m, "global_name", None),
            getattr(m, "name", None),
        ):
            if cand and cand.casefold() == target:
                hits.add(m.id)
                break
    return hits


async def candidates_in_nicknames(session, name: str) -> set[int]:
    """All user_ids whose stored display_name equals `name` (case-insensitive)."""
    target = _norm(name)
    rows = (
        await session.execute(
            select(Nickname.user_id).where(
                func.lower(Nickname.display_name) == target
            )
        )
    ).scalars().all()
    return set(rows)


async def resolve_name(name: str, guild, session) -> ResolveOutcome:
    """Resolve a single plain-text name. guild and/or session may be None."""
    guild_hits = candidates_in_guild(guild, name)
    if len(guild_hits) == 1:
        return ResolveOutcome(name, next(iter(guild_hits)), "guild")
    if len(guild_hits) > 1:
        return ResolveOutcome(name, None, "ambiguous", tuple(sorted(guild_hits)))

    if session is not None:
        nick_hits = await candidates_in_nicknames(session, name)
        if len(nick_hits) == 1:
            return ResolveOutcome(name, next(iter(nick_hits)), "nickname")
        if len(nick_hits) > 1:
            return ResolveOutcome(name, None, "ambiguous", tuple(sorted(nick_hits)))

    return ResolveOutcome(name, None, "none")


async def resolve_message(parsed, guild, session):
    """Fold a ParsedMessage's plain-text names into its submission list.

    Returns (submissions, skipped):
      submissions  — list[ParsedSubmission] with uniquely-resolved names merged
                     in, deduped against users already present as real mentions.
      skipped      — list[ResolveOutcome] for names we refused to guess (0 or >1
                     candidates); the caller logs these for human review.
    """
    submissions = list(parsed.submissions)
    seen = {s.user_id for s in submissions}
    skipped: list[ResolveOutcome] = []
    for u in parsed.unresolved:
        outcome = await resolve_name(u.name, guild, session)
        if not outcome.resolved:
            skipped.append(outcome)
            continue
        if outcome.user_id in seen:
            # Same person already counted via a real mention this puzzle.
            continue
        seen.add(outcome.user_id)
        submissions.append(ParsedSubmission(outcome.user_id, u.guesses, u.hard_mode))
    return submissions, skipped
