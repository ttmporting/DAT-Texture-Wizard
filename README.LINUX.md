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

**This is not a runnable Linux port yet.** The original application still uses
Python 2 imports/syntax. `run-linux.sh` intentionally refuses to launch until a
`.linux-port-ready` marker is added after the migration and regression tests pass.

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
