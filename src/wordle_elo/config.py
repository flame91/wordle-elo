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
    k_factor_new: int = Field(default=40, alias="K_FACTOR_NEW")
    new_player_games: int = Field(default=10, alias="NEW_PLAYER_GAMES")
    delta_clamp: int = Field(default=40, alias="DELTA_CLAMP")
    damping_anchor: int = Field(default=800, alias="DAMPING_ANCHOR")
    placement_games: int = Field(default=14, alias="PLACEMENT_GAMES")
    season_start_date: date = Field(default=date(2025, 10, 22), alias="SEASON_START_DATE")

    # Quarterly seasons. SEASON_EPOCH is the first boundary the rollover job
    # acts on; earlier puzzles seed the first season without a reset. On each
    # quarter rollover ratings regress toward INITIAL by SEASON_CARRY.
    season_epoch: date = Field(default=date(2026, 1, 1), alias="SEASON_EPOCH")
    season_carry: float = Field(default=0.5, alias="SEASON_CARRY")

    # Date-based puzzle-no fallback (Wordle Activity messages no longer embed the number)
    wordle_epoch_date: date = Field(default=date(2021, 6, 19), alias="WORDLE_EPOCH_DATE")


def load_config() -> Config:
    return Config()  # type: ignore[call-arg]


def bootstrap() -> Config:
    """Load config + push ELO knobs into the elo module so module-level
    constants (INITIAL, K, K_NEW, NEW_PLAYER_GAMES, DELTA_CLAMP) reflect
    user overrides. Call this in every entry point (bot + every script).
    """
    cfg = load_config()
    from . import elo, parser, season

    elo.configure(
        initial=cfg.initial_elo,
        k=cfg.k_factor,
        k_new=cfg.k_factor_new,
        new_player_games=cfg.new_player_games,
        delta_clamp=cfg.delta_clamp,
        damping_anchor=cfg.damping_anchor,
    )
    parser.configure(epoch_date=cfg.wordle_epoch_date, tz_name=cfg.tz)
    season.configure(
        wordle_epoch=cfg.wordle_epoch_date,
        season_epoch=cfg.season_epoch,
        carry=cfg.season_carry,
        anchor=cfg.initial_elo,
    )
    return cfg
