from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..leaderboard import format_full_leaderboard
from ..nicknames import refresh_from_channel_history
from ..standings import (
    ACTIVE_DAYS,
    build_elo_rows,
    build_glicko2_rows,
)

log = logging.getLogger(__name__)

# Bounded scan: enough to find anyone who has authored in #wordle in the last
# few months, but capped so a /leaderboard call with missing nicknames doesn't
# block on years of history.
NICKNAME_REFRESH_LIMIT = 2000


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show the full ranking leaderboard")
    @app_commands.describe(algorithm="Which rating algorithm to display (default: ELO)")
    @app_commands.choices(
        algorithm=[
            app_commands.Choice(name="ELO — day-relative absolute (default)", value="elo"),
            app_commands.Choice(name="Glicko-2 — LoL-style pairwise", value="glicko2"),
        ]
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        algorithm: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer()
        algo = algorithm.value if algorithm else "elo"

        rows = await self._build_rows(algo)
        if not rows:
            # Trigger a nickname refresh in case the empty result is masking
            # un-resolved Player rows (rare — but parity with the original path).
            await self._maybe_refresh_nicknames(rows)
            await interaction.followup.send(
                f"No players active in the last {ACTIVE_DAYS} days."
            )
            return

        await self._maybe_refresh_nicknames(rows)
        if any(r.get("display_name") is None for r in rows):
            rows = await self._build_rows(algo)

        if algo == "glicko2":
            title = "Wordle Glicko-2 Leaderboard"
            rating_label = "Glicko (±RD)"
        else:
            title = "Wordle ELO Leaderboard"
            rating_label = "ELO"

        embed = format_full_leaderboard(rows, title=title, rating_label=rating_label)
        footer = embed.footer.text if embed.footer is not None else ""
        embed.set_footer(text=f"{footer} · Active in last {ACTIVE_DAYS} days")
        await interaction.followup.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _build_rows(self, algo: str) -> list[dict]:
        if algo == "glicko2":
            return await build_glicko2_rows(self.bot.sessionmaker)
        return await build_elo_rows(self.bot.sessionmaker)

    async def _maybe_refresh_nicknames(self, rows: list[dict]) -> None:
        if not any(r.get("display_name") is None for r in rows):
            return
        try:
            await refresh_from_channel_history(
                self.bot,
                self.bot.sessionmaker,
                self.bot.cfg.wordle_channel_id,
                limit=NICKNAME_REFRESH_LIMIT,
            )
        except Exception:
            log.exception("Auto nickname refresh failed; rendering with stale data")


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
