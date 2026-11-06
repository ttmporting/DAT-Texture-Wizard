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
    mipmap_flag: int
    image_format: str
    texture_offset: int
    image_header_offset: int
    image_data_offset: int
    image_data_length: int
    palette_header_offset: int | None
    palette_data_offset: int | None
    palette_type: int | None
    palette_color_count: int
    palette_data_length: int
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
                mipmap_flag=mipmap_flag,
                image_format=GX_FORMAT_NAMES[image_type],
                texture_offset=texture_offset,
                image_header_offset=image_header_offset,
                image_data_offset=image_data_offset,
                image_data_length=data_length,
                palette_header_offset=palette_header_offset,
                palette_data_offset=palette_data_offset,
                palette_type=palette_type,
                palette_color_count=palette_color_count,
                palette_data_length=palette_color_count * 2,
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


# ---------------------------------------------------------------------------
# PNG import and fixed-size GX re-encoding
# ---------------------------------------------------------------------------

def decode_png_rgba(png_data: bytes) -> tuple[int, int, bytes]:
    """Decode a non-interlaced, 8-bit PNG (RGB/RGBA/gray/indexed) to RGBA."""
    signature = b"\\x89PNG\\r\\n\\x1a\\n"
    if not png_data.startswith(signature):
        raise GXTextureError("Selected file is not a valid PNG.")
    position = len(signature)
    width = height = bit_depth = color_type = interlace = None
    palette_bytes = b""
    transparency = b""
    compressed = bytearray()
    saw_end = False
    while position + 12 <= len(png_data):
        length = struct.unpack_from(">I", png_data, position)[0]
        position += 4
        kind = png_data[position:position + 4]
        position += 4
        if length > len(png_data) - position - 4:
            raise GXTextureError("PNG chunk is truncated.")
        payload = png_data[position:position + length]
        position += length
        expected_crc = struct.unpack_from(">I", png_data, position)[0]
        position += 4
        actual_crc = zlib.crc32(payload, zlib.crc32(kind)) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise GXTextureError("PNG contains a chunk checksum error.")
        if kind == b"IHDR":
            if width is not None or length != 13:
                raise GXTextureError("PNG has an invalid IHDR chunk.")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if compression != 0 or filtering != 0:
                raise GXTextureError("PNG uses an unsupported compression or filter method.")
        elif kind == b"PLTE":
            palette_bytes = payload
        elif kind == b"tRNS":
            transparency = payload
        elif kind == b"IDAT":
            compressed.extend(payload)
            if len(compressed) > 64 * 1024 * 1024:
                raise GXTextureError("PNG compressed image data is too large.")
        elif kind == b"IEND":
            saw_end = True
            break
        elif kind and 65 <= kind[0] <= 90:
            # Unknown critical chunks must not be ignored.
            if kind not in (b"IHDR", b"PLTE", b"IDAT", b"IEND"):
                raise GXTextureError("PNG uses an unsupported critical chunk {}.".format(kind.decode("ascii", "replace")))
    if not saw_end or width is None or height is None:
        raise GXTextureError("PNG is missing required image chunks.")
    if not (1 <= width <= 1024 and 1 <= height <= 1024):
        raise GXTextureError("PNG dimensions must be between 1 and 1024 pixels.")
    if bit_depth != 8 or interlace != 0:
        raise GXTextureError("PNG import currently requires 8-bit, non-interlaced images.")
    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    channels = channels_by_type.get(color_type)
    if channels is None:
        raise GXTextureError("PNG color type {} is not supported.".format(color_type))
    if color_type == 3 and (not palette_bytes or len(palette_bytes) % 3):
        raise GXTextureError("Indexed PNG has no valid PLTE color table.")
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise GXTextureError("PNG image data cannot be decompressed: {}".format(exc)) from exc
    stride = width * channels
    expected_length = height * (stride + 1)
    if len(raw) != expected_length:
        raise GXTextureError(
            "PNG decoded data length is invalid (expected {}, found {}).".format(expected_length, len(raw))
        )

    decoded_rows: list[bytearray] = []
    cursor = 0

    def paeth(a: int, b: int, c: int) -> int:
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        return a if pa <= pb and pa <= pc else (b if pb <= pc else c)

    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        scanline = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        previous = decoded_rows[-1] if decoded_rows else bytearray(stride)
        if filter_type == 1:
            for i in range(stride):
                left = scanline[i - channels] if i >= channels else 0
                scanline[i] = (scanline[i] + left) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                scanline[i] = (scanline[i] + previous[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = scanline[i - channels] if i >= channels else 0
                scanline[i] = (scanline[i] + ((left + previous[i]) // 2)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = scanline[i - channels] if i >= channels else 0
                upper = previous[i]
                upper_left = previous[i - channels] if i >= channels else 0
                scanline[i] = (scanline[i] + paeth(left, upper, upper_left)) & 0xFF
        elif filter_type != 0:
            raise GXTextureError("PNG uses unknown row filter {}.".format(filter_type))
        decoded_rows.append(scanline)

    rgba = bytearray(width * height * 4)
    palette = [
        tuple(palette_bytes[i:i + 3]) + (transparency[i // 3] if i // 3 < len(transparency) else 255,)
        for i in range(0, len(palette_bytes), 3)
    ] if color_type == 3 else ()
    for y, row in enumerate(decoded_rows):
        for x in range(width):
            source = x * channels
            target = (y * width + x) * 4
            if color_type == 6:
                rgba[target:target + 4] = row[source:source + 4]
            elif color_type == 2:
                rgba[target:target + 4] = bytes((row[source], row[source + 1], row[source + 2], 255))
            elif color_type == 0:
                value = row[source]
                rgba[target:target + 4] = bytes((value, value, value, 255))
            elif color_type == 4:
                value, alpha = row[source], row[source + 1]
                rgba[target:target + 4] = bytes((value, value, value, alpha))
            else:
                index = row[source]
                if index >= len(palette):
                    raise GXTextureError("PNG pixel references missing palette entry {}.".format(index))
                rgba[target:target + 4] = bytes(palette[index])
    return width, height, bytes(rgba)


def _luminance(color: tuple[int, int, int, int]) -> int:
    return (299 * color[0] + 587 * color[1] + 114 * color[2]) // 1000


def _rgb565_pack(color: tuple[int, int, int, int]) -> int:
    red, green, blue = color[:3]
    return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)


def _encode_rgb5a3(color: tuple[int, int, int, int]) -> int:
    red, green, blue, alpha = color
    if alpha >= 224:
        return 0x8000 | ((red >> 3) << 10) | ((green >> 3) << 5) | (blue >> 3)
    return ((alpha >> 5) << 12) | ((red >> 4) << 8) | ((green >> 4) << 4) | (blue >> 4)


def _normalize_palette_color(color: tuple[int, int, int, int], palette_type: int) -> tuple[int, int, int, int]:
    if palette_type == 0:
        intensity = _luminance(color)
        return (intensity, intensity, intensity, color[3])
    if palette_type == 1:
        return (color[0], color[1], color[2], 255)
    return color


def _median_cut_palette(
    histogram: dict[tuple[int, int, int, int], int], limit: int, palette_type: int
) -> list[tuple[int, int, int, int]]:
    """Weighted median-cut reduction used only when the imported image exceeds TLUT capacity."""
    items = list(histogram.items())
    channels = (0, 1, 2, 3) if palette_type in (0, 2) else (0, 1, 2)
    boxes = [items]
    while len(boxes) < limit:
        best_index = -1
        best_score = -1
        best_channel = 0
        for box_index, box in enumerate(boxes):
            if len(box) < 2:
                continue
            ranges = [
                max(color[channel] for color, _count in box)
                - min(color[channel] for color, _count in box)
                for channel in channels
            ]
            channel_position = max(range(len(ranges)), key=lambda i: ranges[i])
            score = ranges[channel_position] * sum(count for _color, count in box)
            if score > best_score:
                best_index = box_index
                best_score = score
                best_channel = channels[channel_position]
        if best_index < 0:
            break
        box = boxes.pop(best_index)
        box.sort(key=lambda item: item[0][best_channel])
        total = sum(count for _color, count in box)
        half = (total + 1) // 2
        accumulated = 0
        split_at = 1
        for index, (_color, count) in enumerate(box[:-1], start=1):
            accumulated += count
            if accumulated >= half:
                split_at = index
                break
        boxes.insert(best_index, box[split_at:])
        boxes.insert(best_index, box[:split_at])

    result = []
    for box in boxes:
        total = sum(count for _color, count in box)
        representative = tuple(
            sum(color[channel] * count for color, count in box) // total
            for channel in range(4)
        )
        result.append(_normalize_palette_color(representative, palette_type))
    return result


def _encode_palette_color(color: tuple[int, int, int, int], palette_type: int) -> int:
    if palette_type == 0:
        return (color[3] << 8) | _luminance(color)
    if palette_type == 1:
        return _rgb565_pack(color)
    if palette_type == 2:
        return _encode_rgb5a3(color)
    raise GXTextureError("Unsupported GX palette type {}.".format(palette_type))


def encode_gx_palette(
    rgba: bytes, color_count: int, palette_type: int, max_colors: int = 512
) -> tuple[bytes, tuple[tuple[int, int, int, int], ...]]:
    """Build a same-size TLUT from PNG pixels and return its decoded colors."""
    if len(rgba) % 4 or not (1 <= color_count <= 16384):
        raise GXTextureError("Invalid palette input or color count.")
    if palette_type not in (0, 1, 2):
        raise GXTextureError("Unsupported GX palette type {}.".format(palette_type))
    histogram: dict[tuple[int, int, int, int], int] = {}
    for offset in range(0, len(rgba), 4):
        color = _normalize_palette_color(tuple(rgba[offset:offset + 4]), palette_type)
        histogram[color] = histogram.get(color, 0) + 1
    limit = min(color_count, max_colors)
    if len(histogram) <= limit:
        colors = sorted(histogram, key=lambda color: (-histogram[color], color))
    else:
        colors = _median_cut_palette(histogram, limit, palette_type)
    if not colors:
        colors = [(0, 0, 0, 255)]
    while len(colors) < color_count:
        colors.append(colors[-1])
    encoded = b"".join(struct.pack(">H", _encode_palette_color(color, palette_type)) for color in colors[:color_count])
    decoded = decode_gx_palette(encoded, palette_type, color_count)
    return encoded, decoded


def _nearest_palette_indices(
    rgba: bytes, palette: tuple[tuple[int, int, int, int], ...], palette_type: int
) -> dict[tuple[int, int, int, int], int]:
    """Map each distinct imported color once, avoiding a full palette scan per pixel."""
    histogram = set()
    for offset in range(0, len(rgba), 4):
        histogram.add(_normalize_palette_color(tuple(rgba[offset:offset + 4]), palette_type))
    lookup: dict[tuple[int, int, int, int], int] = {}
    for color in histogram:
        best_index = 0
        best_distance = None
        for index, candidate in enumerate(palette):
            dr = color[0] - candidate[0]
            dg = color[1] - candidate[1]
            db = color[2] - candidate[2]
            da = color[3] - candidate[3]
            distance = dr * dr + dg * dg + db * db + 2 * da * da
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_index = index
                if distance == 0:
                    break
        lookup[color] = best_index
    return lookup


def _pixel(rgba: bytes, width: int, height: int, x: int, y: int) -> tuple[int, int, int, int]:
    x = min(max(x, 0), width - 1)
    y = min(max(y, 0), height - 1)
    offset = (y * width + x) * 4
    return tuple(rgba[offset:offset + 4])


def _encode_cmpr_subblock(colors: list[tuple[int, int, int, int]]) -> bytes:
    transparent = any(color[3] < 128 for color in colors)
    opaque = [color for color in colors if color[3] >= 128]
    if not opaque:
        opaque = [(0, 0, 0, 255)]
    first = second = opaque[0]
    best_spread = -1
    for left_index, left in enumerate(opaque):
        for right in opaque[left_index + 1:]:
            distance = sum((left[i] - right[i]) ** 2 for i in range(3))
            if distance > best_spread:
                best_spread = distance
                first, second = left, right
    c0, c1 = _rgb565_pack(first), _rgb565_pack(second)
    if transparent:
        if c0 > c1:
            c0, c1 = c1, c0
    else:
        if c0 < c1:
            c0, c1 = c1, c0
        elif c0 == c1:
            if c0 < 0xFFFF:
                c0 += 1
            else:
                c1 -= 1
    color0, color1 = _decode_rgb565(c0), _decode_rgb565(c1)
    if c0 > c1:
        color2 = tuple((2 * color0[i] + color1[i]) // 3 for i in range(3)) + (255,)
        color3 = tuple((color0[i] + 2 * color1[i]) // 3 for i in range(3)) + (255,)
    else:
        color2 = tuple((color0[i] + color1[i]) // 2 for i in range(3)) + (255,)
        color3 = (0, 0, 0, 0)
    choices = (color0, color1, color2, color3)
    encoded = bytearray(struct.pack(">HH", c0, c1))
    for row in range(4):
        indices = 0
        for column in range(4):
            color = colors[row * 4 + column]
            if transparent and color[3] < 128:
                index = 3
            else:
                compare_count = 3 if transparent else 4
                index = min(
                    range(compare_count),
                    key=lambda candidate: sum((color[i] - choices[candidate][i]) ** 2 for i in range(3)),
                )
            indices |= index << (6 - 2 * column)
        encoded.append(indices)
    return bytes(encoded)


def encode_gx_pixels(
    rgba: bytes,
    width: int,
    height: int,
    image_type: int,
    palette_type: int | None = None,
    palette_color_count: int = 0,
) -> tuple[bytes, bytes]:
    """Encode an RGBA image into the selected GX format, preserving block size."""
    if len(rgba) != width * height * 4:
        raise GXTextureError("Imported PNG pixel data does not match its dimensions.")
    required = gx_image_data_length(width, height, image_type)
    palette_bytes = b""
    palette: tuple[tuple[int, int, int, int], ...] = ()
    index_lookup: dict[tuple[int, int, int, int], int] = {}
    if image_type in (8, 9, 10):
        max_index = {8: 16, 9: 256, 10: 16384}[image_type]
        if palette_type is None or palette_color_count < 1 or palette_color_count > max_index:
            raise GXTextureError("The selected texture's palette metadata is invalid.")
        palette_bytes, palette = encode_gx_palette(rgba, palette_color_count, palette_type)
        index_lookup = _nearest_palette_indices(rgba, palette, palette_type)

    block_width, block_height, block_bytes = GX_BLOCKS[image_type]
    encoded = bytearray()
    if image_type == 14:
        for block_y in range(0, height, 8):
            for block_x in range(0, width, 8):
                for sub_y in (0, 4):
                    for sub_x in (0, 4):
                        colors = [
                            _pixel(rgba, width, height, block_x + sub_x + x, block_y + sub_y + y)
                            for y in range(4) for x in range(4)
                        ]
                        encoded.extend(_encode_cmpr_subblock(colors))
        if len(encoded) != required:
            raise GXTextureError("CMPR encoder produced an unexpected data length.")
        return bytes(encoded), palette_bytes

    for block_y in range(0, height, block_height):
        for block_x in range(0, width, block_width):
            block = bytearray()
            if image_type == 6:
                ar_plane = bytearray()
                gb_plane = bytearray()
                for y in range(block_height):
                    for x in range(block_width):
                        red, green, blue, alpha = _pixel(rgba, width, height, block_x + x, block_y + y)
                        ar_plane.extend(struct.pack(">H", (alpha << 8) | red))
                        gb_plane.extend(struct.pack(">H", (green << 8) | blue))
                block.extend(ar_plane)
                block.extend(gb_plane)
            elif image_type in (0, 8):
                for y in range(block_height):
                    for x in range(0, block_width, 2):
                        colors = [
                            _pixel(rgba, width, height, block_x + x + delta, block_y + y)
                            for delta in (0, 1)
                        ]
                        values = []
                        for color in colors:
                            if image_type == 0:
                                values.append((_luminance(color) + 8) // 17)
                            else:
                                values.append(index_lookup[_normalize_palette_color(color, palette_type)])
                        block.append(((values[0] & 0x0F) << 4) | (values[1] & 0x0F))
            elif image_type in (1, 2, 9):
                for y in range(block_height):
                    for x in range(block_width):
                        color = _pixel(rgba, width, height, block_x + x, block_y + y)
                        if image_type == 1:
                            value = _luminance(color)
                        elif image_type == 2:
                            value = (((color[3] + 8) // 17) << 4) | ((_luminance(color) + 8) // 17)
                        else:
                            value = index_lookup[_normalize_palette_color(color, palette_type)]
                        block.append(value)
            else:
                for y in range(block_height):
                    for x in range(block_width):
                        color = _pixel(rgba, width, height, block_x + x, block_y + y)
                        if image_type == 3:
                            value = (color[3] << 8) | _luminance(color)
                        elif image_type == 4:
                            value = _rgb565_pack(color)
                        elif image_type == 5:
                            value = _encode_rgb5a3(color)
                        elif image_type == 10:
                            value = index_lookup[_normalize_palette_color(color, palette_type)] & 0x3FFF
                        else:
                            raise GXTextureError("Unsupported GX image type {}.".format(image_type))
                        block.extend(struct.pack(">H", value))
            if len(block) != block_bytes:
                raise GXTextureError("GX encoder produced an invalid {} block length.".format(GX_FORMAT_NAMES[image_type]))
            encoded.extend(block)
    if len(encoded) != required:
        raise GXTextureError("GX encoder produced an unexpected data length.")
    return bytes(encoded), palette_bytes


def replace_texture_in_dat(dat_data: bytes, texture: TexturePreview, png_data: bytes) -> bytes:
    """Replace one image in a DAT without moving data blocks or rebuilding pointers.

    The PNG must exactly match the original pixel dimensions. GX and palette
    payloads are encoded to the same allocated byte lengths, so the DAT section
    layout, relocation table, and source file size remain unchanged.
    """
    if len(dat_data) < 0x20:
        raise GXTextureError("Source DAT is shorter than its header.")
    declared_size, rt_start = struct.unpack_from(">II", dat_data, 0)
    if declared_size != len(dat_data) or rt_start > len(dat_data) - 0x20:
        raise GXTextureError("Source DAT header is inconsistent; refusing to modify it.")
    width, height, rgba = decode_png_rgba(png_data)
    if (width, height) != (texture.width, texture.height):
        raise GXTextureError(
            "PNG dimensions are {}×{}; this texture requires exactly {}×{} pixels. "
            "Resize the PNG before importing.".format(width, height, texture.width, texture.height)
        )
    encoded_image, encoded_palette = encode_gx_pixels(
        rgba, width, height, texture.image_type,
        texture.palette_type, texture.palette_color_count,
    )
    if len(encoded_image) != texture.image_data_length:
        raise GXTextureError(
            "Encoded GX image is {:,} bytes; source block is {:,} bytes.".format(
                len(encoded_image), texture.image_data_length
            )
        )
    image_absolute = 0x20 + texture.image_data_offset
    if image_absolute < 0x20 or image_absolute + len(encoded_image) > len(dat_data):
        raise GXTextureError("Image data block extends beyond the source DAT.")
    image_header_absolute = 0x20 + texture.image_header_offset
    if image_header_absolute + 0x18 > len(dat_data):
        raise GXTextureError("Image header lies outside the source DAT.")
    header_data_pointer, header_width, header_height, header_type, mipmap_flag = struct.unpack_from(
        ">IHHII", dat_data, image_header_absolute
    )
    if (
        header_data_pointer != texture.image_data_offset
        or (header_width, header_height, header_type) != (texture.width, texture.height, texture.image_type)
        or mipmap_flag != texture.mipmap_flag
    ):
        raise GXTextureError("Texture header changed since the gallery was scanned; rescan before importing.")
    if mipmap_flag:
        raise GXTextureError(
            "This texture uses mipmaps. Mipmapped texture import is not enabled yet, so no data was changed."
        )

    updated = bytearray(dat_data)
    updated[image_absolute:image_absolute + len(encoded_image)] = encoded_image

    if texture.image_type in (8, 9, 10):
        if (
            texture.palette_header_offset is None or texture.palette_data_offset is None
            or texture.palette_type is None or len(encoded_palette) != texture.palette_data_length
        ):
            raise GXTextureError("The selected indexed texture has incomplete palette metadata.")
        palette_header_absolute = 0x20 + texture.palette_header_offset
        palette_data_absolute = 0x20 + texture.palette_data_offset
        if palette_header_absolute + 0x0E > len(updated):
            raise GXTextureError("Palette header lies outside the source DAT.")
        if palette_data_absolute + len(encoded_palette) > len(updated):
            raise GXTextureError("Palette data block extends beyond the source DAT.")
        current_palette_pointer, current_palette_type, _name, current_count = struct.unpack_from(
            ">IIIH", updated, palette_header_absolute
        )
        if (
            current_palette_pointer != texture.palette_data_offset
            or current_palette_type != texture.palette_type
            or current_count != texture.palette_color_count
        ):
            raise GXTextureError("Palette header changed since the gallery was scanned; rescan before importing.")
        updated[palette_data_absolute:palette_data_absolute + len(encoded_palette)] = encoded_palette

    return bytes(updated)
