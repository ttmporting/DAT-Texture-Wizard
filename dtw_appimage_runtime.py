"""Runtime path helpers for relocatable Linux distributions such as AppImage."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_bundled_tcl_tk() -> None:
    """Point bundled Python/Tk at Tcl/Tk scripts shipped under sys.prefix."""
    if not os.environ.get("APPDIR"):
        return
    library_root = Path(sys.prefix) / "lib"
    tcl_dirs = sorted(library_root.glob("tcl*"))
    tk_dirs = sorted(library_root.glob("tk*"))
    tcl_dir = next((path for path in tcl_dirs if (path / "init.tcl").is_file()), None)
    tk_dir = next((path for path in tk_dirs if (path / "tk.tcl").is_file()), None)
    if tcl_dir:
        os.environ["TCL_LIBRARY"] = str(tcl_dir)
    if tk_dir:
        os.environ["TK_LIBRARY"] = str(tk_dir)
