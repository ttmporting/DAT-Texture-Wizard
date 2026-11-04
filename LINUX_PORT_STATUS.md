# Linux port status

Target: Nobara 43 (Fedora-derived), x86-64
Upstream baseline: DAT Texture Wizard v6.1.4
Upstream commit: `c411422edeb1cd39aa5df9a41eefe31c902809b7`
Working branch: `linux-port`

## Milestone 1 — compatibility foundation

- [x] Create and verify the `linux-port` branch from the v6.1.4 baseline.
- [x] Add OS helpers for app paths, executable discovery, subprocess creation,
      desktop path opening, and Windows-only Tk tool-window decoration.
- [x] Add unit tests for the compatibility helpers.
- [x] Add Nobara/Fedora dependency setup and a deliberately guarded launcher.
- [x] Add GitHub Actions checks for the isolated compatibility layer.

Recorded local validation:
- 17 total unit tests passed on Python 3: 11 platform-helper tests and 6 DAT-probe tests.
- DAT probe tests cover valid/malformed synthetic HSD headers and tables.
- `dtw_platform.py`, `dtw_dat_probe.py`, and their test modules pass `py_compile`.

The full application is **not yet a native Linux program**. Do not remove the
launch guard or create `.linux-port-ready` until the application is converted
and binary-format regression tests pass.

## Python 2 migration inventory

A static scan of the upstream v6.1.4 files found:

| File | Lines | Print statements | xrange | Other notable blockers |
|---|---:|---:|---:|---|
| `DAT Texture Wizard.py` | 14,118 | 67 | 22 | 3 `long()`, 8 legacy imports, `os.startfile`, subprocess `creationflags` |
| `tplCodec.py` | 1,041 | 4 | 48 | Python 2 `StringIO`, Windows `pngquant.exe`, subprocess `creationflags` |
| `hsdFiles.py` | 1,243 | 49 | 1 | legacy `tkMessageBox` import |
| `hsdStructures.py` | 2,711 | 26 | 0 | `sets.Set`, `raw_input()`, legacy `tkMessageBox` |
| `GuiSubComponents.py` | 662 | 0 | 0 | legacy Tk imports, `dict.has_key()`, Windows `-toolwindow` |
| `RenderEngine.py` | 231 | 0 | 0 | legacy `Tkinter` import |
| `newTkDnD.py` | 111 | 0 | 0 | bundled Windows TkDND paths |
| `png.py` | 3,276 | 0 | 0 | 7 references to Python 2 `basestring` |

These are static source-search counts, not a syntax parse or proof of
Python 3 readiness.

## Next milestones

### Milestone 2 — Python 3 conversion

1. Run a controlled 2to3 conversion on the Python application modules.
2. Replace `sets.Set`, Python 2 Tk imports, `long`, `xrange`, and
   `raw_input` with Python 3 equivalents.
3. Review PyPNG's `basestring` compatibility and converted imports.
4. Replace binary `StringIO` usage with `io.BytesIO`; do not use text
   `io.StringIO` for DAT/TPL/image bytes.
5. Audit `ord`/`chr`, bytearray indexing, struct packing, and file I/O
   boundaries. Add fixtures before changing serialization code.

### Milestone 3 — Linux runtime integration

1. Replace `newTkDnD.py`'s Windows TkDND loader with `tkinterdnd2` and a
   non-drag-and-drop fallback.
2. Route subprocess creation through the platform helper and omit
   `creationflags` on POSIX.
3. Discover native `pngquant` and `wimgt`; use argument arrays and avoid
   `shell=True` for paths and user-controlled input.
4. Replace `os.startfile` with the desktop opener helper.
5. Use OS-neutral paths and XDG user config/data directories.

### Milestone 4 — regression tests and packaging

1. Add DAT parse/rebuild round-trip fixtures.
2. Add TPL decode/encode fixtures for all supported texture formats.
3. Exercise PNG import/export, ISO/GCM operations, and native helper integration.
4. Only after those pass, add desktop integration and RPM/AppImage builds.

