from __future__ import annotations

import logging

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands

from .config import Config
from .db import init_db, make_engine, make_sessionmaker
from .pipeline import process_message
from .scheduler import catch_up

log = logging.getLogger(__name__)


class WordleEloBot(commands.Bot):
    def __init__(self, cfg: Config):
        intents = discord.Intents.default()
        intents.message_content = True   # privileged — must be enabled in Developer Portal
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.cfg = cfg
        self.engine = make_engine(cfg.db_path)
        self.sessionmaker = make_sessionmaker(self.engine)
        self.apscheduler: AsyncIOScheduler | None = None

    async def setup_hook(self) -> None:
        await init_db(self.engine)

        # Cogs
        await self.load_extension("wordle_elo.commands.rank")
        await self.load_extension("wordle_elo.commands.leaderboard")
        await self.load_extension("wordle_elo.commands.history")

        # Sync slash commands to a single guild for instant availability
        guild_obj = discord.Object(id=self.cfg.discord_guild_id)
        self.tree.copy_global_to(guild=guild_obj)
        await self.tree.sync(guild=guild_obj)

        # Catch-up: every day 00:30 in the bot's timezone
        self.apscheduler = AsyncIOScheduler(timezone=self.cfg.tz)
        self.apscheduler.add_job(
            catch_up,
            "cron",
            hour=0,
            minute=30,
            args=[self],
            id="daily_catchup",
            replace_existing=True,
        )
        self.apscheduler.start()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id=%s)", self.user, getattr(self.user, "id", "?"))

    async def on_message(self, msg: discord.Message) -> None:
        if msg.channel.id != self.cfg.wordle_channel_id:
            return
        if msg.author.id != self.cfg.wordle_app_id:
            return
        try:
            await process_message(self, msg)
        except Exception:
            log.exception("Failed to process message %s", msg.id)
            await self._notify_admin(f"Failed to process message {msg.id}")

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.channel.id != self.cfg.wordle_channel_id:
            return
        if after.author.id != self.cfg.wordle_app_id:
            return
        # Re-parse, but don't repost leaderboard (already posted on first arrival)
        try:
            await process_message(self, after, silent=True)
        except Exception:
            log.exception("Failed to reprocess edited message %s", after.id)

    async def _notify_admin(self, text: str) -> None:
        if not self.cfg.admin_user_id:
            return
        try:
            user = await self.fetch_user(self.cfg.admin_user_id)
            await user.send(text)
        except Exception:
            log.exception("Failed to notify admin")
