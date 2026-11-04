#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m unittest discover -s tests -v
python3 -m py_compile dtw_platform.py dtw_dat_probe.py tests/test_dtw_platform.py tests/test_dat_probe.py