## Binary safety rule

DAT, TPL, and disc contents are binary formats. All transformations must
preserve byte values and offsets exactly. GUI startup is not enough:
serialization round trips and known-good fixture comparisons are mandatory.

## Verification checkpoint — 2026-11-04

GitHub Actions run [#41887077131](https://github.com/ttmporting/DAT-Texture-Wizard/actions/runs/41887077131)
completed successfully on the `linux-port` branch.

Verified in CI:
- 11 unit tests passed for the standalone OS compatibility helpers.
- `dtw_platform.py` and its test module compile under Python 3.
- The source audit completed and enumerated remaining Python 2 and Windows-only constructs.
- All three shell scripts passed `bash -n`.
- `run-linux.sh` correctly refuses to start unless the explicit
  `.linux-port-ready` marker exists (expected exit status 2).

This is **foundation verification only**. It does not certify DAT/TPL/ISO
operations or mean that the full GUI launches.

### Remaining legacy-source audit findings

The latest source audit still reports:
- 146 Python 2 print statements across the main application, DAT modules,
  structure module, and TPL codec.
- 71 `xrange()` calls and 3 `long()` calls.
- 1 `raw_input()`, 1 `dict.has_key()`, and 7 `basestring` references.
- 18 legacy Tkinter/configuration imports.
- 2 `os.startfile()` calls and 4 Windows `creationflags` arguments.
- 3 hard-coded `.exe` helper references.

### DAT/TPL/ISO fixture availability

The upstream v6.1.4 repository contains no sample `.dat`, `.tpl`, `.iso`,
or `.gcm` fixtures. Its PNG files are application artwork, not test vectors.
Therefore, end-to-end tests for loading/rebuilding DAT files, TPL texture
round-trips, and ISO/GCM rebuilding have **not** been run. Those tests require
known-good, legally supplied fixtures and expected output hashes.

Do not describe the application as Linux-ready until the Python 3 conversion,
native helper integration, and those binary-format regression tests are complete.


## User-provided DAT fixture verification — 2026-11-04

A user-supplied Green Fox Melee skin file, `PlFxGr-TAILS.dat`, was inspected
locally. The DAT itself was not added to this public repository.

Read-only structural probe result:
- File size: 424,158 bytes; the DAT header declares the same size.
- The 0x20-byte HSD header can be unpacked using the same `>5I` layout as
  upstream `hsdFiles.datFileObj.parseHeader()`.
- Data section size: 424,126 bytes.
- Relocation table: 1,658 entries; all pointer locations and pointer targets
  checked by the probe are within the expected data area.
- Root nodes: 2; reference nodes: 0.
- Both root node labels resolve in the ASCII string table:
  `PlyFox5KGr_Share_joint` at data offset 317,536 and
  `PlyFox5KGr_Share_matanim_joint` at data offset 319,120.
- Root/reference node table and string-table boundaries are consistent.
- Probe result: **valid**, with no structural errors or warnings.

A reusable read-only probe is now in `dtw_dat_probe.py`:

```bash
python3 dtw_dat_probe.py /path/to/PlFxGr-TAILS.dat
```

The committed `tests/test_dat_probe.py` builds synthetic HSD DAT byte
sequences to test valid headers, malformed bounds, bad relocation entries,
missing labels, and size discrepancies. It does not publish the user's DAT.

**Scope limitation:** this verifies the HSD header/relocation/node/string-table
structure. It does not yet run DTW's full HSD structure decoder, enumerate or
decode embedded GX textures, save a rebuilt DAT, or prove that a modified file
loads in Dolphin. Those remain end-to-end tests for after the Python 3 port.


Latest verification after adding the DAT probe:
- GitHub Actions run [#41887908094](https://github.com/ttmporting/DAT-Texture-Wizard/actions/runs/41887908094) completed successfully.
- 17 unit tests passed.
- The complete Linux foundation check script passed.


## Second user-provided DAT fixture — 2026-11-04

A second real Melee DAT was extracted by the user from their GameCube ISO
with Wiimm's ISO Tool 3.05a. The ISO itself was not uploaded to this repository,
and this extracted DAT was also kept out of the public repository.

Local read-only probe of `PlFxGr.dat`:
- Size: 362,982 bytes; header-declared size matches.
- SHA-256: `b8a41b28a72c5ce2adc0705075662f73763553838356557ecd302e40c066e6d4`.
- Relocation table: 1,792 entries; all relocation pointer locations are
  4-byte aligned and all 1,792 targets were within the data area.
- Root nodes: 2; reference nodes: 0; both labels resolve:
  `PlyFox5KGr_Share_joint` and
  `PlyFox5KGr_Share_matanim_joint`.
- Probe result: **valid**, with no structural errors or warnings.

An additional read-only root-layout check matched the root entries to the
current upstream DTW structure definitions:
- The joint root at data offset 116,328 has an inferred 0x40-byte span and
  matches the 0x40-byte `JointObjDesc` layout. Its child and display-object
  pointer fields are present in the relocation table.
- The material-animation root at data offset 338,440 has an inferred 0x0C-byte
  span and matches the 0x0C-byte `MatAnimJointDesc` layout. Its child and
  material-animation pointer fields are present in the relocation table.

The two files are intentionally different test inputs, not files expected
to match:
- `PlFxGr.dat` is the original/baseline Fox Green costume DAT extracted from
  the user's rebuilt GameCube ISO.
- `PlFxGr-TAILS.dat` is the user's modified/custom Fox Green skin DAT.

Different sizes, relocation counts, texture payloads, and structure contents
are expected for independently modified DATs. The shared Fox Green root labels
identify their logical costume role; they do not imply byte-for-byte or
structural identity. Both binaries remain local to the test workspace; neither
is committed.

The intended regression workflow is to open and interpret each DAT independently,
enumerate and decode its textures, perform a controlled texture replacement,
rebuild the DAT, reopen the rebuilt output, and verify that unrelated binary
content and pointer relationships remain valid. The original fixture provides
a baseline; the modified fixture exercises compatibility with custom-skin data.

**Scope limitation:** this confirms the DAT header, relocation table, node and
string tables, and the two root structure layouts for each file. It does not
yet prove that DTW's entire recursive HSD tree decoder succeeds,
enumerate/decode GX textures, or rebuild either DAT. Those remain required
milestones for the native Linux port.


## Native GUI navigation preview — first iteration

The branch now includes a standalone Python 3/Tk GUI preview:
- `dtw_dat_tree.py` parses the existing HSD header/relocation/node/string
  tables and builds a read-only lazy structure-navigation model.
- `dtw_gui.py` provides File/Open/Reload, a two-column expandable tree with
  offsets, search over currently populated rows, Properties and Raw Data panes,
  and a reserved DAT Texture Tree tab.
- `run-gui-preview.sh` launches the preview without changing the main
  fail-closed `run-linux.sh` entrypoint.
- The tree follows the legacy Structural Analysis layout: File Header contains
  Relocation, Root Nodes, Reference Nodes (when present), and String Tables.
  Known `Next_Sibling` links appear as peer rows under the common parent.

Validation performed locally:
- 10 unit tests pass, including 5 new tests for the DAT tree model.
- Both user-provided Fox Green DATs load into the model and show their two root
  labels; their root branches were expanded successfully in an Xvfb GUI smoke
  test. The original extracted DAT displayed 74 immediate peer/child rows on
  its Joint root; the custom-skin DAT displayed 79.
- GUI smoke tests confirmed the root table, branch population, structure
  selection, Properties pane, and raw-data view render under Tk 8.6.

**Important scope boundary:** this is not yet the complete original HSD
recursive class-validation engine. Only a subset of common fighter model and
material-animation structures has explicit field/sibling metadata; other
nodes remain generic pointer structures. The GUI is read-only. It does not yet
enumerate or decode GX textures, preview images, import/export texture data,
save changes, or rebuild DAT files. Do not remove the main launcher guard.
