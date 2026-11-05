"""Human-readable labels ported from the upstream DTW v6.1.4 lookup tables.

This module only labels files; it never modifies on-disc filenames or paths.
"""
from __future__ import annotations

from pathlib import PurePosixPath


# Names mirror the original DTW character lookup, including its special labels.
CHARACTER_FILE_NAMES = {
    "BO": "[Boy] Male Wireframe", "CA": "Captain Falcon",
    "CH": "Crazy Hand", "CL": "Child/Young Link", "CO": "Common to the cast",
    "DD": "Diddy", "DK": "Donkey Kong", "DR": "Dr. Mario",
    "FC": "Falco", "FE": "[Fire Emblem] Roy", "FX": "Fox",
    "GK": "[GigaKoopa] GigaBowser", "GL": "[Girl] Female Wireframe",
    "GN": "Ganondorf", "GW": "Game 'n Watch", "IC": "Ice Climbers",
    "KB": "Kirby", "KP": "[Koopa] Bowser", "LC": "Lucas",
    "LG": "Luigi", "LK": "Link", "LZ": "Charizard",
    "MH": "Master Hand", "MN": "Menus Data", "MR": "Mario",
    "MS": "[Mars] Marth", "MT": "Mewtwo", "NN": "[Nana] Ice Climbers",
    "NS": "Ness", "PC": "Pichu", "PE": "Peach", "PK": "Pikachu",
    "PN": "[Popo/Nana] Ice Climbers", "PP": "[Popo] Ice Climbers",
    "PR": "[Purin] Jigglypuff", "SB": "SandBag", "SK": "Sheik",
    "SS": "Samus", "WF": "Wolf", "YS": "Yoshi", "ZD": "Zelda",
}

CHARACTER_COLOR_NAMES = {
    "AQ": "aqua", "BK": "black", "BR": "brown", "BU": "blue",
    "GR": "green", "GY": "gray", "LA": "lavender", "NR": "neutral",
    "OR": "orange", "PI": "pink", "RD": "red", "RE": "red",
    "RL": "red", "RR": "red", "WH": "white", "YE": "yellow",
}

STAGE_NAMES = {
    "BB.": "Big Blue", "CN.": "Corneria", "CS.": "Princess Peach's Castle",
    "EF1": "Goomba Trophy Stage", "EF2": "Entei Trophy Stage",
    "EF3": "Majora Trophy Stage", "FS.": "Fourside", "FZ.": "Flat Zone",
    "GB.": "Great Bay", "GD.": "Jungle Japes [Garden]", "GR.": "Green Greens",
    "HE.": "All-Star Rest Area [Heal]", "HR.": "Homerun Contest",
    "I1.": "Mushroom Kingdom", "I2.": "Mushroom Kingdom II (Subcon)",
    "TIC": "Icetop (unused stage)", "IM.": "Icicle Mountain",
    "IZ.": "Fountain of Dreams [Izumi]", "KG.": "Kongo Jungle",
    "KR.": "Brinstar Depths [Kraid]", "MC.": "Mute City",
    "NBA": "Battlefield", "NBR": "F-Zero Grand Prix",
    "NFG": "Trophy Collector [Figure Get]", "NKR": "Mushroom Kingdom Adventure",
    "NLA": "Final Destination", "NPO": "Pushon?",
    "NSR": "Hyrule Maze", "NZR": "Brinstar Escape Shaft [Zebes]",
    "OK.": "Kongo Jungle (N64)", "OP.": "Dream Land (N64)", "OT.": "Onett",
    "OY.": "Yoshi's Island (N64)", "PS.": "Pokemon Stadium",
    "PS1": "Pokemon Stadium - Fire Form", "PS2": "Pokemon Stadium - Grass Form",
    "PS3": "Pokemon Stadium - Water Form", "PS4": "Pokemon Stadium - Rock Form",
    "PU.": "Poke Floats [Pura]", "RC.": "Rainbow Cruise",
    "SH.": "Hyrule Temple [Shrine]", "ST.": "Yoshi's Story",
    "TE.": '"TEST" (a.k.a. The Coffee Shop)', "VE.": "Venom",
    "YT.": "Yoshi's Island", "ZE.": "Brinstar [Zebes]",
}

ONE_PLAYER_STAGE_CODES = {
    "EF1", "EF2", "EF3", "HE.", "HR.", "NBR", "NFG", "NKR", "NSR", "NZR", "TE."
}

