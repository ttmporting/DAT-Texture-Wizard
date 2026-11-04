#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$ROOT/.linux-port-ready" ]]; then
    echo "DAT Texture Wizard Linux port is not launch-ready yet." >&2
    echo "The upstream source still contains Python 2 syntax and Windows-only calls." >&2
    echo "Follow the migration status in README.LINUX.md." >&2
    exit 2
fi

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python3"
fi
exec "$PYTHON" "$ROOT/DAT Texture Wizard.py" "$@"
