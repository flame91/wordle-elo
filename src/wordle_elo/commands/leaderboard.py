from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import desc, func, select

from ..leaderboard import format_full_leaderboard
from ..models import Nickname, Player, Submission
from ..nicknames import refresh_from_channel_history
from ..tier import assign_tier

log = logging.getLogger(__name__)

ACTIVE_DAYS = 7

# Bounded scan: enough to find anyone who has authored in #wordle in the last
# few months, but capped so a /leaderboard call with missing nicknames doesn't
# block on years of history.
NICKNAME_REFRESH_LIMIT = 2000


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show the full ELO leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()

        players, nicks, avg_by_user = await self._load(self.bot.sessionmaker)

        missing = [p.user_id for p in players if p.user_id not in nicks]
        if missing:
            try:
                await refresh_from_channel_history(
                    self.bot,
                    self.bot.sessionmaker,
                    self.bot.cfg.wordle_channel_id,
                    limit=NICKNAME_REFRESH_LIMIT,
                )
            except Exception:
                log.exception("Auto nickname refresh failed; rendering with stale data")
            else:
                _, nicks, _ = await self._load(self.bot.sessionmaker)

        if not players:
            await interaction.followup.send(
                f"No players active in the last {ACTIVE_DAYS} days."
            )
            return

        all_ratings = [p.elo for p in players]
        rows = [
            {
                "user_id": p.user_id,
                "display_name": nicks.get(p.user_id),
                "elo": p.elo,
                "tier": assign_tier(p.elo, all_ratings, p.games_played),
                "games_played": p.games_played,
                "games_won": p.games_won,
                "best_streak": p.best_streak,
                "current_streak": p.current_streak,
                "avg_winning_guesses": avg_by_user.get(p.user_id),
            }
            for p in players
        ]
        embed = format_full_leaderboard(rows)
        if embed.footer is not None and embed.footer.text:
            embed.set_footer(
                text=f"{embed.footer.text} · Active in last {ACTIVE_DAYS} days"
            )
        else:
            embed.set_footer(text=f"Active in last {ACTIVE_DAYS} days")
        await interaction.followup.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @staticmethod
    async def _load(sessionmaker):
        cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)
        async with sessionmaker() as session:
            players = (
                await session.execute(
                    select(Player)
                    .where(Player.last_played_at.is_not(None))
                    .where(Player.last_played_at >= cutoff)
                    .order_by(desc(Player.elo))
                )
            ).scalars().all()
            nick_rows = (await session.execute(select(Nickname))).scalars().all()
            nicks = {n.user_id: n.display_name for n in nick_rows}
            avg_rows = await session.execute(
                select(Submission.user_id, func.avg(Submission.guesses))
                .where(Submission.guesses <= 6)
                .group_by(Submission.user_id)
            )
            avg_by_user = {uid: float(avg) for uid, avg in avg_rows}
        return players, nicks, avg_by_user


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