# Vanilla filename-to-variant labels in DTW v6.1.4 / its 20XX lookup table.
SPECIAL_STAGE_VARIANTS = {
    "C0.USD": "Sector Z",
    "CS.0AT": "Omega Peach's Castle",
    "FS.1AT": "Smashville Fourside",
    "FS.2AT": "Moonside",
    "GB.0AT": "Turtle Stage",
    "GB.1AT": "Great Bay, Beach",
    "GB.HAT": "Great Bay, Hacked",
    "GD.1AT": "Jungle Japes, Hacked (w/platform)",
    "GD.2AT": "Jungle Japes, Omega",
    "GR.1AT": "Green Greens, Hacked",
    "HE.0AT": "Walk-Off Heal",
    "I1.0AT": "Milun's Mushroom Kingdom",
    "I1.1AT": "Porygon",
    "I1.2AT": "Shiny Porygon",
    "IZ.GAT": "Cave of Dreams",
    "KG.HAT": "Kongo Jungle, Hacked",
    "NBA.2AT": "Ancient Battlefield",
    "NBA.3AT": "Battlefield Plaza",
    "NBA.4AT": "Matrix Battlefield",
    "NBA.BAT": "Battlefield Plaza",
    "NBA.GAT": "Brawl Battlefield - Day",
    "NBA.HAT": "Brawl Battlefield - Day (w/Castle)",
    "NBA.IAT": "Brawl Battlefield - Void",
    "NBA.LAT": "Brawl Battlefield",
    "NFG.0AT": "Trophy Collector (Two platforms)",
    "NFG.1AT": "Trophy Collector (Three platforms)",
    "NFG.2AT": "Trophy Collector, Omega",
    "NKR.1AT": "Mushroom Kingdom Adventure, Hacked",
    "NKR.2AT": "Mushroom Kingdom Adventure, Omega",
    "NLA.0AT": "Final Destination",
    "NLA.2AT": "Wii-U Final Destination",
    "NLA.GAT": "Wii-U Final Destination",
    "NLA.HAT": "zankyou FD",
    "NSR.1AT": "Hyrule Maze, Hacked",
    "OK.0AT": "Monster Island",
    "OP.GAT": "Halberd Land",
    "OP.KAT": "KirbyWare, Inc.",
    "OP.RAT": "Return to Dream Land",
    "OY.HAT": "Yoshi's Island (N64), Milun Hack",
    "OY.WAT": "WarioWare, Inc.",
    "PB.USD": "Pokemon Stadium (Blue, No transforms)",
    "PG.USD": "Indigo Stadium",
    "PN.USD": "Pokemon Stadium (Blue, No transforms)",
    "SH.SAT": "Skyrule (Redux)",
    "SH.0AT": "Dark Temple",
    "ST.GAT": "Peach's Story",
    "TCA.GAT": "Silph Co. (Saffron City)",
    "TCL.BAT": "Smash 4 Battlefield",
    "TCL.GAT": "Brawl Battlefield - Dusk",
    "TCL.SAT": "Suzaku Castle",
    "TDK.0AT": "Meta Mine",
    "TDR.0AT": "Training Room",
    "TFE.KAT": "Kalos Pokémon League",
    "TFX.0AT": "The Plain",
    "TGN.0AT": "75m",
    "TKB.GAT": "Miiverse (variation 1)",
    "TKB.HAT": "Miiverse (variation 2)",
    "TKB.IAT": "Miiverse (variation 3)",
    "TKB.JAT": "Miiverse (variation 4)",
    "TKP.MAT": "Metroid Lab",
    "TLG.1AT": "Giant GameCube",
    "TLG.MAT": "Metal Cavern M",
    "TLK.0AT": "Lylat Cruise",
    "TMS.0AT": "Toy Time",
    "TNS.0AT": "Throne Room (Wario Land)",
    "TPE.HAT": "Hyrule Castle (N64)",
    "TSK.0AT": "Meta Crystal",
    "YT.1AT": "Yoshi's Island, Hacked",
    "YT.2AT": "Milun's Island - Form A",
    "YT.3AT": "Milun's Island - Form B",
    "YT.4AT": "Milun's Island - Form C",
}

