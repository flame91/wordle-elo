import discord
from discord import app_commands

from wordle_elo.commands.help import collect_commands
from wordle_elo.leaderboard import format_help_embed


def test_format_help_embed_renders_commands_and_params():
    infos = [
        ("rank", "Show ELO", [("member", "Optional: another member")]),
        ("version", "Recent releases", [("count", "How many (1..20)")]),
    ]
    embed = format_help_embed(infos)
    desc = embed.description or ""
    assert "`/rank` — Show ELO" in desc
    assert "`member`" in desc
    assert "`/version` — Recent releases" in desc
    assert "`count`" in desc


def test_format_help_embed_handles_paramless_commands():
    embed = format_help_embed([("leaderboard", "Full standings", [])])
    assert "`/leaderboard` — Full standings" in (embed.description or "")


def test_format_help_embed_empty():
    embed = format_help_embed([])
    assert "No commands" in (embed.description or "")


def test_collect_commands_extracts_name_description_params():
    """Adding a command should make it visible via /help with no extra plumbing —
    name, description, and parameter docs all come straight from the Command."""

    async def ping(interaction: discord.Interaction):  # pragma: no cover
        pass

    async def echo(interaction: discord.Interaction, text: str):  # pragma: no cover
        pass

    ping_cmd = app_commands.Command(name="ping", description="Ping the bot", callback=ping)
    echo_cmd = app_commands.Command(name="echo", description="Echo a message", callback=echo)
    app_commands.describe(text="What to echo back")(echo_cmd)

    infos = collect_commands([ping_cmd, echo_cmd])
    names = [i[0] for i in infos]
    assert names == ["echo", "ping"]
    echo_info = next(i for i in infos if i[0] == "echo")
    assert echo_info[1] == "Echo a message"
    assert ("text", "What to echo back") in echo_info[2]


def test_collect_commands_dedupes_by_qualified_name():
    async def f(interaction: discord.Interaction):  # pragma: no cover
        pass

    a = app_commands.Command(name="x", description="first", callback=f)
    b = app_commands.Command(name="x", description="second", callback=f)
    infos = collect_commands([a, b])
    assert len(infos) == 1
