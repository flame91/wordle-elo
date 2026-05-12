from datetime import date
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_bot_token: str = Field(alias="DISCORD_BOT_TOKEN")
    discord_guild_id: int = Field(alias="DISCORD_GUILD_ID")
    wordle_channel_id: int = Field(alias="WORDLE_CHANNEL_ID")
    wordle_app_id: int = Field(alias="WORDLE_APP_ID")
    admin_user_id: int | None = Field(default=None, alias="ADMIN_USER_ID")

    tz: str = Field(default="Asia/Seoul", alias="TZ")
    db_path: Path = Field(default=Path("/data/wordle.db"), alias="DB_PATH")
    log_dir: Path = Field(default=Path("/data/logs"), alias="LOG_DIR")

    initial_elo: int = Field(default=1000, alias="INITIAL_ELO")
    k_factor: int = Field(default=24, alias="K_FACTOR")
    placement_games: int = Field(default=14, alias="PLACEMENT_GAMES")
    season_start_date: date = Field(default=date(2026, 5, 12), alias="SEASON_START_DATE")


def load_config() -> Config:
    return Config()  # type: ignore[call-arg]
