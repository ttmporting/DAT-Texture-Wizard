import struct
import unittest

from dtw_dat_probe import DatFormatError, inspect_dat


def build_minimal_dat():
    # One 4-byte payload word, one RT entry pointing at offset 0, one root
    # node naming the payload at offset 4, and a one-label ASCII string table.
    data_area = struct.pack(">I", 4) + b"DATA"
    rt_start = len(data_area)
    relocation = struct.pack(">I", 0)
    root_nodes = struct.pack(">II", 4, 0)
    strings = b"root_joint\0"
    body = data_area + relocation + root_nodes + strings
    header = struct.pack(">5I", 0x20 + len(body), rt_start, 1, 1, 0) + b"\0" * 12
    return header + body


class DatProbeTests(unittest.TestCase):
    def test_reads_minimal_valid_dat(self):
        report = inspect_dat(build_minimal_dat())
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["header"]["rt_entry_count"], 1)
        self.assertEqual(report["nodes"][0]["label"], "root_joint")

    def test_rejects_short_header(self):
        with self.assertRaises(DatFormatError):
            inspect_dat(b"\0" * 31)

    def test_reports_invalid_section_bounds(self):
        sample = bytearray(build_minimal_dat())
        struct.pack_into(">I", sample, 4, 0xFFFFFFF0)
        report = inspect_dat(bytes(sample))
        self.assertFalse(report["valid"])
        self.assertTrue(any("Section boundaries" in x for x in report["errors"]))

    def test_reports_invalid_relocation_location(self):
        sample = bytearray(build_minimal_dat())
        # RT table begins at body offset 8; point it at the RT itself.
        struct.pack_into(">I", sample, 0x20 + 8, 8)
        report = inspect_dat(bytes(sample))
        self.assertFalse(report["valid"])
        self.assertTrue(any("relocation entries" in x for x in report["errors"]))

    def test_reports_missing_node_label(self):
        sample = bytearray(build_minimal_dat())
        # String offset 1 is not the start of a string in the table.
        struct.pack_into(">I", sample, 0x20 + 12 + 4, 1)
        report = inspect_dat(bytes(sample))
        self.assertFalse(report["valid"])
        self.assertTrue(any("missing string-table" in x for x in report["errors"]))

    def test_file_size_discrepancy_is_warning(self):
        sample = bytearray(build_minimal_dat())
        struct.pack_into(">I", sample, 0, len(sample) - 1)
        report = inspect_dat(bytes(sample))
        self.assertTrue(report["valid"], report["errors"])
        self.assertTrue(any("differs from actual size" in x for x in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
