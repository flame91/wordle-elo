"""CHANGELOG.md loader for the /version command."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Matches "## [VERSION]" optionally followed by "- DATE".
_VERSION_RE = re.compile(r"^##\s+\[([^\]]+)\](?:\s*[-–]\s*(.+?))?\s*$", re.MULTILINE)


@dataclass(frozen=True)
class VersionEntry:
    version: str
    date: str | None
    body: str


def parse_changelog(text: str) -> list[VersionEntry]:
    matches = list(_VERSION_RE.finditer(text))
    entries: list[VersionEntry] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries.append(
            VersionEntry(
                version=m.group(1).strip(),
                date=(m.group(2) or "").strip() or None,
                body=text[start:end].strip(),
            )
        )
    return entries


def _find_changelog() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "CHANGELOG.md"
        if candidate.exists():
            return candidate
    return None


def load_versions(path: Path | None = None) -> list[VersionEntry]:
    p = path or _find_changelog()
    if p is None or not p.exists():
        return []
    return parse_changelog(p.read_text(encoding="utf-8"))
