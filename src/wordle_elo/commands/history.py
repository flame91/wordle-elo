from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import desc, select

from ..leaderboard import format_history_embed
from ..models import Submission


class HistoryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="history", description="Show recent Wordle results")
    @app_commands.describe(
        member="Optional: member to look up",
        days="How many recent puzzles to show (1..60, default 14)",
    )
    async def history(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        days: int = 14,
    ):
        target = member or interaction.user
        days = max(1, min(60, days))
        await interaction.response.defer()
        async with self.bot.sessionmaker() as session:
            rows = (
                await session.execute(
                    select(Submission)
                    .where(Submission.user_id == target.id)
                    .order_by(desc(Submission.puzzle_no))
                    .limit(days)
                )
            ).scalars().all()
        if not rows:
            await interaction.followup.send(
                f"<@{target.id}> has no tracked submissions yet.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await interaction.followup.send(
            embed=format_history_embed(target.id, rows),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot):
    await bot.add_cog(HistoryCog(bot))
