import unittest

from dtw_stage_tree import build_stage_groups
from dtw_gamecube import FstEntry


def make_entry(index, name, kind="file"):
    return FstEntry(
        index=index, name=name, path="GTME01/Pl/" + name, kind=kind,
        parent_index=1, declared_parent_index=1,
        offset=0x1000 + index * 0x20 if kind == "file" else None,
        size=128 if kind == "file" else None, next_index=None,
    )


class StageTreeTests(unittest.TestCase):
    def test_groups_vanilla_stage_files_together(self):
        files = [make_entry(1, "GrIz.dat"), make_entry(2, "GrIz.usd")]
        groups = build_stage_groups(files)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].category, "Stages")
        self.assertEqual(groups[0].name, "Fountain of Dreams [Izumi]")
        self.assertEqual(groups[0].entries, tuple(files))

    def test_target_test_files_use_character_groups(self):
        groups = build_stage_groups([
            make_entry(1, "GrTCa.dat"),
            make_entry(2, "GrTFx.dat"),
        ])
        self.assertEqual([group.category for group in groups], ["Target Tests", "Target Tests"])
        self.assertEqual({group.name for group in groups}, {"Captain Falcon's Target Test", "Fox's Target Test"})

    def test_one_player_stages_are_separated(self):
        groups = build_stage_groups([make_entry(1, "GrEF1.dat"), make_entry(2, "GrNBa.dat")])
        goomba = next(group for group in groups if group.name == "Goomba Trophy Stage")
        battlefield = next(group for group in groups if group.name == "Battlefield")
        self.assertEqual(goomba.category, "1P Mode")
        self.assertEqual(battlefield.category, "Stages")

    def test_special_variants_remain_under_their_base_stage_folder(self):
        groups = build_stage_groups([
            make_entry(1, "GrIz.dat"),
            make_entry(2, "GrIz.gat"),
        ])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].name, "Fountain of Dreams [Izumi]")
        self.assertEqual([entry.name for entry in groups[0].entries], ["GrIz.dat", "GrIz.gat"])

    def test_stadium_variants_share_one_group(self):
        groups = build_stage_groups([make_entry(1, "GrP2.usd"), make_entry(2, "GrP3.usd")])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].name, "Pokemon Stadium")

    def test_unknown_stage_files_remain_accessible(self):
        group = build_stage_groups([make_entry(1, "GrQQ.unknown")])[0]
        self.assertEqual(group.category, "Other Stage Files")
        self.assertEqual(group.entries[0].name, "GrQQ.unknown")


if __name__ == "__main__":
    unittest.main()
