import unittest

from dtw_disc_labels import character_description, disc_file_description, stage_description


class DiscLabelTests(unittest.TestCase):
    def test_fox_green_costume_matches_original_dtw_description(self):
        self.assertEqual(character_description("PlFxGr.dat"), "Fox's green costume")
        self.assertEqual(disc_file_description("PlFxGr.dat"), "Fox's green costume")

    def test_character_shared_animation_and_copy_power_descriptions(self):
        self.assertEqual(character_description("PlFx.dat"), "Fox's NTSC data & shared textures")
        self.assertEqual(character_description("PlFxAJ.dat"), "Fox's animation data")
        self.assertEqual(character_description("PlKbCpFx.dat"), "Kirby's copy power (Fox)")

    def test_pal_and_usd_notes(self):
        self.assertEqual(character_description("PlFx.p"), "Fox's PAL data & shared textures")
        self.assertEqual(character_description("PlFxGr.usd"), "Fox's green costume (English)")

    def test_stage_and_target_test_names(self):
        self.assertEqual(stage_description("GrIz.dat"), "Fountain of Dreams [Izumi]")
        self.assertEqual(stage_description("GrTCa.dat"), "Captain Falcon's Target Test stage")
        self.assertEqual(stage_description("GrEF1.dat"), "Goomba Trophy Stage")

    def test_special_stage_variants(self):
        self.assertEqual(stage_description("GrIz.gat"), "Cave of Dreams")
        self.assertEqual(stage_description("GrNBa.2at"), "Ancient Battlefield")

    def test_misc_file_descriptions(self):
        self.assertEqual(disc_file_description("MnSlChr.dat"), "Character Select Screen")
        self.assertEqual(disc_file_description("EfFxData.dat"), "Fox & Falco graphical effects")
        self.assertEqual(disc_file_description("PlCo.dat"), "Textures common to the cast")


if __name__ == "__main__":
    unittest.main()
