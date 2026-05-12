"""Discord embed formatters."""

from __future__ import annotations

import discord

CROWN = "\U0001f451"
PAD = "　"  # full-width space, aligns with crown

TIER_EMOJI = {
    "Challenger": "\U0001f3c6",  # 🏆
    "Diamond": "\U0001f48e",      # 💎
    "Platinum": "\U0001f947",     # 🥇
    "Gold": "\U0001f947",         # 🥇
    "Silver": "\U0001f948",       # 🥈
    "Bronze": "\U0001f949",       # 🥉
    "Provisional": "\U0001f31f",  # 🌟
}


def _score(guesses: int, hard_mode: bool) -> str:
    s = "X/6" if guesses == 7 else f"{guesses}/6"
    if hard_mode:
        s += "*"
    return s


def _delta(d: int) -> str:
    if d > 0:
        return f"+{d}"
    return str(d)


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
        tier_emoji = TIER_EMOJI.get(tier, "")
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


def format_full_leaderboard(rows: list[dict]) -> discord.Embed:
    if not rows:
        return discord.Embed(title="Leaderboard", description="No players yet.")
    lines = []
    for i, p in enumerate(rows, start=1):
        win_pct = (p["games_won"] / p["games_played"] * 100) if p["games_played"] else 0
        tier = p.get("tier", "")
        emoji = TIER_EMOJI.get(tier, "")
        lines.append(
            f"`{i:>2}` <@{p['user_id']}> — **{p['elo']}** {emoji}{tier}  "
            f"({p['games_played']}g · {win_pct:.0f}% · \U0001f525{p['current_streak']})"
        )
    return discord.Embed(
        title="Wordle ELO Leaderboard",
        description="\n".join(lines),
        color=discord.Color.blue(),
    )


def format_rank_embed(player, rank: int, total: int, recent_avg_guesses: float | None = None,
                      tier: str = "") -> discord.Embed:
    win_pct = (player.games_won / player.games_played * 100) if player.games_played else 0
    lines = [
        f"**ELO**: {player.elo}  {TIER_EMOJI.get(tier, '')} {tier}",
        f"**Rank**: {rank} / {total}",
        f"**Games**: {player.games_played} ({player.games_won} wins, {win_pct:.0f}%)",
        f"**Streak**: {player.current_streak} (best {player.best_streak})",
    ]
    if recent_avg_guesses is not None:
        lines.append(f"**Recent avg guesses**: {recent_avg_guesses:.2f}")
    return discord.Embed(
        title=f"<@{player.user_id}>",
        description="\n".join(lines),
        color=discord.Color.green(),
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
