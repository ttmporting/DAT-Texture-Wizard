#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "ERROR: Python 3.11 or newer is required to build the AppImage." >&2
    exit 127
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("ERROR: AppImage build tooling requires Python 3.11 or newer.")
print("Build host Python:", sys.version.split()[0])
PY

# setuptools executes a root-level setup.py even when pyproject.toml is present.
# The original Windows setup.py used Python 2 syntax; it is archived under
# legacy/ and must not be restored at the project root.
if [[ -f "$ROOT/setup.py" ]]; then
    echo "ERROR: Root setup.py is the legacy Windows/Python 2 build script." >&2
    echo "Keep it archived as legacy/windows-setup-cxfreeze.py." >&2
    exit 2
fi

echo "== Preflight native PEP 517 wheel build =="
mkdir -p "$ROOT/build/wheel-preflight"
PIP_DISABLE_PIP_VERSION_CHECK=1 "$PYTHON_BIN" -m pip wheel \
    --no-deps \
    --wheel-dir "$ROOT/build/wheel-preflight" \
    "$ROOT"

VENV_DIR="${APPIMAGE_VENV:-$ROOT/.venv-appimage}"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install --require-hashes -r packaging/requirements-build.txt

echo "== Check AppImage build configuration =="
"$VENV_DIR/bin/python" -m appimage.ctl check

echo
echo "== Build DAT Texture Wizard AppImage =="
"$VENV_DIR/bin/python" -m appimage.ctl build

mapfile -t APPIMAGES < <(find "$ROOT/dist" -maxdepth 1 -type f -name 'DATTextureWizard-*.AppImage' -print | sort)
if [[ "${#APPIMAGES[@]}" -ne 1 ]]; then
    echo "ERROR: Expected one DATTextureWizard AppImage in dist/, found ${#APPIMAGES[@]}." >&2
    find "$ROOT/dist" -maxdepth 1 -type f -print >&2 || true
    exit 1
fi
chmod +x "${APPIMAGES[0]}"
echo
echo "AppImage created: ${APPIMAGES[0]}"
echo "Run it with: ${APPIMAGES[0]}"
