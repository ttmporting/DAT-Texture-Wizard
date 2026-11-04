import struct
import tempfile
import unittest
from pathlib import Path

from dtw_dat_tree import DatTreeModel


def make_small_fox_dat() -> bytes:
    """Make a tiny synthetic Fox-like DAT with two child pointers."""
    rt_start = 0x70
    rt_locations = (0x10, 0x18)
    root_label = b"PlyFox5KGr_Share_joint\0"
    body = bytearray(0x80 + len(root_label))
    # Root JointObjDesc at data offset 0x08: child pointer at +8, display ptr at +16.
    struct.pack_into(">I", body, 0x10, 0x50)
    struct.pack_into(">I", body, 0x18, 0x60)
    # Relocation table and one root node table entry.
    struct.pack_into(">2I", body, rt_start, *rt_locations)
    struct.pack_into(">2I", body, rt_start + 8, 0x08, 0)
    body[0x80:0x80 + len(root_label)] = root_label
    file_size = 0x20 + len(body)
    header = struct.pack(">5I", file_size, rt_start, len(rt_locations), 1, 0) + b"\0\0\0\0" + b"\0" * 8
    return header + body


class DatTreeModelTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "PlFxGr.dat"
        self.path.write_bytes(make_small_fox_dat())
        self.model = DatTreeModel(self.path)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_file_header_sections_follow_original_tree_order(self):
        records = self.model.root_tree_records()
        self.assertEqual([r.kind for r in records], ["file_header", "relocation_table", "root_table", "string_table"])
        self.assertEqual(records[0].iid, "file-header")

    def test_root_node_maps_to_known_hsd_class(self):
        root = self.model.table_children("root_table")[0]
        self.assertEqual(root.text, "PlyFox5KGr_Share_joint")
        self.assertEqual(root.type_hint, "JointObjDesc")
        self.assertEqual(root.offset, 0x08)

    def test_pointer_fields_are_reported_with_offsets(self):
        details = self.model.record_pointer_details(0x08, "JointObjDesc")
        self.assertEqual([row["field"] for row in details], ["Child Pointer", "Display Object Pointer"])
        self.assertEqual([row["target"] for row in details], [0x50, 0x60])
        self.assertEqual([row["relative_offset"] for row in details], [8, 16])

    def test_direct_children_exclude_nulls_and_known_next_sibling_fields(self):
        children = self.model.direct_children(0x08, "JointObjDesc")
        self.assertEqual([(p.target, p.child_type) for p in children], [(0x50, "JointObjDesc"), (0x60, "DisplayObjDesc")])

    def test_inspector_offsets_include_dat_header_bias(self):
        self.assertEqual(self.model.absolute_offset(0x50), 0x70)
        self.assertEqual(self.model.structure_length(0x08, "JointObjDesc"), 0x40)


if __name__ == "__main__":
    unittest.main()
