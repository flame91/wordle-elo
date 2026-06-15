"""Parser for Discord Wordle Activity 'yesterday's results' messages.

Target message shape (sample):

    Your group is on a 151 day streak! 🔥🔥🔥 Here are yesterday's results:
    👑 3/6: <@111> <@222> <@333>
    4/6: <@444>
    5/6: <@555>

The puzzle number ("Wordle No. 1783") usually appears in the embed (image header
text) rather than the message body. This parser inspects content + every text
field across all embeds.

The bot only feeds messages from WORDLE_APP_ID through this parser, so we don't
guard against false matches from human chat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Capture everything after the colon to end of line, then pull out both real
# mentions (<@id>) and plain-text @names. Wordle Activity renders some users as
# plain text instead of a mention, and mixed lines like "JohnDoe <@333>" used to
# fail to match at all under the old mentions-only pattern.
LINE_RE = re.compile(
    r"(?P<guesses>[1-6X])/6(?P<hard>\*?)\s*:\s*(?P<users>.+)",
    re.MULTILINE,
)
USER_RE = re.compile(r"<@!?(\d+)>")
# A plain-text @name is what's left once the <@id> mentions are stripped out.
PLAIN_NAME_RE = re.compile(r"@([^\s<@>]+)")
PUZZLE_RE = re.compile(r"Wordle\s*(?:No\.?|#)\s*([\d,]+)", re.IGNORECASE)

X_FAIL_GUESSES = 7  # internal representation for X/6 (failed)

# Date-based puzzle-number fallback for messages that don't embed the number
# (Wordle Activity's current format). Overridden at startup via `configure()`.
EPOCH_DATE = date(2021, 6, 19)
TZ = ZoneInfo("Asia/Seoul")


def configure(*, epoch_date: date | None = None, tz_name: str | None = None) -> None:
    """Override module-level date-fallback knobs. Called from `config.bootstrap()`."""
    global EPOCH_DATE, TZ
    if epoch_date is not None:
        EPOCH_DATE = epoch_date
    if tz_name is not None:
        TZ = ZoneInfo(tz_name)


def _puzzle_no_from_created_at(created_at: datetime) -> int:
    """Wordle Activity posts ~midnight local time with `yesterday's results`,
    so the puzzle date is (message's local calendar date) - 1 day.
    """
    local_date = created_at.astimezone(TZ).date()
    return (local_date - timedelta(days=1) - EPOCH_DATE).days


@dataclass(frozen=True)
class ParsedSubmission:
    user_id: int
    guesses: int  # 1..6 = solved in N, 7 = failed (X/6)
    hard_mode: bool

    @property
    def won(self) -> bool:
        return self.guesses <= 6


@dataclass(frozen=True)
class UnresolvedSubmission:
    """A result-line entry that gave us a plain-text @name but no snowflake.
    The name still needs to be resolved to a user_id (see `resolve.py`)."""

    name: str
    guesses: int  # 1..6 = solved in N, 7 = failed (X/6)
    hard_mode: bool


@dataclass(frozen=True)
class ParsedMessage:
    puzzle_no: int
    submissions: tuple[ParsedSubmission, ...]
    unresolved: tuple[UnresolvedSubmission, ...] = ()


def _extract_puzzle_no(*texts: str) -> int | None:
    for t in texts:
        if not t:
            continue
        m = PUZZLE_RE.search(t)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def _parse_lines(
    content: str,
) -> tuple[list[ParsedSubmission], list[UnresolvedSubmission]]:
    subs: list[ParsedSubmission] = []
    unresolved: list[UnresolvedSubmission] = []
    seen: set[int] = set()
    seen_names: set[str] = set()
    for m in LINE_RE.finditer(content):
        token = m.group("guesses")
        guesses = X_FAIL_GUESSES if token == "X" else int(token)
        hard = bool(m.group("hard"))
        users = m.group("users")
        for uid_str in USER_RE.findall(users):
            uid = int(uid_str)
            if uid in seen:
                continue
            seen.add(uid)
            subs.append(ParsedSubmission(uid, guesses, hard))
        # Whatever isn't a real mention may still be a plain-text @name.
        residual = USER_RE.sub(" ", users)
        for name in PLAIN_NAME_RE.findall(residual):
            key = name.casefold()
            if key in seen_names:
                continue
            seen_names.add(key)
            unresolved.append(UnresolvedSubmission(name, guesses, hard))
    return subs, unresolved


def parse_text(
    content: str,
    embed_texts: list[str] | None = None,
    fallback_puzzle_no: int | None = None,
) -> ParsedMessage | None:
    """Pure parsing entrypoint — kept free of discord.py dependencies for unit tests."""
    subs, unresolved = _parse_lines(content or "")
    if not subs and not unresolved:
        return None
    puzzle_no = _extract_puzzle_no(content or "", *(embed_texts or []))
    if puzzle_no is None:
        puzzle_no = fallback_puzzle_no
    if puzzle_no is None:
        return None
    return ParsedMessage(puzzle_no, tuple(subs), tuple(unresolved))


def collect_embed_texts(message) -> list[str]:
    """Pull every candidate text field out of a discord.py Message's embeds."""
    out: list[str] = []
    for emb in getattr(message, "embeds", []) or []:
        for attr in ("title", "description"):
            v = getattr(emb, attr, None)
            if v:
                out.append(v)
        author = getattr(emb, "author", None)
        if author and getattr(author, "name", None):
            out.append(author.name)
        footer = getattr(emb, "footer", None)
        if footer and getattr(footer, "text", None):
            out.append(footer.text)
        for f in getattr(emb, "fields", []) or []:
            if getattr(f, "name", None):
                out.append(f.name)
            if getattr(f, "value", None):
                out.append(f.value)
        for img_attr in ("image", "thumbnail"):
            img = getattr(emb, img_attr, None)
            if img and getattr(img, "url", None):
                out.append(img.url)
    return out


def parse_message(message) -> ParsedMessage | None:
    fallback = None
    created_at = getattr(message, "created_at", None)
    if created_at is not None:
        fallback = _puzzle_no_from_created_at(created_at)
    return parse_text(
        message.content or "",
        collect_embed_texts(message),
        fallback_puzzle_no=fallback,
    )
