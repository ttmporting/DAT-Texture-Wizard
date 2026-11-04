"""Small, testable operating-system helpers for DAT Texture Wizard.

This module deliberately does not import Tkinter or any DTW modules. It can
therefore be tested independently while the legacy Python 2 application is
being migrated to Python 3.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

PathLike = Union[str, os.PathLike]


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def application_root(module_file: Optional[PathLike] = None,
                     argv0: Optional[PathLike] = None) -> Path:
    """Return the application directory for source and frozen execution.

    Pass __file__ from the entry-point module when running from source.
    For frozen applications, the executable's directory is authoritative.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    candidate = module_file or argv0
    if candidate:
        return Path(candidate).resolve().parent
    return Path.cwd().resolve()


def resource_path(relative_path: PathLike,
                  root: Optional[PathLike] = None) -> Path:
    """Resolve a resource relative to the app, never the current directory."""
    base = Path(root).resolve() if root is not None else application_root()
    return (base / relative_path).resolve()


def find_executable(name: str,
                    bundled_candidates: Iterable[PathLike] = (),
                    env_var: Optional[str] = None) -> Optional[str]:
    """Find a native helper, preferring an explicit override then bundled files.

    On Linux, callers should pass native executable candidates (for example
    bin/linux/pngquant), not Windows .exe paths.
    """
    if env_var:
        override = os.environ.get(env_var)
        if override:
            expanded = os.path.expanduser(override)
            if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
                return str(Path(expanded).resolve())
            located = shutil.which(override)
            if located:
                return located

    for candidate in bundled_candidates:
        candidate_path = Path(candidate).expanduser()
        if candidate_path.is_file() and os.access(str(candidate_path), os.X_OK):
            return str(candidate_path.resolve())

    return shutil.which(name)


def popen(command: Union[str, Sequence[str]], **kwargs):
    """Start a subprocess without passing Windows-only flags on Unix."""
    if is_windows():
        kwargs.setdefault(
            "creationflags",
            getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
    else:
        kwargs.pop("creationflags", None)
    return subprocess.Popen(command, **kwargs)


def open_path(path: PathLike):
    """Open a file/folder in the user's desktop default application."""
    target = str(Path(path).expanduser().resolve())
    if is_windows():
        os.startfile(target)  # type: ignore[attr-defined]
        return None
    if is_macos():
        opener = "open"
    elif is_linux():
        opener = "xdg-open"
    else:
        raise NotImplementedError("Opening paths is unsupported on this platform")

    executable = shutil.which(opener)
    if not executable:
        raise FileNotFoundError(
            "{} was not found; install the desktop integration utilities".format(opener)
        )
    return subprocess.Popen(
        [executable, target],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def set_toolwindow_if_supported(window) -> bool:
    """Apply Tk's Windows-only compact tool-window decoration when available."""
    if not is_windows():
        return False
    try:
        window.attributes("-toolwindow", 1)
    except Exception:
        return False
    return True
