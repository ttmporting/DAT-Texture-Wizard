# Native Linux GUI preview

This is the first native Tk GUI milestone for the `linux-port` branch. It is a
read-only navigation prototype, not a complete DAT Texture Wizard replacement.

## Run on Nobara 43

Tkinter is supplied by the system Python package:

```bash
sudo dnf install python3-tkinter
```

From the repository folder:

```bash
./run-gui-preview.sh
```

Or open a specific DAT directly:

```bash
./run-gui-preview.sh "$HOME/Downloads/TMCE-dat-test-20261104-105711/P-GTME/files/PlFxGr.dat"
```

The GUI supports **File → Open DAT**, reload, search among currently populated
rows, selection, expandable/collapsible structure branches, an offset column,
and Properties / Raw Data inspection. The left-side navigation follows the
original Structural Analysis organization:

- File Header
  - Relocation Table
  - Root Nodes Table
    - Root HSD structures (expanded lazily)
  - Reference Nodes Table (when present)
  - String Table

The tree uses the same key rule as the original viewer: known `Next_Sibling`
links are displayed beside their siblings under the common parent, not as a
nested child. The model currently has class/field hints for common fighter
model and material-animation structures; unrecognized nodes remain browsable
as generic structures.

## Current limitations

- No texture enumeration, thumbnail rendering, texture import/export, DAT save,
  or rebuild operation is enabled.
- This preview's generic graph model is not yet equivalent to the full original
  recursive HSD class-validation engine. Only a subset of structure classes
  has known field layouts and sibling metadata.
- The existing `run-linux.sh` remains intentionally guarded. Use
  `run-gui-preview.sh` for this preview until the full application migration is
  complete.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile dtw_dat_probe.py dtw_dat_tree.py dtw_gui.py
bash -n run-gui-preview.sh
```
