# Native Linux GUI preview

This is an early native Tk GUI milestone for the `linux-port` branch. The
primary workspace is now the **Melee File Tree**, followed by Structural
Analysis and a reserved DAT Texture Tree tab. The preview supports read-only
GameCube browsing, file export, and carefully bounded staged file replacement.
It is not yet the complete DAT Texture Wizard texture editor.

## Run on Nobara 43

Tkinter is supplied by the system Python package:

```bash
sudo dnf install python3-tkinter
```

From the repository folder:

```bash
./run-gui-preview.sh
```

Open the user's Melee / GameCube image directly:

```bash
./run-gui-preview.sh "$HOME/Downloads/TM-CE - Rebuilt, v1.iso"
```

Or open one standalone DAT:

```bash
./run-gui-preview.sh "$HOME/Downloads/TMCE-dat-test-20261104-105711/P-GTME/files/PlFxGr.dat"
```

## Melee File Tree

The first tab is the main starting point, with quick links for System,
Characters, Menus, and Stages. Expand folders to browse the image's FST; it
does not load the full disc into memory.

The right-side actions follow the original DTW layout:

- **Export** — exports a selected file, or recursively exports a selected folder.
- **Import** — chooses a replacement for one selected file and stages it.
- **Browse Textures** — loads a selected DAT/USD into the DAT Texture Tree
  workspace (the actual GX texture scanner/decoder is still pending).
- **Analyze Structure** — loads a selected DAT/USD into Structural Analysis.

The File menu and right-side panel include **Save Patched ISO As…**. The
operation creates a new copy and verifies the updated FST size and extracted
replacement contents. The source ISO is never modified.

### Safe replacement limits

Current import/save support is intentionally limited to replacements that fit
inside the original file's allocated byte range before the next disc file or
FST. The FST file-size field is updated for a shorter or larger-in-padding
replacement. If the replacement would overlap another file or the FST, it is
rejected. Full ISO file relocation/rebuild (needed when a custom DAT grows
beyond its available space) is not implemented yet.

The FST browser derives directory paths from the directory next-index preorder
ranges. This tolerates noncanonical directory parent-index fields such as the
one found in the supplied TM-CE image, while reporting the discrepancy.

## Structural Analysis

The Structural Analysis tab follows the original DTW organization:

- File Header
  - Relocation Table
  - Root Nodes Table
    - Root HSD structures (expanded lazily)
  - Reference Nodes Table (when present)
  - String Table

Known `Next_Sibling` links are displayed beside siblings under their common
parent, not nested below the preceding sibling. The model includes a subset of
common fighter model and material-animation field hints; unrecognized nodes
remain browsable as generic pointer-bearing structures.

## Current limitations

- GX texture enumeration, image decoding, thumbnails, texture import/export,
  DAT save, and DAT rebuild are not enabled.
- The HSD structure model is not yet equivalent to the original recursive
  class-validation engine.
- Full ISO relocation/rebuild is not enabled; larger replacements are only
  accepted when the existing file has enough free space before the next disc
  extent/FST.
- The main `run-linux.sh` remains intentionally guarded. Use
  `run-gui-preview.sh` for this preview until the full application migration
  is complete.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile dtw_dat_probe.py dtw_dat_tree.py dtw_gamecube.py dtw_gui.py
bash -n run-gui-preview.sh
```
