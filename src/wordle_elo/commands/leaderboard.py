from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import desc, select

from ..leaderboard import format_full_leaderboard
from ..models import Player
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
        if not players:
            await interaction.followup.send("No players tracked yet.")
            return
        all_ratings = [p.elo for p in players]
        rows = []
        for p in players:
            rows.append(
                {
                    "user_id": p.user_id,
                    "display_name": p.display_name,
                    "elo": p.elo,
                    "tier": assign_tier(p.elo, all_ratings, p.games_played),
                    "games_played": p.games_played,
                    "games_won": p.games_won,
                    "current_streak": p.current_streak,
                }
            )
        await interaction.followup.send(
            embed=format_full_leaderboard(rows),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
