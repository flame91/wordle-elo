from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..leaderboard import format_full_leaderboard
from ..standings import build_leaderboard_rows


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show the full ELO leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = await build_leaderboard_rows(self.bot.sessionmaker)
        if not rows:
            await interaction.followup.send("No players tracked yet.")
            return
        await interaction.followup.send(
            embed=format_full_leaderboard(rows),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
