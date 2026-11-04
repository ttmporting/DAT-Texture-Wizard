"""Read-only structural validator for HSD/GameCube DAT files.

This checks the header, relocation table, root/reference node tables, and
string-table boundaries used by DAT Texture Wizard's hsdFiles.datFileObj.
It does not parse HSD structure classes or edit/rebuild the file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

HEADER_SIZE = 0x20


class DatFormatError(ValueError):
    """The file does not contain a structurally readable HSD DAT header."""


def inspect_dat(data: bytes) -> dict[str, Any]:
    """Return a structural report; malformed sections are reported as errors."""
    errors: list[str] = []
    warnings: list[str] = []
    if len(data) < HEADER_SIZE:
        raise DatFormatError(
            "File is shorter than the 0x20-byte HSD DAT header ({})".format(len(data))
        )

    file_size, rt_start, rt_count, root_count, ref_count = struct.unpack_from(">5I", data, 0)
    magic = data[20:24]
    body = data[HEADER_SIZE:]
    body_size = len(body)

    rt_end = rt_start + rt_count * 4
    root_nodes_end = rt_end + root_count * 8
    string_table_start = root_nodes_end + ref_count * 8

    if file_size != len(data):
        warnings.append(
            "Header file size {} differs from actual size {}".format(file_size, len(data))
        )
    if not (0 <= rt_start <= rt_end <= root_nodes_end <= string_table_start <= body_size):
        errors.append(
            "Section boundaries exceed the data section: "
            "rt_start={}, rt_end={}, root_nodes_end={}, string_table_start={}, body_size={}".format(
                rt_start, rt_end, root_nodes_end, string_table_start, body_size
            )
        )
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "file_size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "header": {
                "declared_file_size": file_size,
                "rt_start": rt_start,
                "rt_entry_count": rt_count,
                "root_node_count": root_count,
                "reference_node_count": ref_count,
                "magic_hex": magic.hex(),
            },
            "sections": {
                "data_size": body_size,
                "rt_end": rt_end,
                "root_nodes_end": root_nodes_end,
                "string_table_start": string_table_start,
            },
        }

    rt_bytes = body[rt_start:rt_end]
    pointer_locations: tuple[int, ...] = ()
    pointer_targets: tuple[int, ...] = ()
    if len(rt_bytes) != rt_count * 4:
        errors.append("Relocation table length does not match the header")
    else:
        pointer_locations = (
            struct.unpack(">{}I".format(rt_count), rt_bytes) if rt_count else ()
        )
        bad_locations = [offset for offset in pointer_locations if offset + 4 > rt_start]
        if bad_locations:
            errors.append(
                "{} relocation entries point outside the pre-RT data area".format(
                    len(bad_locations)
                )
            )
        pointer_targets = tuple(
            struct.unpack_from(">I", body, offset)[0]
            for offset in pointer_locations
            if offset + 4 <= rt_start
        )
        bad_targets = [offset for offset in pointer_targets if offset >= rt_start]
        if bad_targets:
            errors.append(
                "{} relocation targets lie outside the data area".format(len(bad_targets))
            )

    nodes: list[dict[str, Any]] = []
    node_count = root_count + ref_count
    node_table = body[rt_end:string_table_start]
    if len(node_table) != node_count * 8:
        errors.append("Root/reference node table length does not match the header")
    else:
        string_table = body[string_table_start:]
        raw_strings = string_table.split(b"\0")
        strings: dict[int, str] = {}
        string_offset = 0
        for raw in raw_strings[:node_count]:
            try:
                strings[string_offset] = raw.decode("ascii")
            except UnicodeDecodeError:
                errors.append("String table contains a non-ASCII label")
                break
            string_offset += len(raw) + 1
        if len(strings) != node_count:
            errors.append(
                "String table has {} labels; header declares {} nodes".format(
                    len(strings), node_count
                )
            )

        for index in range(node_count):
            struct_offset, label_offset = struct.unpack_from(">II", node_table, index * 8)
            label = strings.get(label_offset)
            if label is None:
                errors.append(
                    "Node {} refers to missing string-table offset {}".format(
                        index, label_offset
                    )
                )
            if struct_offset >= rt_start:
                errors.append(
                    "Node {} structure offset {} is outside the data area".format(
                        index, struct_offset
                    )
                )
            nodes.append({
                "kind": "root" if index < root_count else "reference",
                "structure_offset": struct_offset,
                "label_offset": label_offset,
                "label": label,
            })

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "file_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "header": {
            "declared_file_size": file_size,
            "rt_start": rt_start,
            "rt_entry_count": rt_count,
            "root_node_count": root_count,
            "reference_node_count": ref_count,
            "magic_hex": magic.hex(),
            "magic_ascii": magic.decode("ascii", errors="replace"),
        },
        "sections": {
            "data_size": body_size,
            "rt_end": rt_end,
            "root_nodes_end": root_nodes_end,
            "string_table_start": string_table_start,
            "string_table_size": body_size - string_table_start,
        },
        "relocation": {
            "entry_count": len(pointer_locations),
            "pointer_locations_aligned": all(x % 4 == 0 for x in pointer_locations),
            "pointer_targets_checked": len(pointer_targets),
        },
        "nodes": nodes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only HSD DAT structural probe")
    parser.add_argument("dat_file", type=Path, help="DAT file to inspect")
    args = parser.parse_args()
    try:
        report = inspect_dat(args.dat_file.read_bytes())
    except (OSError, DatFormatError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
