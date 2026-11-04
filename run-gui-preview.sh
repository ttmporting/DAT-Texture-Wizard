#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: python3 was not found." >&2
  exit 127
fi
if ! "$PYTHON_BIN" -c 'import tkinter' >/dev/null 2>&1; then
  echo "ERROR: Tkinter is missing. On Nobara/Fedora install it with:" >&2
  echo "  sudo dnf install python3-tkinter" >&2
  exit 2
fi
exec "$PYTHON_BIN" "$SCRIPT_DIR/dtw_gui.py" "$@"
