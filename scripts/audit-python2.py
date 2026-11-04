#!/usr/bin/env python3
"""Report common Python 2 and Windows-specific constructs in DTW source.

This is a lightweight inventory, not a parser or proof of Python 3 readiness.
Run from the repository root: python3 scripts/audit-python2.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SOURCE_FILES = (
    "DAT Texture Wizard.py", "GuiSubComponents.py", "hsdFiles.py",
    "hsdStructures.py", "RenderEngine.py", "tplCodec.py", "newTkDnD.py",
    "png.py",
)
PATTERNS = {
    "python2_print_statement": re.compile(r"^[ \t]*print[ \t]+(?!\()(?=\S)", re.M),
    "python2_xrange": re.compile(r"\bxrange\s*\("),
    "python2_long_constructor": re.compile(r"\blong\s*\("),
    "python2_raw_input": re.compile(r"\braw_input\s*\("),
    "python2_has_key": re.compile(r"\.has_key\s*\("),
    "python2_basestring": re.compile(r"\bbasestring\b"),
    "legacy_tk_or_config_import": re.compile(
        r"^[ \t]*(?:import[ \t]+(?:Tkinter|tkFont|tkMessageBox|tkFileDialog|ttk|ConfigParser)"
        r"|from[ \t]+(?:Tkinter|ScrolledText|tkColorChooser|cStringIO|StringIO|sets)"
        r")", re.M,
    ),
    "windows_startfile": re.compile(r"\bos\.startfile\b"),
    "windows_creationflags": re.compile(r"\bcreationflags\s*="),
    "windows_exe_helper_reference": re.compile(r"['\"][^'\"]+\.exe['\"]", re.I),
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    report = {}
    for name in SOURCE_FILES:
        path = root / name
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        report[name] = {
            "lines": len(source.splitlines()),
            **{label: len(pattern.findall(source))
               for label, pattern in PATTERNS.items()},
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
