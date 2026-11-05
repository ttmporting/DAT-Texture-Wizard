"""Logical Melee character groups for the native disc-tree browser.

These are presentation-only folders. Every leaf retains its original FST entry
and path; this module never changes the image's directory table.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from dtw_gamecube import FstEntry


CHARACTER_NAMES = {
    "CA": "Captain Falcon",
    "CL": "Young Link",
    "DK": "Donkey Kong",
    "DR": "Dr. Mario",
    "FC": "Falco",
    "FX": "Fox",
    "GN": "Ganondorf",
    "GW": "Mr. Game & Watch",
    "KB": "Kirby",
    "KP": "Bowser",
    "LG": "Luigi",
    "LK": "Link",
    "MA": "Mario",
    "MS": "Marth",
    "MT": "Mewtwo",
    "NS": "Ness",
    "PC": "Pichu",
    "PE": "Peach",
    "PK": "Pikachu",
    "PR": "Jigglypuff",
    "SS": "Samus",
    "ZD": "Zelda",
    "YS": "Yoshi",
}
# Nana's PlNn assets belong alongside the Ice Climbers' PlCl/PlIc assets.
CODE_ALIASES = {"NN": "IC", "IC": "IC"}
CHARACTER_NAMES["IC"] = "Ice Climbers"

CHARACTER_FILE_SUFFIXES = {".dat", ".usd", ".lat", ".rat"}
_CHARACTER_PREFIX = re.compile(r"^Pl([A-Z]{2})(?=[A-Z0-9_-]*$)", re.IGNORECASE)


@dataclass(frozen=True)
class CharacterGroup:
    """A virtual character folder and its original disc-file entries."""

    code: str
    name: str
    entries: tuple[FstEntry, ...]


def character_code_for_entry(entry: FstEntry) -> str | None:
    """Return the Melee fighter code for a character DAT-like file.

    Unknown two-letter prefixes are ignored rather than accidentally treating
    arbitrary names such as Player.dat as fighter assets.
    """
    if not entry.is_file or PurePosixPath(entry.name).suffix.casefold() not in CHARACTER_FILE_SUFFIXES:
        return None
    match = _CHARACTER_PREFIX.match(entry.name)
    if not match:
        return None
    raw_code = match.group(1).upper()
    code = CODE_ALIASES.get(raw_code, raw_code)
    return code if code in CHARACTER_NAMES else None


def build_character_groups(entries: Iterable[FstEntry]) -> tuple[CharacterGroup, ...]:
    """Collect fighter files by character code without rewriting their paths."""
    grouped: dict[str, list[FstEntry]] = {}
    for entry in entries:
        code = character_code_for_entry(entry)
        if code is not None:
            grouped.setdefault(code, []).append(entry)

    return tuple(
        CharacterGroup(code, CHARACTER_NAMES[code], tuple(grouped[code]))
        for code in sorted(grouped, key=lambda value: (CHARACTER_NAMES[value].casefold(), value))
    )
