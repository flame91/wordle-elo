from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..leaderboard import format_season_finale_embed
from ..nicknames import refresh_from_channel_history
from ..seasons import (
    current_season_label,
    list_archived_seasons,
    load_season_archive,
)
from ..standings import (
    ACTIVE_DAYS,
    build_elo_rows,
    build_glicko2_rows,
    render_leaderboard_embed,
    resolve_names,
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
    @app_commands.describe(
        algorithm="Which rating algorithm to display (default: ELO)",
        season="Past season to view (e.g. 2026-Q1); omit for the current season",
    )
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
        season: str | None = None,
    ):
        await interaction.response.defer()
        algo = algorithm.value if algorithm else "elo"

        if season:
            await self._send_season_archive(interaction, season)
            return

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

        label = await current_season_label(self.bot.sessionmaker)
        embed = render_leaderboard_embed(rows, algo, season_label=label)
        await interaction.followup.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _send_season_archive(self, interaction: discord.Interaction, label: str) -> None:
        label = label.strip().upper()
        ranked = await load_season_archive(self.bot.sessionmaker, label)
        if not ranked:
            available = await list_archived_seasons(self.bot.sessionmaker)
            hint = f" Available: {', '.join(available)}." if available else ""
            await interaction.followup.send(f"No archived season `{label}`.{hint}")
            return
        names = await resolve_names(
            self.bot.sessionmaker, [r["user_id"] for r in ranked]
        )
        embed = format_season_finale_embed(label, ranked, names, top=25)
        await interaction.followup.send(
            embed=embed, allowed_mentions=discord.AllowedMentions.none()
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
