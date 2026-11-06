import struct
import unittest

from dtw_gx_texture import (
    GXTextureError,
    decode_gx_palette,
    decode_gx_pixels,
    encode_rgba_png,
    gx_image_data_length,
    png_data_uri,
    resize_rgba_nearest,
    scan_gx_textures,
)


class FakeDat:
    def __init__(self, body, pointer_locations, structure_offsets, rt_start, string_table_start):
        self.body = body
        self.pointer_locations = tuple(pointer_locations)
        self.structure_offsets = tuple(structure_offsets)
        self.rt_start = rt_start
        self.string_table_start = string_table_start
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
        self.assertEqual(gx_image_data_length(9, 9, 6), 256)
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
        self.assertTrue(report.textures[0].png_data.startswith(b"\x89PNG"))

    def test_discovers_indexed_texture_and_palette(self):
        palette_bytes = struct.pack(">16H", 0xF800, *([0] * 15))
        dat, fake = make_texture_dat(8, 8, 8, bytes([0x00]) * 32, 1, palette_bytes)
        report = scan_gx_textures(fake)
        self.assertEqual(len(report.textures), 1)
        self.assertEqual(report.textures[0].palette_color_count, 16)
        self.assertEqual(tuple(report.textures[0].rgba[:4]), (248, 0, 0, 255))


if __name__ == "__main__":
    unittest.main()
