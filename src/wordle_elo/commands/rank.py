from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import desc, func, select

from ..leaderboard import format_rank_embed
from ..models import Player, Submission
from ..tier import assign_tier


class RankCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rank", description="Show Wordle ELO for you (or a member)")
    @app_commands.describe(member="Optional: another member to look up")
    async def rank(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ):
        target = member or interaction.user
        await interaction.response.defer()

        async with self.bot.sessionmaker() as session:
            player = await session.get(Player, target.id)
            if player is None:
                await interaction.followup.send(
                    f"<@{target.id}> hasn't played any tracked Wordle puzzles yet.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return

            ahead = await session.scalar(
                select(func.count()).select_from(Player).where(Player.elo > player.elo)
            )
            total = await session.scalar(select(func.count()).select_from(Player))

            sub_q = (
                select(Submission.guesses)
                .where(Submission.user_id == target.id)
                .order_by(desc(Submission.puzzle_no))
                .limit(14)
                .subquery()
            )
            avg_g = await session.scalar(select(func.avg(sub_q.c.guesses)))

            all_ratings = [r for (r,) in await session.execute(select(Player.elo))]

        tier = assign_tier(player.elo, all_ratings, player.games_played)
        embed = format_rank_embed(
            player,
            rank=(ahead or 0) + 1,
            total=total or 0,
            recent_avg_guesses=float(avg_g) if avg_g is not None else None,
            tier=tier,
        )
        await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(RankCog(bot))
