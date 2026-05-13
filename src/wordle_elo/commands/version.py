from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..leaderboard import format_version_embed
from ..version import load_versions

DEFAULT_COUNT = 5
MAX_COUNT = 20


class VersionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="version", description="Show recent release history")
    @app_commands.describe(count=f"How many versions to show (1..{MAX_COUNT}, default {DEFAULT_COUNT})")
    async def version(
        self,
        interaction: discord.Interaction,
        count: int = DEFAULT_COUNT,
    ):
        count = max(1, min(MAX_COUNT, count))
        entries = load_versions()
        embed = format_version_embed(entries[:count])
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(VersionCog(bot))
