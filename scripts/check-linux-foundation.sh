#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Compatibility, DAT navigation, and GameCube disc tests =="
python3 -m unittest discover -s tests -v

echo
echo "== Compile Python 3 compatibility and GUI modules =="
python3 -m py_compile dtw_platform.py dtw_dat_probe.py dtw_dat_tree.py dtw_character_tree.py dtw_disc_labels.py dtw_stage_tree.py dtw_gx_texture.py dtw_gamecube.py dtw_gui.py \
    tests/test_dtw_platform.py tests/test_dat_probe.py tests/test_dat_tree_model.py tests/test_character_tree.py tests/test_disc_labels.py tests/test_stage_tree.py tests/test_gx_texture.py tests/test_gamecube_iso.py

echo
echo "== Audit remaining Python 2 / Windows-only constructs =="
python3 scripts/audit-python2.py

echo
echo "== Validate shell scripts =="
bash -n run-linux.sh
bash -n run-gui-preview.sh
bash -n scripts/install-nobara-deps.sh
bash -n scripts/run-tests.sh

echo
echo "== Verify launcher fails closed before port readiness =="
if [[ -e .linux-port-ready ]]; then
    echo "Unexpected .linux-port-ready marker in unverified checkout." >&2
    exit 1
fi
set +e
./run-linux.sh > .linux-launch-guard.log 2>&1
launcher_status=$?
set -e
cat .linux-launch-guard.log
if [[ "$launcher_status" -ne 2 ]] || ! grep -q "not launch-ready yet" .linux-launch-guard.log; then
    rm -f .linux-launch-guard.log
    echo "Launcher did not enforce its unready guard as expected." >&2
    exit 1
fi
rm -f .linux-launch-guard.log

echo
echo "Linux port foundation, DAT navigation, stage grouping, and GX texture preview checks passed."
echo "GameCube file export and copy-on-write ISO rebuilding are enabled in the preview."
echo "DAT structure navigation and GX previews are read-only; texture editing, DAT save, and full app readiness are not certified."
