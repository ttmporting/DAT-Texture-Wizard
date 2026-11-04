"""Read-only DAT structure tree model for the native DTW preview GUI.

The model mirrors the original application's Structural Analysis navigation:
File Header -> Relocation/Root/Reference/String tables -> lazily expanded
HSD structures. It deliberately does not edit or rebuild DAT files.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dtw_dat_probe import DatFormatError, inspect_dat

HEADER_SIZE = 0x20


@dataclass(frozen=True)
class StructurePointer:
    location: int
    target: int
    field_name: str
    child_type: str | None = None


@dataclass(frozen=True)
class TreeRecord:
    kind: str
    text: str
    iid: str
    offset: int | None = None
    type_hint: str | None = None
    label: str | None = None
    ancestor_offsets: tuple[int, ...] = ()


# Partial class knowledge taken from the original DTW hsdStructures definitions.
# Unknown structures remain browsable as generic pointer-bearing structures.
TYPE_TITLES = {
    "JointObjDesc": "Joint Struct",
    "MatAnimJointDesc": "Material Animation Joint",
    "MatAnimDesc": "Material Animation Struct",
    "DisplayObjDesc": "Display Object",
    "MaterialObjDesc": "Material Object",
    "PolygonObjDesc": "Polygons Object",
    "TextureObjDesc": "Texture Object",
    "InverseMatrixObjDesc": "Inverse Matrix",
    "MaterialColorObjDesc": "Material Colors",
    "PixelProcObjDesc": "Pixel Processing Object",
    "VertexAttributesArray": "Vertex Attributes Array",
    "DisplayDataBlock": "Display List Data Block",
}

# Relative pointer-field offsets -> (field label, expected target class).
FIELD_LAYOUTS: dict[str, dict[int, tuple[str, str | None]]] = {
    "JointObjDesc": {
        0x00: ("Name Pointer", None),
        0x08: ("Child Pointer", "JointObjDesc"),
        0x0C: ("Next Sibling Pointer", "JointObjDesc"),
        0x10: ("Display Object Pointer", "DisplayObjDesc"),
        0x38: ("Inverse Matrix Pointer", "InverseMatrixObjDesc"),
        0x3C: ("Reference Object Pointer", None),
    },
    "MatAnimJointDesc": {
        0x00: ("Child Pointer", "MatAnimJointDesc"),
        0x04: ("Next Sibling Pointer", "MatAnimJointDesc"),
        0x08: ("Material Animation Pointer", "MatAnimDesc"),
    },
    "MatAnimDesc": {
        0x00: ("Next Sibling Pointer", "MatAnimDesc"),
        0x04: ("Animation Object Pointer", None),
        0x08: ("Texture Animation Pointer", None),
        0x0C: ("Render Animation Pointer", None),
    },
    "DisplayObjDesc": {
        0x00: ("Name Pointer", None),
        0x04: ("Next Sibling Pointer", "DisplayObjDesc"),
        0x08: ("Material Object Pointer", "MaterialObjDesc"),
        0x0C: ("Polygon Object Pointer", "PolygonObjDesc"),
    },
    "MaterialObjDesc": {
        0x00: ("Name Pointer", None),
        0x08: ("Texture Object Pointer", "TextureObjDesc"),
        0x0C: ("Material Colors Pointer", "MaterialColorObjDesc"),
        0x14: ("Pixel Processing Pointer", "PixelProcObjDesc"),
    },
    "PolygonObjDesc": {
        0x00: ("Name Pointer", None),
        0x04: ("Next Sibling Pointer", "PolygonObjDesc"),
        0x08: ("Vertex Attributes Array Pointer", "VertexAttributesArray"),
        0x14: ("Display List Data Pointer", "DisplayDataBlock"),
    },
}

STRUCT_LENGTHS = {
    "JointObjDesc": 0x40,
    "MatAnimJointDesc": 0x0C,
    "MatAnimDesc": 0x10,
    "DisplayObjDesc": 0x10,
    "MaterialObjDesc": 0x18,
    "PolygonObjDesc": 0x18,
}

ROOT_TYPES = {
    "PlyFox5K_Share_joint": "JointObjDesc",
    "PlyFox5KOr_Share_joint": "JointObjDesc",
    "PlyFox5KLa_Share_joint": "JointObjDesc",
    "PlyFox5KGr_Share_joint": "JointObjDesc",
    "PlyFox5K_Share_matanim_joint": "MatAnimJointDesc",
    "PlyFox5KOr_Share_matanim_joint": "MatAnimJointDesc",
    "PlyFox5KLa_Share_matanim_joint": "MatAnimJointDesc",
    "PlyFox5KGr_Share_matanim_joint": "MatAnimJointDesc",
}


def root_type_hint(label: str | None) -> str | None:
    """Recognize standard Melee fighter root-symbol suffixes."""
    if not label:
        return None
    if label in ROOT_TYPES:
        return ROOT_TYPES[label]
    if label.endswith("_Share_matanim_joint"):
        return "MatAnimJointDesc"
    if label.endswith("_Share_joint"):
        return "JointObjDesc"
    return None


class DatTreeModel:
    """Parse a DAT once, then serve lazy tree branches and field inspection."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.data = self.path.read_bytes()
        self.report = inspect_dat(self.data)
        if not self.report.get("valid"):
            raise DatFormatError(
                "DAT structural validation failed: "
                + "; ".join(self.report.get("errors", []))
            )

        self.body = self.data[HEADER_SIZE:]
        h = self.report["header"]
        s = self.report["sections"]
        self.rt_start = h["rt_start"]
        self.rt_count = h["rt_entry_count"]
        self.rt_end = s["rt_end"]
        self.root_nodes_end = s["root_nodes_end"]
        self.string_table_start = s["string_table_start"]
        self.root_count = h["root_node_count"]
        self.ref_count = h["reference_node_count"]

        self.pointer_locations = (
            struct.unpack_from(">{0}I".format(self.rt_count), self.body, self.rt_start)
            if self.rt_count else ()
        )
        self.pointer_values = tuple(
            struct.unpack_from(">I", self.body, location)[0]
            for location in self.pointer_locations
        )
        self.pointer_pairs = tuple(sorted(zip(self.pointer_locations, self.pointer_values)))

        # Pointer targets are candidate structure starts. Null pointers are not structures.
        root_targets = {
            node["structure_offset"] for node in self.report.get("nodes", [])
        }
        self.structure_offsets = sorted(
            {value for value in self.pointer_values if value != 0}
            | root_targets
            | {self.rt_start, self.rt_end, self.root_nodes_end, self.string_table_start}
        )
        self._next_offset = {
            offset: (
                self.structure_offsets[i + 1]
                if i + 1 < len(self.structure_offsets) else self.rt_start
            )
            for i, offset in enumerate(self.structure_offsets)
        }
        self._known_root_labels = {
            node["structure_offset"]: node["label"]
            for node in self.report.get("nodes", [])
            if node.get("label")
        }
        self.root_nodes = [
            node for node in self.report.get("nodes", []) if node["kind"] == "root"
        ]
        self.reference_nodes = [
            node for node in self.report.get("nodes", []) if node["kind"] == "reference"
        ]
        data_pointer_targets = set(self.pointer_values)
        self.root_struct_nodes = [
            n for n in self.root_nodes
            if n["structure_offset"] not in data_pointer_targets
        ]
        self.root_label_nodes = [
            n for n in self.root_nodes
            if n["structure_offset"] in data_pointer_targets
        ]
        self.ref_struct_nodes = [
            n for n in self.reference_nodes
            if n["structure_offset"] not in data_pointer_targets
        ]
        self.ref_label_nodes = [
            n for n in self.reference_nodes
            if n["structure_offset"] in data_pointer_targets
        ]

    @property
    def file_name(self) -> str:
        return self.path.name

    def absolute_offset(self, data_offset: int) -> int:
        return HEADER_SIZE + data_offset

    def structure_length(self, offset: int, type_hint: str | None = None) -> int:
        known = STRUCT_LENGTHS.get(type_hint or "")
        if known is not None:
            span = self._next_offset.get(offset, self.rt_start) - offset
            if span >= known:
                return known
        return max(0, self._next_offset.get(offset, self.rt_start) - offset)

    def field_name(self, type_hint: str | None, relative_offset: int) -> tuple[str, str | None]:
        layout = FIELD_LAYOUTS.get(type_hint or "", {})
        if relative_offset in layout:
            return layout[relative_offset]
        return ("Pointer +0x{:X}".format(relative_offset), None)

    def pointer_fields(
        self, offset: int, type_hint: str | None = None
    ) -> list[StructurePointer]:
        end = offset + self.structure_length(offset, type_hint)
        rows = []
        for location, target in self.pointer_pairs:
            if location < offset:
                continue
            if location >= end:
                break
            field_label, child_type = self.field_name(type_hint, location - offset)
            rows.append(StructurePointer(location, target, field_label, child_type))
        return rows

    def direct_children(
        self, offset: int, type_hint: str | None = None
    ) -> list[StructurePointer]:
        """Return outgoing pointers, excluding known Next_Sibling links.

        As in the original Structural Analysis view, siblings are displayed
        beside one another under their common parent, rather than nested under
        the preceding sibling.
        """
        result = []
        seen = set()
        for pointer in self.pointer_fields(offset, type_hint):
            if pointer.target == 0 or pointer.field_name.startswith("Next Sibling"):
                continue
            if pointer.target not in seen:
                seen.add(pointer.target)
                result.append(pointer)
        return result

    def sibling_chain(
        self, offset: int, type_hint: str | None = None
    ) -> list[tuple[int, str | None]]:
        """Follow known HSD Next_Sibling fields with loop protection."""
        layout = FIELD_LAYOUTS.get(type_hint or "", {})
        next_fields = [
            (pos, child_type)
            for pos, (name, child_type) in layout.items()
            if name.startswith("Next Sibling")
        ]
        if not next_fields:
            return []
        rel, sibling_type = next_fields[0]
        location = offset + rel
        if location not in self.pointer_locations:
            return []
        target = struct.unpack_from(">I", self.body, location)[0]
        if not target or target == offset:
            return []
        return [(target, sibling_type)]

    def structure_title(
        self,
        offset: int,
        type_hint: str | None = None,
        label: str | None = None,
        sibling_index: int = 0,
    ) -> str:
        if label:
            return label
        title = TYPE_TITLES.get(type_hint or "", "Structure")
        if sibling_index:
            title += " {}".format(sibling_index + 1)
        return title

    def children_with_siblings(
        self,
        offset: int,
        type_hint: str | None = None,
        ancestor_offsets: Iterable[int] = (),
    ) -> list[tuple[int, str | None, str | None, bool]]:
        """Return direct children and known sibling chains.

        The final boolean identifies a back-reference/cycle that must not be
        expanded again.
        """
        ancestors = tuple(ancestor_offsets) + (offset,)
        output = []
        seen = set()
        for pointer in self.direct_children(offset, type_hint):
            current = pointer.target
            current_type = pointer.child_type
            sibling_steps = 0
            while current and current not in seen:
                seen.add(current)
                is_cycle = current in ancestors
                output.append((current, current_type, None, is_cycle))
                if is_cycle:
                    break
                sibling_rows = self.sibling_chain(current, current_type)
                if not sibling_rows:
                    break
                current, current_type = sibling_rows[0]
                sibling_steps += 1
                if sibling_steps > 4096:
                    break
        return output

    def root_tree_records(self) -> list[TreeRecord]:
        """Top-level records matching the original File Header/table layout."""
        out = [TreeRecord("file_header", "File Header", "file-header", 0)]
        out.append(TreeRecord(
            "relocation_table", "Relocation Table",
            "file-header/relocation-table", self.rt_start
        ))
        if self.root_struct_nodes:
            out.append(TreeRecord(
                "root_table", "Root Nodes Table",
                "file-header/root-nodes-table", self.rt_end
            ))
        if self.ref_struct_nodes:
            out.append(TreeRecord(
                "reference_table", "Reference Nodes Table",
                "file-header/reference-nodes-table", self.root_nodes_end
            ))
        out.append(TreeRecord(
            "string_table", "String Table",
            "file-header/string-table", self.string_table_start
        ))
        return out

    def table_children(self, table_kind: str) -> list[TreeRecord]:
        if table_kind == "root_table":
            nodes = self.root_struct_nodes
            prefix = "file-header/root-nodes-table"
        elif table_kind == "reference_table":
            nodes = self.ref_struct_nodes
            prefix = "file-header/reference-nodes-table"
        else:
            return []
        records = []
        for i, node in enumerate(nodes):
            offset = node["structure_offset"]
            label = node.get("label") or None
            type_hint = root_type_hint(label)
            title = self.structure_title(offset, type_hint, label, i)
            iid = prefix + "/" + str(offset)
            records.append(
                TreeRecord("structure", title, iid, offset, type_hint, label, (offset,))
            )
        return records

    def record_pointer_details(
        self, offset: int, type_hint: str | None = None
    ) -> list[dict[str, object]]:
        rows = []
        for ptr in self.pointer_fields(offset, type_hint):
            rows.append({
                "field": ptr.field_name,
                "relative_offset": ptr.location - offset,
                "file_offset": self.absolute_offset(ptr.location),
                "target": ptr.target,
                "target_file_offset": self.absolute_offset(ptr.target) if ptr.target else None,
                "target_type": ptr.child_type,
            })
        return rows

    def describe(self) -> dict[str, object]:
        h = self.report["header"]
        s = self.report["sections"]
        return {
            "file": self.file_name,
            "path": str(self.path),
            "size": len(self.data),
            "sha256": self.report["sha256"],
            "root_nodes": len(self.root_nodes),
            "reference_nodes": len(self.reference_nodes),
            "root_structures": len(self.root_struct_nodes),
            "relocations": self.rt_count,
            "data_size": s["data_size"],
            "rt_start": self.rt_start,
            "rt_end": self.rt_end,
            "string_table_start": self.string_table_start,
            "magic": h.get("magic_ascii", h.get("magic_hex", "")),
        }

    def read_bytes(self, offset: int, length: int) -> bytes:
        start = HEADER_SIZE + offset
        return self.data[start:start + length]
