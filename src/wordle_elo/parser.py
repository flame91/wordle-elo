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

LINE_RE = re.compile(
    r"(?P<guesses>[1-6X])/6(?P<hard>\*?)\s*:\s*"
    r"(?P<users>(?:<@!?\d+>\s*)+)"
)
USER_RE = re.compile(r"<@!?(\d+)>")
PUZZLE_RE = re.compile(r"Wordle\s*(?:No\.?|#)\s*([\d,]+)", re.IGNORECASE)

X_FAIL_GUESSES = 7  # internal representation for X/6 (failed)


@dataclass(frozen=True)
class ParsedSubmission:
    user_id: int
    guesses: int  # 1..6 = solved in N, 7 = failed (X/6)
    hard_mode: bool

    @property
    def won(self) -> bool:
        return self.guesses <= 6


@dataclass(frozen=True)
class ParsedMessage:
    puzzle_no: int
    submissions: tuple[ParsedSubmission, ...]


def _extract_puzzle_no(*texts: str) -> int | None:
    for t in texts:
        if not t:
            continue
        m = PUZZLE_RE.search(t)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def _parse_lines(content: str) -> list[ParsedSubmission]:
    subs: list[ParsedSubmission] = []
    seen: set[int] = set()
    for m in LINE_RE.finditer(content):
        token = m.group("guesses")
        guesses = X_FAIL_GUESSES if token == "X" else int(token)
        hard = bool(m.group("hard"))
        for uid_str in USER_RE.findall(m.group("users")):
            uid = int(uid_str)
            if uid in seen:
                continue
            seen.add(uid)
            subs.append(ParsedSubmission(uid, guesses, hard))
    return subs


def parse_text(content: str, embed_texts: list[str] | None = None) -> ParsedMessage | None:
    """Pure parsing entrypoint — kept free of discord.py dependencies for unit tests."""
    subs = _parse_lines(content or "")
    if not subs:
        return None
    puzzle_no = _extract_puzzle_no(content or "", *(embed_texts or []))
    if puzzle_no is None:
        return None
    return ParsedMessage(puzzle_no, tuple(subs))


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
    return parse_text(message.content or "", collect_embed_texts(message))
