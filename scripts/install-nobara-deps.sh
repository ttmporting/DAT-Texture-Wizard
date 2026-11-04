#!/usr/bin/env bash
set -euo pipefail

if ! command -v dnf >/dev/null 2>&1; then
    echo "This installer expects a Fedora-derived distribution with dnf." >&2
    exit 1
fi

sudo dnf install -y \
    python3 \
    python3-pip \
    python3-tkinter \
    git \
    pngquant \
    xdg-utils

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-linux.txt

echo
echo "System and Python dependencies installed."
echo "NOTE: the upstream DTW entry point still requires the planned Python 2-to-3 migration."
echo "The application is not launch-ready yet; see README.LINUX.md."
