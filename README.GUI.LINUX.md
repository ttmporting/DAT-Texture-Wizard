# Native Linux GUI preview

This is an early native Tk GUI milestone for the `linux-port` branch. The
primary workspace is the **Melee File Tree**, followed by Structural Analysis
and a reserved DAT Texture Tree tab. The preview supports GameCube disc
browsing, file export, staged file replacement, and a verified full ISO
rebuild to a new output image. It is not yet the complete DAT Texture Wizard
texture editor.

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

The **Characters** branch is a presentation-only view that groups Melee
`PlXX…` character DAT/USD files under expandable fighter folders (for example,
all `PlFx…` files appear under **Fox**). Individual leaves resolve to their
original FST entries, so imports, exports, and rebuilds retain the true disc
path. The original on-disc folder hierarchy remains available alongside this
logical grouping; no directory entries are added to the ISO.

The **Stages** branch is also virtual. It groups recognizable stage files into
named stage folders, with separate **Target Tests**, **1P Mode**, and
**Other Stage Files** categories. The original FST tree is still available,
and each virtual file row resolves to its original ISO entry.

The **Affects / Description** column uses the filename lookup conventions from
upstream DTW v6.1.4. For example, `PlFxGr.dat` is labeled **Fox's green
costume**, `PlFx.dat` is Fox's NTSC data/shared textures, and known stage
files are labeled with their stage names. Known special 20XX variants are
included. Dynamic Random Neutrals names read from a mod's live CSS data are
not yet resolved, so those currently fall back to their base stage label.
These are filename-based descriptions, not results from decoding the DAT's
embedded texture pixels.

The right-side actions follow the original DTW layout:

- **Export** — exports a selected file, or recursively exports a selected folder.
- **Import** — stages a replacement for one selected file. The source ISO is
  unchanged.
- **Browse Textures** — loads a selected DAT/USD into the DAT Texture Tree
  workspace (the actual GX texture scanner/decoder is still pending).
- **Analyze Structure** — loads a selected DAT/USD into Structural Analysis.

Use **Rebuild / Save ISO As…** after staging one or more replacements. The
operation creates a new image copy, relocates the FST, repacks every
FST-listed file at 0x20-byte boundaries, updates the boot header's FST offset,
size, and maximum-size fields, and verifies all copied/replaced file hashes.
The source ISO is never modified.

### Fox custom-skin import walkthrough

To test the larger TAILS DAT against the supplied TM-CE image:

1. Open `TM-CE - Rebuilt, v1.iso` in the Melee File Tree.
2. Search for `PlFxGr.dat` and select the matching file under
   `P-GTME/files`.
3. Click **Import** and select `PlFxGr-TAILS.dat`.
4. Click **Rebuild / Save ISO As…** and save under a new name, for example
   `TM-CE - Rebuilt, v1 - TAILS.iso`.
5. Wait for the verified rebuild to complete, then test the new image in
   Dolphin. Keep the original ISO and original DAT as untouched backups.

The rebuild copies the disc's system prefix, fixes the anomalous directory
parent fields by rebuilding the FST hierarchy, and repacks the complete FST
file set. Do not test by overwriting the original disc image.

### Full rebuild behavior and safety boundaries

The rebuilt image retains the original boot header, BI2, apploader, and DOL
region at their original offsets. A new FST is written after the DOL, followed
by all files listed by the FST in table order. Directory entries and the name
string table are retained; file offsets and sizes are updated.

The rebuild supports replacements larger or smaller than their original
allocation, including custom DATs such as the larger TAILS Fox skin. The
output is created as a temporary file, reopened, and verified before it is
atomically renamed to the destination. The original ISO is never overwritten.

The implementation is conservative:
- The source must have a readable GameCube boot header, FST, and DOL extent.
- File offsets and sizes must fit the 32-bit GameCube FST fields (4 GiB limit).
- Replacing the boot DOL itself is not supported.
- This rebuild preserves existing FST entries and their directory/string table
  content. It does not add/remove/rename files or create directories.
- The actual TM-CE image has not yet been exercised end-to-end in the GUI. The
  FST reader was written to recover paths from directory preorder ranges and
  to report parent-index inconsistencies encountered in that image.

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
- Full ISO rebuilding currently supports replacing existing FST-listed files
  only. It does not yet support new files, directory edits, or replacing the
  boot DOL.
- The native GUI remains a focused preview, not the original complete DTW
  feature set. The main `run-linux.sh` remains intentionally guarded. Use
  `run-gui-preview.sh` until the full application migration is complete.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile dtw_dat_probe.py dtw_dat_tree.py dtw_gamecube.py dtw_gui.py
bash -n run-gui-preview.sh
```
