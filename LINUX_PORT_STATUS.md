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
- 8 compatibility unit tests passed on Python 3.
- `dtw_platform.py` passed `py_compile`.

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
