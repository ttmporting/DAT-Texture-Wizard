# DAT Texture Wizard — Linux port (Nobara 43 / Fedora family)

This branch is the native Linux porting track for upstream DAT Texture Wizard
v6.1.4. The original upstream source and Windows launch/build files are being
kept intact while portability work is introduced incrementally.

## Current status

- [x] Establish a dedicated `linux-port` branch from the v6.1.4 baseline.
- [x] Add an isolated OS compatibility module (`dtw_platform.py`).
- [x] Add unit tests for paths, helper discovery, subprocess flags, and Tk window attributes.
- [x] Add a Fedora/Nobara dependency installer and Python requirements file.
- [ ] Migrate the application and every supporting module from Python 2 to Python 3.
- [ ] Replace the legacy Windows TkDND loader with `tkinterdnd2` and graceful fallback.
- [ ] Replace hard-coded `.exe` helper paths with native `pngquant` and `wimgt` discovery.
- [ ] Verify DAT parsing/rebuilding and TPL encode/decode against fixtures.
- [ ] Enable the Linux launcher and produce an AppImage/RPM package.

The native Python 3 GUI preview is now runnable and supports the tested Melee
DAT texture replacement and copy-on-write ISO rebuild workflow. The original
upstream Windows/Python 2 application is **not yet fully migrated**;
`run-linux.sh` intentionally remains guarded. The AppImage packages the native
GUI preview only, not the still-unported legacy application.

## Nobara 43 setup

```bash
git switch linux-port
bash scripts/install-nobara-deps.sh
```

The installer uses the system package manager for Python/Tk and desktop
utilities, then installs Python dependencies into `.venv`. It does not install
or execute Windows binaries. The `wimgt` helper (from Wiimm's SZS Toolset) must
be installed separately and added to `PATH`; it is required only for CMPR
(texture type 14) encoding.

## Development checks

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile dtw_platform.py
```

The tests intentionally cover the compatibility layer independently of the
legacy application so that OS-specific behavior can be stabilized before the
large Python 2 codebase is migrated.

## Porting rules

1. Treat DAT/TPL payloads as bytes. Do not apply text encoding/decoding to
   binary buffers except at explicit string-table boundaries.
2. Keep Windows behavior working where practical; do not remove upstream
   `.bat`, `.exe`, or Windows packaging assets as part of Linux changes.
3. Never shell-quote a user-controlled path manually. Prefer argument lists
   with `subprocess` and `shell=False`.
4. Keep Linux settings/cache/output paths separate from the source checkout
   when appropriate, using XDG directories in a later packaging step.
5. Do not mark the port ready until texture and DAT round-trip tests pass.


## Native GUI navigation preview

A read-only native Tk preview now provides the original Structural Analysis
navigation pattern (File Header, relocation/root/reference/string tables, and
expandable HSD structure branches). It is an early GUI milestone, not yet the
full texture editor. Install Tkinter and start it with:

```bash
sudo dnf install python3-tkinter
./run-gui-preview.sh
```

Open a DAT immediately by passing its path to the launcher. See
[`README.GUI.LINUX.md`](README.GUI.LINUX.md) for details and current limitations.
The main `run-linux.sh` remains guarded until the entire application and binary
round-trip tests are complete.


The native GUI preview now opens to a Melee-oriented GameCube **Melee File Tree**
with System / Characters / Menus / Stages shortcuts and right-side Export,
Import, Browse Textures, and Analyze Structure actions. File export is active.
Import stages an existing-file replacement; **Rebuild / Save ISO As…** relocates
the FST and repacks all FST files, so oversized replacements are supported
within the 32-bit GameCube address limit. The DAT Texture Tree now discovers
and decodes GX image/palette records into a visual PNG gallery, supports
fixed-size PNG-to-GX texture replacement, and saves edited DAT copies. General
DAT structure editing and rebuilding remain in development.
See [README.GUI.LINUX.md](README.GUI.LINUX.md).

## AppImage distribution

The current native GUI preview has an AppImage packaging target. It bundles a
standalone Python/Tcl/Tk runtime and the required native Linux modules:

```bash
bash scripts/build-appimage.sh
```

The initial artifact targets x86_64 glibc-based desktop Linux. Distro coverage,
older glibc systems, musl/Alpine, and ARM builds require separate validation
or builds. See [README.GUI.LINUX.md](README.GUI.LINUX.md) for launching,
FUSE fallback, and the automated build workflow.
