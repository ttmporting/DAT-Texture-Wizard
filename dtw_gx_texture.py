"""Read-only Nintendo GX texture discovery and PNG decoding for HSD DAT files.

Texture headers follow upstream DTW's HSD TextureObjDesc -> ImageObjDesc and
optional PaletteObjDesc relationships. The decoder is pure Python and writes
PNG bytes with the standard library; no Windows helpers or Pillow are needed.
"""
from __future__ import annotations

import base64
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


GX_FORMAT_NAMES = {
    0: "I4",
    1: "I8",
    2: "IA4",
    3: "IA8",
    4: "RGB565",
    5: "RGB5A3",
    6: "RGBA8",
    8: "CI4",
    9: "CI8",
    10: "CI14x2",
    14: "CMPR",
}
GX_BLOCKS = {
    0: (8, 8, 32),
    1: (8, 4, 32),
    2: (8, 4, 32),
    3: (4, 4, 32),
    4: (4, 4, 32),
    5: (4, 4, 32),
    6: (4, 4, 64),
    8: (8, 8, 32),
    9: (8, 4, 32),
    10: (4, 4, 32),
    14: (8, 8, 32),
}


class GXTextureError(ValueError):
    """A GX image or palette is malformed or unsupported."""


@dataclass(frozen=True)
class TexturePreview:
    """One decoded image plus the HSD locations that identify its source."""

    index: int
    name: str
    width: int
    height: int
    image_type: int
    image_format: str
    texture_offset: int
    image_header_offset: int
    image_data_offset: int
    image_data_length: int
    palette_header_offset: int | None
    palette_data_offset: int | None
    palette_type: int | None
    palette_color_count: int
    rgba: bytes
    png_data: bytes


@dataclass(frozen=True)
class TextureScanReport:
    textures: tuple[TexturePreview, ...]
    warnings: tuple[str, ...]


def gx_image_data_length(width: int, height: int, image_type: int) -> int:
    """Return the padded GX image size (including complete edge blocks)."""
    if image_type not in GX_BLOCKS:
        raise GXTextureError("Unsupported GX image type {}.".format(image_type))
    if not (1 <= width <= 1024 and 1 <= height <= 1024):
        raise GXTextureError("Invalid GX image dimensions {}x{}.".format(width, height))
    block_width, block_height, block_bytes = GX_BLOCKS[image_type]
    blocks_x = (width + block_width - 1) // block_width
    blocks_y = (height + block_height - 1) // block_height
    return blocks_x * blocks_y * block_bytes


def _decode_rgb565(value: int) -> tuple[int, int, int, int]:
    return (
        ((value >> 11) & 0x1F) * 8,
        ((value >> 5) & 0x3F) * 4,
        (value & 0x1F) * 8,
        255,
    )


def _decode_rgb5a3(value: int) -> tuple[int, int, int, int]:
    if value & 0x8000:
        return (
            ((value >> 10) & 0x1F) * 8,
            ((value >> 5) & 0x1F) * 8,
            (value & 0x1F) * 8,
            255,
        )
    return (
        ((value >> 8) & 0x0F) * 17,
        ((value >> 4) & 0x0F) * 17,
        (value & 0x0F) * 17,
        ((value >> 12) & 0x07) * 32,
    )


def decode_gx_palette(encoded: bytes, palette_type: int, color_count: int) -> tuple[tuple[int, int, int, int], ...]:
    """Decode a GX TLUT using IA8, RGB565, or RGB5A3 encoding."""
    if palette_type not in (0, 1, 2):
        raise GXTextureError("Unsupported GX palette type {}.".format(palette_type))
    if not (1 <= color_count <= 16384):
        raise GXTextureError("Invalid GX palette color count {}.".format(color_count))
    if len(encoded) < color_count * 2:
        raise GXTextureError("Palette data is shorter than its declared color count.")
    colors = []
    for (value,) in struct.iter_unpack(">H", encoded[:color_count * 2]):
        if palette_type == 0:  # IA8: AAAAAAAAIIIIIIII
            intensity = value & 0xFF
            color = (intensity, intensity, intensity, value >> 8)
        elif palette_type == 1:
            color = _decode_rgb565(value)
        else:
            color = _decode_rgb5a3(value)
        colors.append(color)
    return tuple(colors)


