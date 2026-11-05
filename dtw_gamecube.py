"""GameCube ISO FST reader, file export, and verified copy-on-write rebuilds.

The source image is never modified. Rebuilds preserve the boot/BI2/apploader/DOL
prefix, write a relocated FST, then repack all FST files in directory-table
order with aligned data extents. The rebuilt image is reopened and verified
before its temporary file is atomically renamed to the requested destination.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

GC_MAGIC = bytes.fromhex("C2339F3D")
BOOT_HEADER_MIN = 0x440
FST_ENTRY_SIZE = 12
MELEE_GAME_IDS = {"GALE01", "GALP01", "GALJ01", "GTME01"}


class GameCubeFormatError(ValueError):
    """The input does not contain a structurally readable GameCube ISO."""


class ReplacementError(ValueError):
    """A staged replacement cannot be written safely without relocating files."""


@dataclass(frozen=True)
class FstEntry:
    index: int
    name: str
    path: str
    kind: str
    parent_index: int
    declared_parent_index: int | None
    offset: int | None
    size: int | None
    next_index: int | None = None

    @property
    def is_directory(self) -> bool:
        return self.kind == "directory"

    @property
    def is_file(self) -> bool:
        return self.kind == "file"


class GameCubeIso:
    """Read a GameCube boot header and FST, with preorder-based directory paths."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.iso_size = self.path.stat().st_size
        with self.path.open("rb") as source:
            header = source.read(BOOT_HEADER_MIN)
        if len(header) < BOOT_HEADER_MIN:
            raise GameCubeFormatError("Image is too short to contain a GameCube boot header.")
        if header[0x1C:0x20] != GC_MAGIC:
            raise GameCubeFormatError("GameCube disc magic C2339F3D was not found at 0x1C.")
        try:
            self.game_id = header[:6].decode("ascii")
        except UnicodeDecodeError as exc:
            raise GameCubeFormatError("Game ID is not ASCII.") from exc
        self.disc_number = header[6]
        self.game_version = header[7]
        self.dol_offset, self.fst_offset, self.fst_size, self.fst_max_size = struct.unpack_from(
            ">4I", header, 0x420
        )
        self.is_melee = self.game_id in MELEE_GAME_IDS
        if not self.fst_offset or self.fst_size < FST_ENTRY_SIZE:
            raise GameCubeFormatError("Boot header does not point to a plausible FST.")
        if self.fst_offset + self.fst_size > self.iso_size:
            raise GameCubeFormatError("FST extends beyond the end of the image.")
        with self.path.open("rb") as source:
            source.seek(self.fst_offset)
            self.fst = source.read(self.fst_size)
        if len(self.fst) != self.fst_size:
            raise GameCubeFormatError("FST could not be read completely.")
        self.entries, self.parent_mismatches = self._parse_fst()
        self.by_index = {entry.index: entry for entry in self.entries}
        self.children: dict[int, list[FstEntry]] = {}
        for entry in self.entries[1:]:
            self.children.setdefault(entry.parent_index, []).append(entry)
        self._file_offsets = sorted(
            entry.offset for entry in self.entries
            if entry.is_file and entry.offset is not None and entry.size is not None and entry.size > 0
        )
        self.warnings: list[str] = []
        if self.parent_mismatches:
            self.warnings.append(
                "{} FST directory parent field(s) disagree with their preorder nesting; "
                "paths were recovered using directory next-index ranges.".format(
                    len(self.parent_mismatches)
                )
            )

    def _parse_fst(self) -> tuple[list[FstEntry], list[tuple[int, int, int]]]:
        if len(self.fst) < FST_ENTRY_SIZE:
            raise GameCubeFormatError("FST root entry is truncated.")
        root_type = self.fst[0]
        entry_count = int.from_bytes(self.fst[8:12], "big")
        if root_type == 0:
            raise GameCubeFormatError("FST root entry is not marked as a directory.")
        if entry_count < 1 or entry_count * FST_ENTRY_SIZE > len(self.fst):
            raise GameCubeFormatError("FST entry count exceeds the table size.")
        names = self.fst[entry_count * FST_ENTRY_SIZE:]
        name_start = int.from_bytes(self.fst[1:4], "big")
        if name_start >= len(names) and name_start != 0:
            raise GameCubeFormatError("FST root name offset is outside the string table.")
        root_next = int.from_bytes(self.fst[8:12], "big")
        if root_next != entry_count:
            raise GameCubeFormatError("FST root directory next-index does not match entry count.")

        def get_name(name_offset: int, index: int) -> str:
            if name_offset >= len(names):
                raise GameCubeFormatError("FST entry {} has an invalid name offset.".format(index))
            end = names.find(b"\0", name_offset)
            if end < 0:
                raise GameCubeFormatError("FST entry {} has an unterminated name.".format(index))
            try:
                value = names[name_offset:end].decode("utf-8")
            except UnicodeDecodeError:
                value = names[name_offset:end].decode("shift_jis", errors="replace")
            if not value or value in {".", ".."} or "/" in value or "\\" in value:
                raise GameCubeFormatError("FST entry {} has an unsafe path component.".format(index))
            return value

        root = FstEntry(0, self.game_id, self.game_id, "directory", -1, 0, None, None, entry_count)
        parsed = [root]
        # Stack stores (directory FST index, exclusive next-index, full path).
        stack: list[tuple[int, int, str]] = [(0, entry_count, self.game_id)]
        mismatches: list[tuple[int, int, int]] = []

        for index in range(1, entry_count):
            while stack and index >= stack[-1][1]:
                stack.pop()
            if not stack:
                raise GameCubeFormatError("FST entry {} is outside the root directory range.".format(index))
            actual_parent, _, parent_path = stack[-1]
            pos = index * FST_ENTRY_SIZE
            flag = self.fst[pos]
            name_offset = int.from_bytes(self.fst[pos + 1:pos + 4], "big")
            name = get_name(name_offset, index)
            path = parent_path + "/" + name
            if flag != 0:
                declared_parent = int.from_bytes(self.fst[pos + 4:pos + 8], "big")
                next_index = int.from_bytes(self.fst[pos + 8:pos + 12], "big")
                if not index < next_index <= entry_count:
                    raise GameCubeFormatError(
                        "Directory entry {} has invalid next-index {}.".format(index, next_index)
                    )
                if declared_parent != actual_parent:
                    mismatches.append((index, declared_parent, actual_parent))
                parsed.append(FstEntry(
                    index, name, path, "directory", actual_parent,
                    declared_parent, None, None, next_index
                ))
                stack.append((index, next_index, path))
            else:
                file_offset, file_size = struct.unpack_from(">II", self.fst, pos + 4)
                if file_offset > self.iso_size or file_size > self.iso_size - file_offset:
                    raise GameCubeFormatError(
                        "File entry {} ({}) extends beyond the image.".format(index, path)
                    )
                parsed.append(FstEntry(
                    index, name, path, "file", actual_parent,
                    None, file_offset, file_size, None
                ))
        return parsed, mismatches

    @property
    def file_count(self) -> int:
        return sum(entry.is_file for entry in self.entries)

    @property
    def directory_count(self) -> int:
        return sum(entry.is_directory for entry in self.entries) - 1

    def get_entry(self, index: int) -> FstEntry:
        try:
            return self.by_index[index]
        except KeyError as exc:
            raise KeyError("Unknown FST entry index: {}".format(index)) from exc

    def children_of(self, parent_index: int) -> list[FstEntry]:
        return list(self.children.get(parent_index, ()))

    def find(self, query: str) -> list[FstEntry]:
        query = query.casefold()
        return [entry for entry in self.entries[1:] if query in entry.path.casefold()]

    def read_file(self, index: int, replacements: Mapping[int, str | Path] | None = None) -> bytes:
        entry = self.get_entry(index)
        if not entry.is_file or entry.offset is None or entry.size is None:
            raise ValueError("Selected FST entry is not a file.")
        replacement = (replacements or {}).get(index)
        if replacement:
            return Path(replacement).read_bytes()
        with self.path.open("rb") as source:
            source.seek(entry.offset)
            data = source.read(entry.size)
        if len(data) != entry.size:
            raise OSError("Could not read complete file data for {}.".format(entry.path))
        return data

    def allocation_end(self, index: int) -> int:
        entry = self.get_entry(index)
        if not entry.is_file or entry.offset is None:
            raise ValueError("Selected FST entry is not a file.")
        boundaries = [
            offset for offset in self._file_offsets if offset > entry.offset
        ]
        if self.fst_offset > entry.offset:
            boundaries.append(self.fst_offset)
        return min(boundaries) if boundaries else self.iso_size

    def replacement_capacity(self, index: int) -> int:
        entry = self.get_entry(index)
        if not entry.is_file or entry.offset is None:
            raise ReplacementError("Only existing files can be replaced.")
        allocation_end = self.allocation_end(index)
        original_end = entry.offset + (entry.size or 0)
        if original_end > allocation_end:
            raise ReplacementError(
                "The original file already overlaps the next file/FST boundary; "
                "safe in-place replacement is disabled for this entry."
            )
        return max(0, allocation_end - entry.offset)

    def validate_replacement(self, index: int, replacement_path: str | Path) -> dict[str, object]:
        """Validate a replacement file's basic identity without imposing size limits."""
        entry = self.get_entry(index)
        candidate = Path(replacement_path).expanduser().resolve()
        if not entry.is_file:
            raise ReplacementError("Select a file, not a folder, to import a replacement.")
        if not candidate.is_file():
            raise ReplacementError("Replacement file does not exist.")
        source_suffix = Path(entry.name).suffix.casefold()
        replacement_suffix = candidate.suffix.casefold()
        if source_suffix and source_suffix != replacement_suffix:
            raise ReplacementError(
                "File extension mismatch: disc file is {} but replacement is {}.".format(
                    source_suffix, replacement_suffix or "(no extension)"
                )
            )
        return {
            "entry_index": index,
            "disc_path": entry.path,
            "replacement_path": str(candidate),
            "old_size": entry.size,
            "new_size": candidate.stat().st_size,
            "capacity": None,
            "sha256": self.sha256_file(candidate),
        }

    def stage_replacement_for_rebuild(
        self, index: int, replacement_path: str | Path
    ) -> dict[str, object]:
        """Stage any valid-size replacement; the full rebuild repacks every file."""
        info = self.validate_replacement(index, replacement_path)
        try:
            info["capacity"] = self.replacement_capacity(index)
        except ReplacementError:
            info["capacity"] = None
        return info

    def stage_replacement(self, index: int, replacement_path: str | Path) -> dict[str, object]:
        """Stage a replacement only if its current allocation is large enough."""
        info = self.validate_replacement(index, replacement_path)
        capacity = self.replacement_capacity(index)
        if int(info["new_size"]) > capacity:
            raise ReplacementError(
                "Replacement is {:,} bytes, but only {:,} bytes are available in the "
                "current allocation. Use stage_replacement_for_rebuild() to queue it "
                "for a full ISO rebuild.".format(int(info["new_size"]), capacity)
            )
        info["capacity"] = capacity
        return info

    @staticmethod
    def sha256_file(path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()


    @staticmethod
    def _dol_size_from_header(dol_header: bytes) -> int:
        """Return DOL byte length using its 7 text and 11 data section tables."""
        if len(dol_header) < 0x100:
            raise GameCubeFormatError("DOL header is truncated.")
        offsets = struct.unpack_from(">18I", dol_header, 0x00)
        sizes = struct.unpack_from(">18I", dol_header, 0x90)
        ends = [0x100]
        for section_offset, section_size in zip(offsets, sizes):
            if section_size == 0:
                continue
            if section_offset < 0x100:
                raise GameCubeFormatError("DOL section points inside its 0x100-byte header.")
            ends.append(section_offset + section_size)
        return max(ends)

    def _system_region_end(self) -> int:
        if not self.dol_offset:
            raise GameCubeFormatError("Boot header has no DOL offset; full ISO rebuild is unsafe.")
        with self.path.open("rb") as source:
            source.seek(self.dol_offset)
            dol_header = source.read(0x100)
        dol_size = self._dol_size_from_header(dol_header)
        dol_end = self.dol_offset + dol_size
        if dol_end > self.iso_size:
            raise GameCubeFormatError("DOL extent runs beyond the source image.")
        if dol_end > self.fst_offset:
            raise GameCubeFormatError("DOL overlaps the current FST; refusing to rebuild this image.")
        return max(0x440, dol_end)

    @staticmethod
    def _align(value: int, alignment: int = 0x20) -> int:
        return (value + alignment - 1) & ~(alignment - 1)

    @staticmethod
    def _copy_and_hash(source, destination, length: int, chunk_size: int = 1024 * 1024) -> str:
        digest = hashlib.sha256()
        remaining = length
        while remaining:
            block = source.read(min(chunk_size, remaining))
            if not block:
                raise OSError("Unexpected end of file while copying ISO content.")
            destination.write(block)
            digest.update(block)
            remaining -= len(block)
        return digest.hexdigest()

    def rebuild_patched_copy(
        self,
        destination: str | Path,
        staged: Mapping[int, str | Path],
        overwrite: bool = False,
    ) -> dict[str, object]:
        """Repack every FST file and relocate the FST into a new, verified ISO copy.

        The original boot block, BI2, apploader, and DOL remain at their original
        offsets. The updated FST follows the DOL; all FST files are repacked at
        0x20-byte boundaries after the FST. File names, directory entries, and
        the string table are retained byte-for-byte.
        """
        dest = Path(destination).expanduser().resolve()
        if dest == self.path:
            raise ReplacementError("Choose a new output path; the source ISO is never overwritten.")
        if not staged:
            raise ReplacementError("There are no staged file replacements.")
        if dest.exists() and not overwrite:
            raise FileExistsError(str(dest))
        dest.parent.mkdir(parents=True, exist_ok=True)

        staged_paths: dict[int, Path] = {}
        for index, source_path in staged.items():
            info = self.validate_replacement(index, source_path)
            staged_paths[index] = Path(str(info["replacement_path"]))

        system_end = self._system_region_end()
        new_fst_offset = self._align(system_end)
        new_fst = bytearray(self.fst)
        fst_entry_count = len(self.entries)
        if len(new_fst) < fst_entry_count * FST_ENTRY_SIZE:
            raise GameCubeFormatError("FST entry table is shorter than its declared entry count.")

        file_layout: list[tuple[FstEntry, int, int, Path | None]] = []
        cursor = self._align(new_fst_offset + len(new_fst))
        for entry in self.entries:
            if entry.is_directory:
                # The parent field is part of the FST format. Reconstruct it from
                # the directory preorder ranges rather than preserving malformed
                # parent indices seen in some rebuilt/custom images.
                struct.pack_into(">I", new_fst, entry.index * FST_ENTRY_SIZE + 4, entry.parent_index)
                continue
            replacement_path = staged_paths.get(entry.index)
            file_size = replacement_path.stat().st_size if replacement_path else int(entry.size or 0)
            if entry.offset is None:
                raise GameCubeFormatError("File {} has no source offset.".format(entry.path))
            # A FST entry for the boot DOL is rare, but if present it must keep
            # the same offset because the boot header still points to it.
            is_boot_dol = entry.offset == self.dol_offset and entry.name.casefold() == "start.dol"
            if is_boot_dol and replacement_path:
                raise ReplacementError("Replacing start.dol is not supported by this safe rebuild.")
            if is_boot_dol:
                new_offset = entry.offset
            else:
                new_offset = cursor
                cursor = self._align(cursor + file_size)
            if new_offset > 0xFFFFFFFF or file_size > 0xFFFFFFFF or new_offset + file_size > 0x100000000:
                raise ReplacementError("Rebuilt image exceeds GameCube's 32-bit FST offset/size limits.")
            struct.pack_into(">II", new_fst, entry.index * FST_ENTRY_SIZE + 4, new_offset, file_size)
            file_layout.append((entry, new_offset, file_size, replacement_path))

        fst_size = len(new_fst)
        if new_fst_offset > 0xFFFFFFFF or fst_size > 0xFFFFFFFF:
            raise ReplacementError("Updated FST exceeds GameCube's 32-bit header limits.")
        total_size = max(cursor, new_fst_offset + fst_size)
        if total_size > 0x100000000:
            raise ReplacementError("Rebuilt image would exceed the 4 GiB GameCube file-offset limit.")

        fd, temp_name = tempfile.mkstemp(
            prefix="." + dest.name + ".", suffix=".partial", dir=str(dest.parent)
        )
        os.close(fd)
        temp_path = Path(temp_name)
        result_entries: dict[str, dict[str, object]] = {}
        try:
            with self.path.open("rb") as original, temp_path.open("w+b") as output:
                self._copy_and_hash(original, output, system_end)
                if output.tell() < new_fst_offset:
                    output.write(bytes(new_fst_offset - output.tell()))
                output.seek(new_fst_offset)
                output.write(new_fst)
                for entry, new_offset, file_size, replacement_path in file_layout:
                    output.seek(new_offset)
                    if replacement_path:
                        with replacement_path.open("rb") as replacement:
                            digest = self._copy_and_hash(replacement, output, file_size)
                    else:
                        assert entry.offset is not None
                        original.seek(entry.offset)
                        digest = self._copy_and_hash(original, output, file_size)
                    result_entries[entry.path] = {
                        "offset": new_offset,
                        "size": file_size,
                        "sha256": digest,
                        "entry_index": entry.index,
                        "replaced": replacement_path is not None,
                    }
                output.truncate(total_size)
                output.seek(0x424)
                output.write(struct.pack(">3I", new_fst_offset, fst_size, fst_size))
                output.flush()
                os.fsync(output.fileno())

            verified = GameCubeIso(temp_path)
            if verified.game_id != self.game_id or len(verified.entries) != len(self.entries):
                raise OSError("Rebuilt image header/FST identity verification failed.")
            for entry, _new_offset, expected_size, _replacement_path in file_layout:
                updated = verified.get_entry(entry.index)
                expected = result_entries[entry.path]
                if updated.path != entry.path or updated.size != expected_size:
                    raise OSError("Rebuilt FST entry verification failed for {}.".format(entry.path))
                with temp_path.open("rb") as source:
                    source.seek(updated.offset or 0)
                    digest = hashlib.sha256()
                    remaining = expected_size
                    while remaining:
                        block = source.read(min(1024 * 1024, remaining))
                        if not block:
                            raise OSError("Rebuilt file data truncated for {}.".format(entry.path))
                        digest.update(block)
                        remaining -= len(block)
                if digest.hexdigest() != expected["sha256"]:
                    raise OSError("Rebuilt file hash verification failed for {}.".format(entry.path))
            if verified.fst_offset != new_fst_offset or verified.fst_size != fst_size:
                raise OSError("Rebuilt boot-header FST pointers did not verify.")
            if dest.exists() and not overwrite:
                raise FileExistsError(str(dest))
            os.replace(temp_path, dest)
            return {
                "destination": str(dest),
                "size": dest.stat().st_size,
                "game_id": verified.game_id,
                "fst_offset": verified.fst_offset,
                "fst_size": verified.fst_size,
                "replacements": {
                    path: details for path, details in result_entries.items()
                    if details["replaced"]
                },
                "file_count": len(file_layout),
            }
        except Exception:
            try:
                temp_path.unlink()
            except OSError:
                pass
            raise

    def save_patched_copy(
        self,
        destination: str | Path,
        staged: Mapping[int, str | Path],
        overwrite: bool = False,
    ) -> dict[str, object]:
        """Copy the source ISO, patch files and FST sizes, then verify atomically."""
        dest = Path(destination).expanduser().resolve()
        if dest == self.path:
            raise ReplacementError("Choose a new output path; the source ISO is never overwritten.")
        if not staged:
            raise ReplacementError("There are no staged file replacements.")
        if dest.exists() and not overwrite:
            raise FileExistsError(str(dest))
        dest.parent.mkdir(parents=True, exist_ok=True)

        replacements: list[tuple[FstEntry, Path, int, str]] = []
        for index, source_path in staged.items():
            info = self.stage_replacement(index, source_path)
            entry = self.get_entry(index)
            replacement_path = Path(info["replacement_path"])
            replacements.append((entry, replacement_path, int(info["new_size"]), str(info["sha256"])))
        replacements.sort(key=lambda row: row[0].offset or 0)

        fd, temp_name = tempfile.mkstemp(
            prefix="." + dest.name + ".", suffix=".partial", dir=str(dest.parent)
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            shutil.copy2(self.path, temp_path)
            with temp_path.open("r+b") as output:
                for entry, source_path, new_size, _digest in replacements:
                    assert entry.offset is not None
                    output.seek(entry.offset)
                    with source_path.open("rb") as replacement:
                        shutil.copyfileobj(replacement, output, length=1024 * 1024)
                    # FST file entry size is the final 32-bit word of its 12-byte record.
                    output.seek(self.fst_offset + entry.index * FST_ENTRY_SIZE + 8)
                    output.write(struct.pack(">I", new_size))
                output.flush()
                os.fsync(output.fileno())

            # Re-open the temporary image and verify all new entry sizes and contents.
            verified = GameCubeIso(temp_path)
            result_entries = {}
            for entry, source_path, new_size, digest in replacements:
                updated = verified.get_entry(entry.index)
                if updated.size != new_size:
                    raise OSError("FST size update verification failed for {}.".format(entry.path))
                extracted = verified.read_file(entry.index)
                if len(extracted) != new_size or hashlib.sha256(extracted).hexdigest() != digest:
                    raise OSError("Replacement data verification failed for {}.".format(entry.path))
                result_entries[entry.path] = {
                    "size": new_size,
                    "sha256": digest,
                    "entry_index": entry.index,
                }
            if dest.exists() and not overwrite:
                raise FileExistsError(str(dest))
            os.replace(temp_path, dest)
            return {
                "destination": str(dest),
                "size": dest.stat().st_size,
                "game_id": verified.game_id,
                "replacements": result_entries,
            }
        except Exception:
            try:
                temp_path.unlink()
            except OSError:
                pass
            raise
