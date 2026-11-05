"""Logical Melee stage folders for the native disc-tree browser."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from dtw_gamecube import FstEntry
from dtw_disc_labels import ONE_PLAYER_STAGE_CODES, STAGE_NAMES, stage_description


@dataclass(frozen=True)
class StageGroup:
    """A virtual stage folder and its original FST file entries."""

    key: str
    category: str
    name: str
    entries: tuple[FstEntry, ...]


def _stage_key_and_group(entry: FstEntry) -> tuple[str, str, str] | None:
    if not entry.is_file or not entry.name.casefold().startswith("gr"):
        return None
    name = entry.name
    stem = name.rsplit(".", 1)[0] if "." in name else name
    suffix = ("." + name.rsplit(".", 1)[1]).upper() if "." in name else ""
    code = name[2:5].upper()
    if len(stem) >= 5 and stem[2:3].upper() == "T":
        character_code = stem[3:5].upper()
        description = stage_description(name) or "Target Test stage"
        return ("target:" + character_code, "Target Tests", description.removesuffix(" stage"),)
    if code in ONE_PLAYER_STAGE_CODES:
        name_for_stage = STAGE_NAMES.get(code, stage_description(name) or "1P Mode Stage")
        return ("1p:" + code, "1P Mode", name_for_stage)
    # Stadium variants use GrP0.usd, GrP1.usd, etc.
    if stem[2:3].upper() == "P" and len(stem) > 3 and stem[3].isalnum():
        return ("stage:PS.", "Stages", STAGE_NAMES["PS."])
    if code in STAGE_NAMES:
        return ("stage:" + code, "Stages", STAGE_NAMES[code])
    # Named 20XX/custom variations can still be grouped under their recognizable
    # three-character vanilla base when that base exists.
    special_name = stage_description(name)
    if special_name and special_name != "Stage file":
        return ("custom:" + stem[2:].upper(), "Stages", special_name)
    return ("other", "Other Stage Files", "Other Stage Files")


def build_stage_groups(entries: Iterable[FstEntry]) -> tuple[StageGroup, ...]:
    """Group Gr-prefixed stage DAT/USD assets without changing real disc paths."""
    grouped: dict[tuple[str, str, str], list[FstEntry]] = {}
    for entry in entries:
        identity = _stage_key_and_group(entry)
        if identity is not None:
            grouped.setdefault(identity, []).append(entry)

    return tuple(
        StageGroup(key, category, name, tuple(files))
        for (key, category, name), files in sorted(
            grouped.items(), key=lambda item: (item[0][1].casefold(), item[0][2].casefold(), item[0][0])
        )
    )