MISC_FILE_NAMES = {
    "CODES": "Custom codes file",
    "GMGOVER": "1P Mode: Game Over Screen",
    "GMPAUSE": "Pause Screen",
    "GMRST": "Results Screen",
    "GMSTROLL": "Credits Screen/Minigame",
    "GMTITLE": "Title Screen",
    "GMTOU1P": "Tournament Mode, File 1",
    "GMTOU2P": "Tournament Mode, File 2",
    "GMTOU3P": "Tournament Mode, File 3",
    "GMTOU4P": "Tournament Mode, File 4",
    "GMTRAIN": "Training Mode",
    "GMTTALL": "Title Screen",
    "IFCOMS0": "Dual 1v1 Infographic",
    "IFCOMS1": "Chess Melee Infographic",
    "IFCOMS2": "Dodgeball Infographic",
    "IFCOMS3": "NBA Jam Infographic",
    "IFCOMS4": "SD Remix Infographic",
    "IFCOMS5": "SSBM Tier List",
    "IFHRNOCN": "Home Run Contest, File 1",
    "IFHRRECO": "Home Run Contest, File 2",
    "IFPRIZE": "Special Achievement Messages",
    "IFVSCAM": "Special Melee: Camera Mode",
    "IRALS": '1P Mode: "VS." Intro Screens',
    "ITCO": "Items",
    "LBMCGAME": "Memory card banners and icon",
    "LBMCSNAP": "Memory card snapshot banner/icon",
    "MXDT": "m-ex metadata and helper functions",
    "MNEXTALL": "Extra menu graphics for the CSS",
    "MNMAALL": "Main menu graphics file",
    "MNSLCHR": "Character Select Screen",
    "MNSLMAP": "Stage Select Screen",
    "NTAPPRO": "'New Challenger' Screens",
    "OPENING": "Game banner, title, and description texts",
    "PLCO": "Textures common to the cast",
    "SDMENU": "Special menu characters",
}


def character_description(filename: str, is_20xx: bool = False) -> str | None:
    """Return DTW-style description for a PlXX character file."""
    name = PurePosixPath(filename).name
    if not name.casefold().startswith("pl") or name.casefold() == "plco.dat":
        return None
    stem = PurePosixPath(name).stem
    if len(stem) < 4:
        return "Character data"
    character = CHARACTER_FILE_NAMES.get(stem[2:4].upper(), "Unknown Character")
    prefix = character + ("' " if character.endswith("s") else "'s ")
    color_key = name[4:6].upper()
    ext = PurePosixPath(name).suffix.casefold()
    if color_key == ".D":
        description = prefix + "NTSC data & shared textures"
    elif color_key == ".P":
        description = prefix + "PAL data & shared textures"
    elif color_key == ".S":
        description = prefix + "SDR data & shared textures"
    elif color_key == "AJ":
        description = prefix + "animation data"
    elif color_key == "CP":
        copy_name = CHARACTER_FILE_NAMES.get(stem[6:8].upper(), "")
        if "]" in copy_name:
            copy_name = copy_name.split("]", 1)[1].strip()
        description = prefix + ("copy power (" + copy_name + ")" if copy_name else "copy power")
    elif color_key == "DV":
        description = prefix + "idle animation data"
    else:
        color = CHARACTER_COLOR_NAMES.get(color_key, "Unknown color")
        description = prefix + color + " costume"
    if is_20xx and (ext == ".lat" or color_key == "RL"):
        description += " ('L' alt)"
    elif is_20xx and (ext == ".rat" or color_key == "RR"):
        description += " ('R' alt)"
    if ext == ".usd" and not name.casefold().startswith("plca"):
        description += " (English)"
    return description


def stage_description(filename: str) -> str | None:
    """Return an upstream-DTW-style name for a Gr-prefixed stage file."""
    name = PurePosixPath(filename).name
    if not name.casefold().startswith("gr") or len(name) < 5:
        return None
    stem = PurePosixPath(name).stem
    suffix = PurePosixPath(name).suffix.upper()
    key = (stem[2:] + suffix).upper()
    variant = SPECIAL_STAGE_VARIANTS.get(key)
    if variant:
        return variant
    code = name[2:5].upper()
    if len(stem) >= 5 and stem[2:3].upper() == "T":
        char = CHARACTER_FILE_NAMES.get(stem[3:5].upper())
        if char:
            return (char + ("' " if char.endswith("s") else "'s ") + "Target Test stage")
    if code in STAGE_NAMES:
        return STAGE_NAMES[code]
    if code == "P" + stem[3:4].upper() + "." or (len(stem) > 3 and stem[2:3].upper() == "P" and stem[3:4].isalnum()):
        return STAGE_NAMES["PS."]
    return "Stage file"


def disc_file_description(filename: str) -> str:
    """Return a best-effort semantic label for a Melee disc file."""
    name = PurePosixPath(filename).name
    character = character_description(name)
    if character:
        return character
    if name.casefold() == "plco.dat":
        return "Textures common to the cast"
    if name.casefold().startswith("ef"):
        if name.casefold() == "effxdata.dat":
            return "Fox & Falco graphical effects"
        code = name[2:4].upper()
        return (CHARACTER_FILE_NAMES.get(code, "Character") + " graphical effects").strip()
    if name.casefold().startswith("gmrstm"):
        code = name[6:8].upper()
        return CHARACTER_FILE_NAMES.get(code, "Character") + " results-screen animation"
    stage = stage_description(name)
    if stage:
        return stage
    return MISC_FILE_NAMES.get(PurePosixPath(name).stem.upper(), "")