def decode_gx_pixels(
    encoded: bytes,
    width: int,
    height: int,
    image_type: int,
    palette: Iterable[tuple[int, int, int, int]] | None = None,
) -> bytes:
    """Decode a tiled GameCube GX image into tightly packed row-major RGBA."""
    required = gx_image_data_length(width, height, image_type)
    if len(encoded) < required:
        raise GXTextureError(
            "Image data is truncated: expected {:,} bytes, found {:,}.".format(required, len(encoded))
        )
    colors = tuple(palette or ())
    if image_type in (8, 9, 10) and not colors:
        raise GXTextureError("Indexed GX image type {} has no decoded palette.".format(image_type))

    block_width, block_height, block_bytes = GX_BLOCKS[image_type]
    pixels = bytearray(width * height * 4)

    def put_pixel(x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        if x < width and y < height:
            position = (y * width + x) * 4
            pixels[position:position + 4] = bytes(rgba)

    position = 0
    if image_type == 14:
        # CMPR is an 8x8 macroblock composed of four 4x4 DXT1-like subblocks.
        for block_y in range(0, height, 8):
            for block_x in range(0, width, 8):
                for sub_y in (0, 4):
                    for sub_x in (0, 4):
                        c0, c1 = struct.unpack_from(">HH", encoded, position)
                        index_rows = encoded[position + 4:position + 8]
                        position += 8
                        color0, color1 = _decode_rgb565(c0), _decode_rgb565(c1)
                        if c0 > c1:
                            color2 = tuple(
                                int(round((2 * color0[i] + color1[i]) / 3.0))
                                for i in range(3)
                            ) + (255,)
                            color3 = tuple(
                                int(round((color0[i] + 2 * color1[i]) / 3.0))
                                for i in range(3)
                            ) + (255,)
                        else:
                            color2 = tuple(
                                int(round((color0[i] + color1[i]) / 2.0))
                                for i in range(3)
                            ) + (255,)
                            color3 = (0, 0, 0, 0)
                        sub_palette = (color0, color1, color2, color3)
                        for row, index_byte in enumerate(index_rows):
                            y = block_y + sub_y + row
                            for column in range(4):
                                x = block_x + sub_x + column
                                color_index = (index_byte >> (6 - 2 * column)) & 0x03
                                put_pixel(x, y, sub_palette[color_index])
        return bytes(pixels)

    for block_y in range(0, height, block_height):
        for block_x in range(0, width, block_width):
            block = encoded[position:position + block_bytes]
            position += block_bytes
            pixel_count = block_width * block_height

            if image_type == 6:
                # RGBA8 blocks store 16 A/R halfwords, then 16 G/B halfwords.
                for i in range(pixel_count):
                    ar = struct.unpack_from(">H", block, i * 2)[0]
                    gb = struct.unpack_from(">H", block, 32 + i * 2)[0]
                    rgba = (ar & 0xFF, gb >> 8, gb & 0xFF, ar >> 8)
                    put_pixel(block_x + i % block_width, block_y + i // block_width, rgba)
                continue

            for i in range(pixel_count):
                x = block_x + i % block_width
                y = block_y + i // block_width
                if image_type in (0, 8):
                    value = block[i // 2]
                    index = (value >> 4) & 0x0F if i % 2 == 0 else value & 0x0F
                    if image_type == 0:
                        intensity = index * 17
                        rgba = (intensity, intensity, intensity, 255)
                    else:
                        if index >= len(colors):
                            raise GXTextureError("CI4 texture references missing palette entry {}.".format(index))
                        rgba = colors[index]
                elif image_type in (1, 2, 9):
                    value = block[i]
                    if image_type == 1:
                        rgba = (value, value, value, 255)
                    elif image_type == 2:
                        intensity = (value & 0x0F) * 17
                        alpha = (value >> 4) * 17
                        rgba = (intensity, intensity, intensity, alpha)
                    else:
                        if value >= len(colors):
                            raise GXTextureError("CI8 texture references missing palette entry {}.".format(value))
                        rgba = colors[value]
                else:
                    value = struct.unpack_from(">H", block, i * 2)[0]
                    if image_type == 3:  # IA8: AAAAAAAAIIIIIIII
                        intensity = value & 0xFF
                        rgba = (intensity, intensity, intensity, value >> 8)
                    elif image_type == 4:
                        rgba = _decode_rgb565(value)
                    elif image_type == 5:
                        rgba = _decode_rgb5a3(value)
                    elif image_type == 10:
                        palette_index = value & 0x3FFF
                        if palette_index >= len(colors):
                            raise GXTextureError(
                                "CI14x2 texture references missing palette entry {}.".format(palette_index)
                            )
                        rgba = colors[palette_index]
                    else:
                        raise GXTextureError("Unsupported GX image type {}.".format(image_type))
                put_pixel(x, y, rgba)

    return bytes(pixels)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def encode_rgba_png(width: int, height: int, rgba: bytes) -> bytes:
    """Encode an RGBA buffer as a standards-compliant PNG using stdlib only."""
    if width < 1 or height < 1 or len(rgba) != width * height * 4:
        raise ValueError("RGBA buffer size does not match the image dimensions.")
    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(raw, 6)) + _png_chunk(b"IEND", b"")


def resize_rgba_nearest(
    rgba: bytes, width: int, height: int, max_width: int, max_height: int
) -> tuple[int, int, bytes]:
    """Create a bounded nearest-neighbor preview without a third-party imaging library."""
    scale = min(1.0, max_width / width, max_height / height)
    out_width = max(1, int(round(width * scale)))
    out_height = max(1, int(round(height * scale)))
    if (out_width, out_height) == (width, height):
        return width, height, rgba
    out = bytearray(out_width * out_height * 4)
    for y in range(out_height):
        source_y = min(height - 1, int(y * height / out_height))
        for x in range(out_width):
            source_x = min(width - 1, int(x * width / out_width))
            source = (source_y * width + source_x) * 4
            target = (y * out_width + x) * 4
            out[target:target + 4] = rgba[source:source + 4]
    return out_width, out_height, bytes(out)


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise GXTextureError("Structure pointer lies outside the DAT.")
    return struct.unpack_from(">I", data, offset)[0]


def _read_c_string(data: bytes, offset: int, limit: int = 96) -> str:
    if offset <= 0 or offset >= len(data):
        return ""
    end = data.find(b"\x00", offset, min(len(data), offset + limit))
    if end < 0:
        end = min(len(data), offset + limit)
    try:
        return data[offset:end].decode("ascii", errors="replace").strip()
    except UnicodeDecodeError:
        return ""


def _metadata_end(model) -> int:
    labels = [
        node.get("label", "")
        for node in (list(model.root_nodes) + list(model.reference_nodes))
        if node.get("label")
    ]
    return min(
        len(model.body),
        model.string_table_start + sum(len(label.encode("ascii", errors="replace")) + 1 for label in labels),
    )


def _payload_in_bounds(offset: int, length: int, body_length: int, rt_start: int, metadata_end: int) -> bool:
    if offset <= 0 or length <= 0 or offset + length > body_length:
        return False
    if offset < rt_start and offset + length > rt_start:
        return False
    if rt_start <= offset < metadata_end:
        return False
    return True


def scan_gx_textures(model) -> TextureScanReport:
    """Find valid TextureObjDesc -> ImageObjDesc records and decode their PNGs.

    The scan requires relocation-table evidence at the relevant pointer fields,
    validates dimensions/formats/buffer bounds, and safely skips malformed or
    unsupported candidates. Data remains read-only.
    """
    body = bytes(model.body)
    pointers = set(model.pointer_locations)
    structure_offsets = set(model.structure_offsets)
    metadata_end = _metadata_end(model)
    warnings: list[str] = []
    previews: list[TexturePreview] = []
    candidates = sorted({
        location - 0x4C
        for location in pointers
        if location >= 0x4C and location - 0x4C in structure_offsets
    })
    seen_offsets: set[int] = set()

    for texture_offset in candidates:
        if texture_offset in seen_offsets or texture_offset + 0x5C > model.rt_start:
            continue
        seen_offsets.add(texture_offset)
        image_pointer_location = texture_offset + 0x4C
        try:
            image_header_offset = _u32(body, image_pointer_location)
            if image_header_offset == 0 or image_header_offset not in structure_offsets:
                continue
            if image_header_offset + 0x18 > model.rt_start:
                continue
            if image_header_offset not in pointers:
                continue
            image_data_offset, width, height, image_type, mipmap_flag, min_lod, max_lod = struct.unpack_from(
                ">IHHIIff", body, image_header_offset
            )
            if (
                mipmap_flag > 1 or not math.isfinite(min_lod) or not math.isfinite(max_lod)
                or min_lod > 10 or max_lod > 10 or min_lod > max_lod
            ):
                continue
            data_length = gx_image_data_length(width, height, image_type)
            if image_header_offset not in pointers:
                continue
            if not _payload_in_bounds(image_data_offset, data_length, len(body), model.rt_start, metadata_end):
                continue
            image_bytes = body[image_data_offset:image_data_offset + data_length]

            palette_header_offset = None
            palette_data_offset = None
            palette_type = None
            palette_color_count = 0
            palette = None
            palette_pointer_location = texture_offset + 0x50
            if palette_pointer_location in pointers:
                candidate_palette_header = _u32(body, palette_pointer_location)
                if candidate_palette_header:
                    if candidate_palette_header + 0x0E > model.rt_start or candidate_palette_header not in structure_offsets:
                        raise GXTextureError("Palette header pointer is invalid.")
                    if candidate_palette_header not in pointers:
                        raise GXTextureError("Palette header data pointer is not relocatable.")
                    palette_data_offset, palette_type, _palette_name, palette_color_count = struct.unpack_from(
                        ">IIIH", body, candidate_palette_header
                    )
                    palette_byte_length = palette_color_count * 2
                    if not _payload_in_bounds(
                        palette_data_offset, palette_byte_length, len(body), model.rt_start, metadata_end
                    ):
                        raise GXTextureError("Palette data lies outside a valid DAT data range.")
                    palette = decode_gx_palette(
                        body[palette_data_offset:palette_data_offset + palette_byte_length],
                        palette_type, palette_color_count,
                    )
                    palette_header_offset = candidate_palette_header

            if image_type in (8, 9, 10) and palette is None:
                raise GXTextureError("Indexed image is missing its palette header.")

            rgba = decode_gx_pixels(image_bytes, width, height, image_type, palette)
            png_data = encode_rgba_png(width, height, rgba)
            name_pointer_location = texture_offset
            texture_name = ""
            if name_pointer_location in pointers:
                texture_name = _read_c_string(body, _u32(body, name_pointer_location))
            if not texture_name:
                texture_name = "Texture {:02d}".format(len(previews) + 1)

            previews.append(TexturePreview(
                index=len(previews) + 1,
                name=texture_name,
                width=width,
                height=height,
                image_type=image_type,
                image_format=GX_FORMAT_NAMES[image_type],
                texture_offset=texture_offset,
                image_header_offset=image_header_offset,
                image_data_offset=image_data_offset,
                image_data_length=data_length,
                palette_header_offset=palette_header_offset,
                palette_data_offset=palette_data_offset,
                palette_type=palette_type,
                palette_color_count=palette_color_count,
                rgba=rgba,
                png_data=png_data,
            ))
        except (GXTextureError, struct.error, ValueError) as exc:
            warnings.append("Texture candidate at 0x{:X} skipped: {}".format(texture_offset, exc))

    if not previews and not warnings:
        warnings.append(
            "No valid GX texture headers were found. This DAT may not contain image textures, "
            "or its HSD texture layout may need an additional class hint."
        )
    return TextureScanReport(tuple(previews), tuple(warnings))


def png_data_uri(png_data: bytes) -> str:
    """Return base64 data suitable for Tk PhotoImage(data=...)."""
    return base64.b64encode(png_data).decode("ascii")
