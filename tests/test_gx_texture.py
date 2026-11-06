import struct
import tempfile
import unittest
from pathlib import Path

from dtw_dat_tree import DatTreeModel

from dtw_gx_texture import (
    GXTextureError,
    decode_gx_palette,
    decode_gx_pixels,
    decode_png_rgba,
    encode_gx_pixels,
    encode_rgba_png,
    gx_image_data_length,
    png_data_uri,
    resize_rgba_nearest,
    replace_texture_in_dat,
    scan_gx_textures,
)


class FakeDat:
    def __init__(self, body, pointer_locations, structure_offsets, rt_start, string_table_start):
        self.body = body
        self.pointer_locations = tuple(pointer_locations)
        self.structure_offsets = tuple(structure_offsets)
        self.rt_start = rt_start
        self.string_table_start = string_table_start
        self.file_name = "texture-fixture.dat"
        self.root_nodes = [{"label": "Root"}]
        self.reference_nodes = []


def make_texture_dat(image_type=0, width=8, height=8, image_bytes=None, palette_type=None, palette_bytes=b""):
    body = bytearray(0x1A1)
    texture_offset = 0x40
    image_header_offset = 0xA0
    palette_header_offset = 0xC0
    image_data_offset = 0x100
    palette_data_offset = 0x140
    image_length = gx_image_data_length(width, height, image_type)
    if image_bytes is None:
        image_bytes = bytes(image_length)
    body[image_data_offset:image_data_offset + len(image_bytes)] = image_bytes
    pointer_locations = [0x1C, texture_offset + 0x4C, image_header_offset]
    pointer_values = [texture_offset, image_header_offset, image_data_offset]
    if palette_type is not None:
        body[palette_data_offset:palette_data_offset + len(palette_bytes)] = palette_bytes
        struct.pack_into(">IIIH", body, palette_header_offset, palette_data_offset, palette_type, 0, len(palette_bytes) // 2)
        pointer_locations.extend([texture_offset + 0x50, palette_header_offset])
        pointer_values.extend([palette_header_offset, palette_data_offset])
    struct.pack_into(">I", body, 0x1C, texture_offset)
    struct.pack_into(">I", body, texture_offset + 0x4C, image_header_offset)
    if palette_type is not None:
        struct.pack_into(">I", body, texture_offset + 0x50, palette_header_offset)
    struct.pack_into(">IHHIIff", body, image_header_offset, image_data_offset, width, height, image_type, 0, 0.0, 0.0)
    rt_start = 0x180
    rt_end = rt_start + len(pointer_locations) * 4
    node_offset = rt_end
    string_offset = node_offset + 8
    body[string_offset:string_offset + 5] = b"Root\0"
    for i, location in enumerate(pointer_locations):
        struct.pack_into(">I", body, rt_start + i * 4, location)
    struct.pack_into(">II", body, node_offset, 0x10, 0)
    header = struct.pack(">5I", 0x20 + len(body), rt_start, len(pointer_locations), 1, 0)
    header += bytes.fromhex("C2339F3D") + b"\0" * 8
    dat = header + bytes(body)
    structure_offsets = sorted({0x10, *pointer_values, rt_start, rt_end, string_offset})
    return dat, FakeDat(bytes(body), pointer_locations, structure_offsets, rt_start, string_offset)


class GXTextureDecoderTests(unittest.TestCase):
    def test_gx_block_sizes_include_padding(self):
        self.assertEqual(gx_image_data_length(1, 1, 0), 32)
        # RGBA8 uses 4x4 / 64-byte blocks; 9x9 pads to 3x3 blocks.
        self.assertEqual(gx_image_data_length(9, 9, 6), 576)
        self.assertEqual(gx_image_data_length(8, 8, 14), 32)

    def test_decodes_i4_nibble_order(self):
        rgba = decode_gx_pixels(bytes([0xF0]) + bytes(31), 8, 8, 0)
        self.assertEqual(tuple(rgba[:4]), (255, 255, 255, 255))
        self.assertEqual(tuple(rgba[4:8]), (0, 0, 0, 255))

    def test_decodes_rgb565_red(self):
        rgba = decode_gx_pixels(struct.pack(">H", 0xF800) * 16, 4, 4, 4)
        self.assertEqual(tuple(rgba[:4]), (248, 0, 0, 255))

    def test_decodes_ia8_alpha_and_intensity(self):
        rgba = decode_gx_pixels(struct.pack(">H", 0x8040) * 16, 4, 4, 3)
        self.assertEqual(tuple(rgba[:4]), (64, 64, 64, 128))

    def test_decodes_rgb5a3_transparency(self):
        rgba = decode_gx_pixels(struct.pack(">H", 0x0F00) * 16, 4, 4, 5)
        self.assertEqual(tuple(rgba[:4]), (255, 0, 0, 0))

    def test_decodes_rgba8_split_ar_gb_planes(self):
        block = bytearray(64)
        for i in range(16):
            struct.pack_into(">H", block, i * 2, 0xFF12)
            struct.pack_into(">H", block, 32 + i * 2, 0x3456)
        rgba = decode_gx_pixels(bytes(block), 4, 4, 6)
        self.assertEqual(tuple(rgba[:4]), (0x12, 0x34, 0x56, 0xFF))

    def test_decodes_ci4_palette(self):
        palette = decode_gx_palette(struct.pack(">16H", 0xF800, *([0] * 15)), 1, 16)
        rgba = decode_gx_pixels(bytes([0x00]) * 32, 8, 8, 8, palette)
        self.assertEqual(tuple(rgba[:4]), (248, 0, 0, 255))

    def test_decodes_cmpr_transparent_index(self):
        # c0 == c1 selects the transparent fourth entry in CMPR's DXT1-style mode.
        block = struct.pack(">HH", 0xFFFF, 0xFFFF) + bytes([0xFF] * 4)
        rgba = decode_gx_pixels(block * 4, 8, 8, 14)
        self.assertEqual(tuple(rgba[:4]), (0, 0, 0, 0))

    def test_png_encoder_and_thumbnail_resize(self):
        rgba = bytes([255, 0, 0, 255] * 4)
        png = encode_rgba_png(2, 2, rgba)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(png_data_uri(png))
        width, height, thumb = resize_rgba_nearest(rgba, 2, 2, 1, 1)
        self.assertEqual((width, height), (1, 1))
        self.assertEqual(thumb, bytes([255, 0, 0, 255]))

    def test_rejects_short_image_buffers(self):
        with self.assertRaises(GXTextureError):
            decode_gx_pixels(b"\0", 8, 8, 0)

    def test_discovers_texture_object_and_image_header(self):
        dat, fake = make_texture_dat()
        report = scan_gx_textures(fake)
        self.assertEqual(len(report.textures), 1)
        self.assertEqual(report.textures[0].width, 8)
        self.assertEqual(report.textures[0].height, 8)
        self.assertEqual(report.textures[0].image_format, "I4")
        self.assertEqual(report.textures[0].image_data_offset, 0x100)
        self.assertEqual(report.textures[0].name, "texture-fixture_0x120_0")
        self.assertTrue(report.textures[0].png_data.startswith(bytes.fromhex("89504e470d0a1a0a")))

    def test_scans_a_real_dat_tree_model_not_only_a_mock(self):
        dat, _fake = make_texture_dat()
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "texture-fixture.dat"
            path.write_bytes(dat)
            model = DatTreeModel(path)
            report = scan_gx_textures(model)
        self.assertEqual(len(report.textures), 1)
        self.assertEqual(report.textures[0].image_format, "I4")
        self.assertEqual(report.textures[0].name, "texture-fixture_0x120_0")

    def test_png_reader_decodes_rgba_and_rgb(self):
        source = bytes([10, 20, 30, 40, 50, 60, 70, 80])
        png = encode_rgba_png(2, 1, source)
        width, height, rgba = decode_png_rgba(png)
        self.assertEqual((width, height), (2, 1))
        self.assertEqual(rgba, source)

    def test_encodes_and_decodes_supported_unpaletted_formats(self):
        rgba = bytes([255, 0, 0, 255] * 64)
        for image_type in (0, 1, 2, 3, 4, 5, 6, 14):
            with self.subTest(image_type=image_type):
                encoded, palette = encode_gx_pixels(rgba, 8, 8, image_type)
                self.assertEqual(len(encoded), gx_image_data_length(8, 8, image_type))
                self.assertEqual(palette, b"")
                decoded = decode_gx_pixels(encoded, 8, 8, image_type)
                self.assertEqual(len(decoded), len(rgba))
                self.assertGreater(decoded[3], 0)

    def test_encodes_ci4_palette_and_indices(self):
        rgba = bytes([255, 0, 0, 255] * 64)
        encoded, palette_bytes = encode_gx_pixels(rgba, 8, 8, 8, 1, 16)
        palette = decode_gx_palette(palette_bytes, 1, 16)
        decoded = decode_gx_pixels(encoded, 8, 8, 8, palette)
        self.assertEqual(len(encoded), 32)
        self.assertEqual(len(palette_bytes), 32)
        self.assertEqual(tuple(decoded[:4]), (248, 0, 0, 255))

    def test_replaces_unpaletted_texture_in_place_without_size_changes(self):
        dat, fake = make_texture_dat(4, 8, 8)
        texture = scan_gx_textures(fake).textures[0]
        replacement_rgba = bytes([0, 255, 0, 255] * 64)
        replacement_png = encode_rgba_png(8, 8, replacement_rgba)
        updated = replace_texture_in_dat(dat, texture, replacement_png)
        self.assertEqual(len(updated), len(dat))
        self.assertEqual(updated[:0x20], dat[:0x20])
        reparsed = DatTreeModel(Path("texture-fixture.dat"), data=updated)
        decoded = scan_gx_textures(reparsed).textures[0]
        self.assertEqual(tuple(decoded.rgba[:4]), (0, 252, 0, 255))

    def test_replaces_indexed_texture_and_palette_in_place(self):
        palette_bytes = struct.pack(">16H", 0xF800, *([0] * 15))
        dat, fake = make_texture_dat(8, 8, 8, bytes([0x00]) * 32, 1, palette_bytes)
        texture = scan_gx_textures(fake).textures[0]
        replacement_rgba = bytes([0, 0, 255, 255] * 64)
        replacement_png = encode_rgba_png(8, 8, replacement_rgba)
        updated = replace_texture_in_dat(dat, texture, replacement_png)
        reparsed = DatTreeModel(Path("texture-fixture.dat"), data=updated)
        decoded = scan_gx_textures(reparsed).textures[0]
        self.assertEqual(tuple(decoded.rgba[:4]), (0, 0, 248, 255))
        self.assertEqual(len(updated), len(dat))

    def test_refuses_texture_import_with_different_dimensions(self):
        dat, fake = make_texture_dat()
        texture = scan_gx_textures(fake).textures[0]
        replacement_png = encode_rgba_png(4, 4, bytes([0, 255, 0, 255] * 16))
        with self.assertRaisesRegex(ValueError, "requires exactly 8×8"):
            replace_texture_in_dat(dat, texture, replacement_png)

    def test_discovers_indexed_texture_and_palette(self):
        palette_bytes = struct.pack(">16H", 0xF800, *([0] * 15))
        dat, fake = make_texture_dat(8, 8, 8, bytes([0x00]) * 32, 1, palette_bytes)
        report = scan_gx_textures(fake)
        self.assertEqual(len(report.textures), 1)
        self.assertEqual(report.textures[0].palette_color_count, 16)
        self.assertEqual(tuple(report.textures[0].rgba[:4]), (248, 0, 0, 255))


if __name__ == "__main__":
    unittest.main()
