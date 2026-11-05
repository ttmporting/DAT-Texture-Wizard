import unittest

from dtw_character_tree import build_character_groups, character_code_for_entry
from dtw_gamecube import FstEntry


def make_entry(index, name, path=None, kind="file"):
    path = path or "GTME01/P-GTME/files/" + name
    return FstEntry(
        index=index,
        name=name,
        path=path,
        kind=kind,
        parent_index=3,
        declared_parent_index=3,
        offset=0x1000 + index * 0x20 if kind == "file" else None,
        size=128 if kind == "file" else None,
        next_index=None,
    )


class CharacterTreeTests(unittest.TestCase):
    def test_groups_all_fox_files_by_prefix_and_keeps_original_entries(self):
        fox_files = [
            make_entry(10, "PlFx.dat"),
            make_entry(11, "PlFxGr.dat"),
            make_entry(12, "PlFxGr.usd"),
        ]
        other = make_entry(13, "PlCa.dat")
        groups = build_character_groups([*fox_files, other])

        fox = next(group for group in groups if group.code == "FX")
        self.assertEqual(fox.name, "Fox")
        self.assertEqual(fox.entries, tuple(fox_files))
        self.assertEqual([entry.path for entry in fox.entries], [
            "GTME01/P-GTME/files/PlFx.dat",
            "GTME01/P-GTME/files/PlFxGr.dat",
            "GTME01/P-GTME/files/PlFxGr.usd",
        ])

    def test_character_groups_are_human_name_sorted(self):
        groups = build_character_groups([
            make_entry(1, "PlFxGr.dat"),
            make_entry(2, "PlCa.dat"),
            make_entry(3, "PlMa.dat"),
        ])
        self.assertEqual([group.name for group in groups], [
            "Captain Falcon", "Fox", "Mario"
        ])

    def test_nana_assets_share_the_ice_climbers_group(self):
        groups = build_character_groups([
            make_entry(1, "PlNn.dat"),
            make_entry(2, "PlCl.dat"),
        ])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].name, "Ice Climbers")
        self.assertEqual([entry.name for entry in groups[0].entries], ["PlNn.dat", "PlCl.dat"])

    def test_ignores_nonfighter_and_noncharacter_files(self):
        player = make_entry(1, "Player.dat")
        unrelated = make_entry(2, "PlFx.png")
        directory = make_entry(3, "PlFxFolder", kind="directory")
        self.assertIsNone(character_code_for_entry(player))
        self.assertIsNone(character_code_for_entry(unrelated))
        self.assertIsNone(character_code_for_entry(directory))
        self.assertEqual(build_character_groups([player, unrelated, directory]), ())


if __name__ == "__main__":
    unittest.main()
