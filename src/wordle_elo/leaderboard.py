"""Discord embed formatters + console table renderer (for dry-run)."""

from __future__ import annotations

import unicodedata

import discord

from .tier import strip_provisional
from .version import VersionEntry

CROWN = "\U0001f451"
PAD = "　"  # full-width space, aligns with crown

TIER_EMOJI = {
    "Diamond": "\U0001f48e",       # 💎
    "Gold":    "\U0001f947",       # 🥇
    "Silver":  "\U0001f948",       # 🥈
    "Bronze":  "\U0001f949",       # 🥉
    "Iron":    "♿️",     # ♿️
}


def _tier_emoji(tier: str) -> str:
    return TIER_EMOJI.get(strip_provisional(tier), "")


def _score(guesses: int, hard_mode: bool) -> str:
    s = "X/6" if guesses == 7 else f"{guesses}/6"
    if hard_mode:
        s += "*"
    return s


def _delta(d: int) -> str:
    if d > 0:
        return f"+{d}"
    return str(d)


def _avg_str(avg: float | None) -> str:
    return f"{avg:.2f}" if avg is not None else "—"



def format_daily_embed(puzzle_no: int, entries: list[dict]) -> discord.Embed:
    if not entries:
        return discord.Embed(
            title=f"Wordle No. {puzzle_no}",
            description="No submissions today.",
        )

    best_guesses = entries[0]["guesses"]
    lines: list[str] = []
    for e in entries:
        is_winner = e["guesses"] == best_guesses and e["guesses"] <= 6
        prefix = CROWN if is_winner else PAD
        score = _score(e["guesses"], e["hard_mode"])
        delta_str = _delta(e["delta_total"])
        tier = e.get("tier", "")
        tier_emoji = _tier_emoji(tier)
        lines.append(
            f"{prefix} **{score}** <@{e['user_id']}>  "
            f"`{e['elo_after']:>4}` ({delta_str})  {tier_emoji} {tier}"
        )

    embed = discord.Embed(
        title=f"Wordle No. {puzzle_no}",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    embed.set_footer(text="/leaderboard for full standings · /rank for your details")
    return embed


# Column order: 순위 / 닉네임 / 계급 / ELO / 승/게임(승률) / 최대연승 / 성공시 평균 시도

def format_full_leaderboard(rows: list[dict]) -> discord.Embed:
    if not rows:
        return discord.Embed(title="Wordle ELO Leaderboard", description="No players yet.")
    lines = []
    for i, p in enumerate(rows, start=1):
        win_pct = (p["games_won"] / p["games_played"] * 100) if p["games_played"] else 0
        tier = p.get("tier", "")
        emoji = _tier_emoji(tier)
        avg = _avg_str(p.get("avg_winning_guesses"))
        name = p.get("display_name")
        name_str = f"**{name}**" if name else f"<@{p['user_id']}>"
        lines.append(
            f"`#{i:>2}` {name_str}  {emoji} **{tier}**  "
            f"`{p['elo']:>4}`  "
            f"{p['games_won']}/{p['games_played']} ({win_pct:.0f}%)  "
            f"\U0001f525**{p['best_streak']}**  "
            f"⌀{avg}"
        )
    embed = discord.Embed(
        title="Wordle ELO Leaderboard",
        description="\n".join(lines),
        color=discord.Color.blue(),
    )
    embed.set_footer(
        text="Rank · Name · Tier · ELO · W/G (Win%) · 🔥Best streak · ⌀Avg guesses (wins)"
    )
    return embed



def format_rank_embed(
    player,
    rank: int,
    total: int,
    recent_avg_guesses: float | None = None,
    tier: str = "",
    avg_winning_guesses: float | None = None,
    recent_7d_games: int | None = None,
    recent_7d_wins: int | None = None,
    recent_7d_avg_guesses: float | None = None,
) -> discord.Embed:
    win_pct = (player.games_won / player.games_played * 100) if player.games_played else 0
    lines = [
        f"**Tier**: {_tier_emoji(tier)} {tier}",
        f"**ELO**: {player.elo}",
        f"**Rank**: {rank} / {total}",
        f"**W/G**: {player.games_won}/{player.games_played} ({win_pct:.0f}%)",
        f"**Best streak**: {player.best_streak} (current {player.current_streak})",
    ]
    if avg_winning_guesses is not None:
        lines.append(f"**Avg guesses (wins)**: {avg_winning_guesses:.2f}")
    if recent_avg_guesses is not None:
        lines.append(f"**Avg guesses (last 14 puzzles)**: {recent_avg_guesses:.2f}")

    if recent_7d_games is not None and recent_7d_games > 0:
        win_pct_7d = (recent_7d_wins or 0) / recent_7d_games * 100
        seven_line = (
            f"**Last 7 days**: {recent_7d_wins}/{recent_7d_games} ({win_pct_7d:.0f}%)"
        )
        if recent_7d_avg_guesses is not None:
            seven_line += f"  ·  ⌀{recent_7d_avg_guesses:.2f}"
        lines.append(seven_line)
    elif recent_7d_games == 0:
        lines.append("**Last 7 days**: no plays")

    return discord.Embed(
        title=f"<@{player.user_id}>",
        description="\n".join(lines),
        color=discord.Color.green(),
    )


_VERSION_BODY_CAP = 500


def format_version_embed(entries: list[VersionEntry]) -> discord.Embed:
    if not entries:
        return discord.Embed(
            title="Version history",
            description="No CHANGELOG entries found.",
            color=discord.Color.dark_teal(),
        )
    blocks: list[str] = []
    for i, e in enumerate(entries):
        header = f"**[{e.version}]**"
        if e.date:
            header += f" — {e.date}"
        if i == 0:
            header = f"▶ {header}  *(current)*"
        body = e.body
        if len(body) > _VERSION_BODY_CAP:
            body = body[:_VERSION_BODY_CAP].rstrip() + "…"
        blocks.append(f"{header}\n{body}" if body else header)
    return discord.Embed(
        title="Version history",
        description="\n\n".join(blocks),
        color=discord.Color.dark_teal(),
    )


def format_help_embed(
    commands_info: list[tuple[str, str, list[tuple[str, str]]]],
) -> discord.Embed:
    if not commands_info:
        return discord.Embed(
            title="Commands",
            description="No commands registered.",
            color=discord.Color.blurple(),
        )
    lines: list[str] = []
    for name, desc, params in commands_info:
        lines.append(f"`/{name}` — {desc}" if desc else f"`/{name}`")
        for pname, pdesc in params:
            lines.append(f"　• `{pname}` — {pdesc}" if pdesc else f"　• `{pname}`")
    return discord.Embed(
        title="Commands",
        description="\n".join(lines),
        color=discord.Color.blurple(),
    )


def format_history_embed(user_id: int, rows: list) -> discord.Embed:
    lines = []
    for r in rows:
        lines.append(f"Wordle {r.puzzle_no}: **{_score(r.guesses, bool(r.hard_mode))}**")
    return discord.Embed(
        title=f"<@{user_id}> recent results (last {len(rows)})",
        description="\n".join(lines) if lines else "No results.",
        color=discord.Color.purple(),
    )



def _visual_width(s: str) -> int:
    """East-Asian aware width: CJK chars count as 2 columns."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _pad_left(s: str, w: int) -> str:
    return s + " " * max(0, w - _visual_width(s))


def _pad_right(s: str, w: int) -> str:
    return " " * max(0, w - _visual_width(s)) + s


def format_leaderboard_console(rows: list[dict]) -> str:
    """Render the same column set as the Discord embed, but as a fixed-width
    table. CJK-width aware so Korean nicknames align correctly.
    Column order matches the user spec:
      순위 / 닉네임 / 계급 / ELO / 승/게임(승률) / 최대연승 / 성공시 평균 시도
    """
    if not rows:
        return "No players yet."

    headers = ["순위", "닉네임", "계급", "ELO", "승/게임(승률)", "최대연승", "평균시도(승)"]
    aligns = ["right", "left", "left", "right", "left", "right", "right"]

    body: list[list[str]] = []
    for i, p in enumerate(rows, start=1):
        win_pct = (p["games_won"] / p["games_played"] * 100) if p["games_played"] else 0
        nick = p.get("display_name") or f"user_{p['user_id']}"
        body.append(
            [
                str(i),
                nick,
                p.get("tier", ""),
                str(p["elo"]),
                f"{p['games_won']}/{p['games_played']} ({win_pct:.1f}%)",
                str(p["best_streak"]),
                _avg_str(p.get("avg_winning_guesses")),
            ]
        )

    widths = []
    for col in range(len(headers)):
        widths.append(max(_visual_width(headers[col]),
                          max(_visual_width(r[col]) for r in body)))

    sep = "  "
    def render(row: list[str]) -> str:
        cells = []
        for cell, w, align in zip(row, widths, aligns):
            cells.append(_pad_right(cell, w) if align == "right" else _pad_left(cell, w))
        return sep.join(cells)

    rule = "─" * (sum(widths) + len(sep) * (len(headers) - 1))
    out = [render(headers), rule]
    out.extend(render(r) for r in body)
    return "\n".join(out)
