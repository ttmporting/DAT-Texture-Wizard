import struct
import tempfile
import unittest
from pathlib import Path

from dtw_gamecube import GameCubeIso, GameCubeFormatError, ReplacementError


def make_test_iso(path: Path) -> bytes:
    header = bytearray(0x440)
    header[:6] = b"GTME01"
    header[0x1C:0x20] = bytes.fromhex("C2339F3D")
    dol_offset = 0x600
    fst_offset = 0x800
    file_offsets = {
        "opening.bnr": 0xA00,
        "PlFxGr.dat": 0xB00,
    }
    names = bytearray(b"\0")

    def add_name(name):
        offset = len(names)
        names.extend(name.encode("ascii") + b"\0")
        return offset

    opening_name = add_name("opening.bnr")
    game_dir_name = add_name("P-GTME")
    files_dir_name = add_name("files")
    dat_name = add_name("PlFxGr.dat")

    entries = bytearray()
    # Root: first byte nonzero; second word is parent index; third is exclusive end index.
    entries.extend(struct.pack(">III", 0x01000000, 0, 5))
    entries.extend(struct.pack(">III", opening_name, file_offsets["opening.bnr"], 5))
    entries.extend(struct.pack(">III", 0x01000000 | game_dir_name, 0, 5))
    # Deliberately bad declared parent=1 (opening.bnr is a file). Nesting says parent=2.
    entries.extend(struct.pack(">III", 0x01000000 | files_dir_name, 1, 5))
    entries.extend(struct.pack(">III", dat_name, file_offsets["PlFxGr.dat"], 8))
    fst = bytes(entries + names)
    struct.pack_into(">4I", header, 0x420, dol_offset, fst_offset, len(fst), len(fst))

    image = bytearray(0xE00)
    image[:len(header)] = header
    dol_header = bytearray(0x100)
    struct.pack_into(">I", dol_header, 0x00, 0x100)  # first text section starts after DOL header
    struct.pack_into(">I", dol_header, 0x90, 4)      # four-byte text section
    image[dol_offset:dol_offset + 0x100] = dol_header
    image[dol_offset + 0x100:dol_offset + 0x104] = b"DOL!"
    image[file_offsets["opening.bnr"]:file_offsets["opening.bnr"] + 5] = b"BNR00"
    image[file_offsets["PlFxGr.dat"]:file_offsets["PlFxGr.dat"] + 8] = b"ORIGDAT!"
    image[fst_offset:fst_offset + len(fst)] = fst
    path.write_bytes(image)
    return bytes(image)


class GameCubeIsoTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.folder = Path(self.tempdir.name)
        self.iso_path = self.folder / "test-melee.iso"
        self.original = make_test_iso(self.iso_path)
        self.iso = GameCubeIso(self.iso_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_parses_header_and_builds_preorder_paths(self):
        self.assertEqual(self.iso.game_id, "GTME01")
        self.assertTrue(self.iso.is_melee)
        self.assertEqual(self.iso.file_count, 2)
        self.assertEqual(self.iso.directory_count, 2)
        file_entry = self.iso.get_entry(4)
        self.assertEqual(file_entry.path, "GTME01/P-GTME/files/PlFxGr.dat")
        self.assertEqual(file_entry.parent_index, 3)

    def test_tolerates_wrong_declared_directory_parent_using_preorder_range(self):
        self.assertEqual(self.iso.parent_mismatches, [(3, 1, 2)])
        self.assertTrue(self.iso.warnings)

    def test_reads_selected_file_data(self):
        self.assertEqual(self.iso.read_file(4), b"ORIGDAT!")

    def test_stages_replacement_when_it_fits_safe_allocation(self):
        replacement = self.folder / "new-PlFxGr.dat"
        replacement.write_bytes(b"CUSTOM-SKIN-DAT")
        info = self.iso.stage_replacement(4, replacement)
        self.assertEqual(info["new_size"], 15)
        self.assertEqual(info["old_size"], 8)
        self.assertGreaterEqual(info["capacity"], 15)

    def test_rejects_replacement_that_would_overlap_next_file(self):
        replacement = self.folder / "too-large.bnr"
        replacement.write_bytes(b"X" * 0x101)
        with self.assertRaises(ReplacementError):
            self.iso.stage_replacement(1, replacement)

    def test_saves_new_iso_copy_and_updates_fst_size(self):
        replacement = self.folder / "new-PlFxGr.dat"
        replacement.write_bytes(b"CUSTOM-SKIN-DAT")
        destination = self.folder / "patched.iso"
        result = self.iso.save_patched_copy(destination, {4: replacement})
        self.assertEqual(result["game_id"], "GTME01")
        self.assertEqual(result["replacements"]["GTME01/P-GTME/files/PlFxGr.dat"]["size"], 15)
        patched = GameCubeIso(destination)
        self.assertEqual(patched.get_entry(4).size, 15)
        self.assertEqual(patched.read_file(4), b"CUSTOM-SKIN-DAT")
        self.assertEqual(self.iso_path.read_bytes(), self.original)

    def test_refuses_to_overwrite_the_source_image(self):
        replacement = self.folder / "new-PlFxGr.dat"
        replacement.write_bytes(b"X")
        with self.assertRaises(ReplacementError):
            self.iso.save_patched_copy(self.iso_path, {4: replacement}, overwrite=True)


    def test_rebuilds_disc_for_replacement_larger_than_original_allocation(self):
        replacement = self.folder / "larger-PlFxGr.dat"
        replacement_data = bytes((index * 17) % 256 for index in range(0x800))
        replacement.write_bytes(replacement_data)
        info = self.iso.stage_replacement_for_rebuild(4, replacement)
        self.assertGreater(info["new_size"], info["capacity"])
        destination = self.folder / "rebuilt.iso"
        result = self.iso.rebuild_patched_copy(destination, {4: replacement})
        self.assertEqual(result["game_id"], "GTME01")
        self.assertEqual(result["file_count"], 2)
        rebuilt = GameCubeIso(destination)
        self.assertGreater(rebuilt.fst_offset, self.iso.dol_offset)
        self.assertEqual(rebuilt.fst_offset, result["fst_offset"])
        self.assertEqual(rebuilt.fst_size, rebuilt.fst_max_size)
        self.assertEqual(rebuilt.get_entry(4).size, len(replacement_data))
        self.assertEqual(rebuilt.read_file(4), replacement_data)
        self.assertEqual(rebuilt.read_file(1), b"BNR00")
        self.assertEqual(self.iso_path.read_bytes(), self.original)

    def test_full_rebuild_relocates_unchanged_files_and_preserves_paths(self):
        replacement = self.folder / "replacement-PlFxGr.dat"
        replacement.write_bytes(b"X" * 0x500)
        destination = self.folder / "rebuilt-with-files.iso"
        result = self.iso.rebuild_patched_copy(destination, {4: replacement})
        rebuilt = GameCubeIso(destination)
        self.assertEqual(rebuilt.get_entry(1).path, "GTME01/opening.bnr")
        self.assertEqual(rebuilt.get_entry(4).path, "GTME01/P-GTME/files/PlFxGr.dat")
        self.assertEqual(rebuilt.parent_mismatches, [])
        rebuilt_bytes = destination.read_bytes()
        self.assertEqual(rebuilt_bytes[:0x424], self.original[:0x424])
        self.assertEqual(rebuilt_bytes[0x430:0x704], self.original[0x430:0x704])
        self.assertEqual(struct.unpack_from(">3I", rebuilt_bytes, 0x424),
                         (rebuilt.fst_offset, rebuilt.fst_size, rebuilt.fst_max_size))
        self.assertEqual(rebuilt.read_file(1), b"BNR00")
        self.assertEqual(rebuilt.read_file(4), b"X" * 0x500)

    def test_rejects_non_gamecube_magic(self):
        bad = self.folder / "bad.iso"
        data = bytearray(self.original)
        data[0x1C:0x20] = b"NOPE"
        bad.write_bytes(data)
        with self.assertRaises(GameCubeFormatError):
            GameCubeIso(bad)


if __name__ == "__main__":
    unittest.main()
