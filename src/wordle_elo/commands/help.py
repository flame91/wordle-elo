from __future__ import annotations

from collections.abc import Iterable

import discord
from discord import app_commands
from discord.ext import commands

from ..leaderboard import format_help_embed


def collect_commands(
    cmds: Iterable[app_commands.Command | app_commands.Group],
) -> list[tuple[str, str, list[tuple[str, str]]]]:
    seen: dict[str, tuple[str, str, list[tuple[str, str]]]] = {}
    for cmd in cmds:
        if not isinstance(cmd, app_commands.Command):
            continue
        params = [(p.name, p.description or "") for p in cmd.parameters]
        seen[cmd.qualified_name] = (cmd.qualified_name, cmd.description or "", params)
    return sorted(seen.values(), key=lambda c: c[0])


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="List all available commands")
    async def help(self, interaction: discord.Interaction):
        infos = collect_commands(self.bot.tree.walk_commands(guild=interaction.guild))
        if not infos:
            infos = collect_commands(self.bot.tree.walk_commands())
        await interaction.response.send_message(embed=format_help_embed(infos))


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
