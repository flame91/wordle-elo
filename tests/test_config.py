"""Verify env → ELO knob plumbing via config.bootstrap()."""

import importlib

import pytest


@pytest.fixture
def restore_elo_defaults():
    """Save and restore elo module globals so configure() in one test doesn't
    leak into others (test isolation)."""
    from wordle_elo import elo
    saved = (elo.INITIAL, elo.K, elo.K_NEW, elo.NEW_PLAYER_GAMES, elo.DELTA_CLAMP)
    yield
    elo.INITIAL, elo.K, elo.K_NEW, elo.NEW_PLAYER_GAMES, elo.DELTA_CLAMP = saved


def test_configure_overrides_module_globals(restore_elo_defaults):
    from wordle_elo import elo
    elo.configure(initial=1500, k=16, k_new=64, new_player_games=20, delta_clamp=60)
    assert elo.INITIAL == 1500
    assert elo.K == 16
    assert elo.K_NEW == 64
    assert elo.NEW_PLAYER_GAMES == 20
    assert elo.DELTA_CLAMP == 60


def test_configure_partial_update_keeps_others(restore_elo_defaults):
    from wordle_elo import elo
    elo.configure(k=99)  # only K
    assert elo.K == 99
    assert elo.K_NEW == 40  # untouched default


def test_k_factor_uses_configured_threshold(restore_elo_defaults):
    from wordle_elo import elo
    elo.configure(k_new=50, k=10, new_player_games=3)
    assert elo.k_factor(0) == 50
    assert elo.k_factor(2) == 50
    assert elo.k_factor(3) == 10
    assert elo.k_factor(100) == 10


def test_bootstrap_pushes_env_into_elo(monkeypatch, tmp_path, restore_elo_defaults):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "x")
    monkeypatch.setenv("DISCORD_GUILD_ID", "1")
    monkeypatch.setenv("WORDLE_CHANNEL_ID", "2")
    monkeypatch.setenv("WORDLE_APP_ID", "3")
    monkeypatch.setenv("INITIAL_ELO", "1100")
    monkeypatch.setenv("K_FACTOR", "20")
    monkeypatch.setenv("K_FACTOR_NEW", "50")
    monkeypatch.setenv("NEW_PLAYER_GAMES", "15")
    monkeypatch.setenv("DELTA_CLAMP", "60")
    # pydantic-settings reads .env file by default — point it elsewhere
    monkeypatch.chdir(tmp_path)

    from wordle_elo import config as config_mod
    importlib.reload(config_mod)
    cfg = config_mod.bootstrap()

    from wordle_elo import elo
    assert elo.INITIAL == 1100
    assert elo.K == 20
    assert elo.K_NEW == 50
    assert elo.NEW_PLAYER_GAMES == 15
    assert elo.DELTA_CLAMP == 60
    assert cfg.initial_elo == 1100
