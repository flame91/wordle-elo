from pathlib import Path

from wordle_elo.leaderboard import format_version_embed
from wordle_elo.version import VersionEntry, load_versions, parse_changelog

SAMPLE = """# Changelog

Some preamble that should be ignored.

## [Unreleased]

### Added
- New shiny thing.

## [0.2.0] - 2026-05-13

### Changed
- Switched to absolute ELO.

## [0.1.0] - 2026-05-12

### Added
- Initial release.
"""


def test_parse_changelog_extracts_versions_in_order():
    entries = parse_changelog(SAMPLE)
    assert [e.version for e in entries] == ["Unreleased", "0.2.0", "0.1.0"]


def test_parse_changelog_captures_dates():
    entries = parse_changelog(SAMPLE)
    assert entries[0].date is None
    assert entries[1].date == "2026-05-13"
    assert entries[2].date == "2026-05-12"


def test_parse_changelog_captures_body():
    entries = parse_changelog(SAMPLE)
    assert "New shiny thing" in entries[0].body
    assert "absolute ELO" in entries[1].body
    assert "Initial release" in entries[2].body
    # Body for one entry must not bleed into the next
    assert "absolute ELO" not in entries[0].body
    assert "Initial release" not in entries[1].body


def test_parse_changelog_returns_empty_when_no_versions():
    assert parse_changelog("# Changelog\n\nNothing yet.\n") == []


def test_load_versions_reads_repo_changelog():
    repo_changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    entries = load_versions(repo_changelog)
    assert len(entries) >= 1
    # First entry must have a version label
    assert entries[0].version


def test_load_versions_returns_empty_for_missing_path(tmp_path):
    assert load_versions(tmp_path / "does-not-exist.md") == []


def test_format_version_embed_highlights_first_entry():
    entries = [
        VersionEntry(version="Unreleased", date=None, body="- x"),
        VersionEntry(version="0.1.0", date="2026-05-12", body="- y"),
    ]
    embed = format_version_embed(entries)
    desc = embed.description or ""
    # First entry is highlighted with ▶ and *(current)*
    assert "▶" in desc
    assert "(current)" in desc
    # Second entry is not highlighted
    second_idx = desc.index("[0.1.0]")
    assert "▶" not in desc[second_idx:]


def test_format_version_embed_empty_list():
    embed = format_version_embed([])
    assert "No CHANGELOG" in (embed.description or "")
