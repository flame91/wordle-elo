import asyncio
import logging
import logging.handlers
from pathlib import Path

from .bot import WordleEloBot
from .config import load_config


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


async def main() -> None:
    cfg = load_config()
    setup_logging(cfg.log_dir)
    bot = WordleEloBot(cfg)
    await bot.start(cfg.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
