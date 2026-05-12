from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import desc, func, select

from ..leaderboard import format_full_leaderboard
from ..models import Player, Submission
from ..tier import assign_tier


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show the full ELO leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with self.bot.sessionmaker() as session:
            players = (
                await session.execute(select(Player).order_by(desc(Player.elo)))
            ).scalars().all()

            avg_rows = await session.execute(
                select(Submission.user_id, func.avg(Submission.guesses))
                .where(Submission.guesses <= 6)
                .group_by(Submission.user_id)
            )
            avg_by_user = {uid: float(avg) for uid, avg in avg_rows}

        if not players:
            await interaction.followup.send("No players tracked yet.")
            return

        all_ratings = [p.elo for p in players]
        rows = []
        for p in players:
            rows.append(
                {
                    "user_id": p.user_id,
                    "elo": p.elo,
                    "tier": assign_tier(p.elo, all_ratings, p.games_played),
                    "games_played": p.games_played,
                    "games_won": p.games_won,
                    "best_streak": p.best_streak,
                    "current_streak": p.current_streak,
                    "avg_winning_guesses": avg_by_user.get(p.user_id),
                }
            )
        await interaction.followup.send(
            embed=format_full_leaderboard(rows),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
