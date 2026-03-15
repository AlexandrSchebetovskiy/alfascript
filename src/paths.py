"""
paths.py — Path resolution for ALFAscript.

All filesystem path discovery lives here. Import this module early;
everything else that needs a path should import from here rather than
recomputing paths inline.
"""

import os
import sys


# ---------------------------------------------------------------------------
# Application directories
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # Running as a PyInstaller bundle
    _MEIPASS  = sys._MEIPASS
    _APP_DIR  = os.path.dirname(sys.executable)
else:
    _MEIPASS  = os.path.abspath(os.path.dirname(__file__))
    _APP_DIR  = _MEIPASS

_BASE_DIR = _APP_DIR


# ---------------------------------------------------------------------------
# multilaunch discovery
# ---------------------------------------------------------------------------

def find_multilaunch() -> str | None:
    """Locate the multilaunch folder.

    Search order:
    1. Sibling folder named ``multilaunch`` next to the exe / script.
    2. The exe / script directory itself is named ``multilaunch``.
    3. ``X:\\multilaunch`` on every drive letter C–Z.

    Returns the absolute path if found, otherwise ``None``.
    """
    base = os.path.dirname(
        sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    )

    candidate = os.path.join(base, "../multilaunch")
    if os.path.isdir(candidate):
        return candidate

    if os.path.basename(base).lower() == "multilaunch":
        return base

    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        path = f"{letter}:\\multilaunch"
        if os.path.isdir(path):
            return path

    return None


def find_scripts_dir(multilaunch: str | None) -> str | None:
    """Return the ``Scripts`` subdirectory inside *multilaunch* (case-insensitive).

    Falls back to ``multilaunch/Scripts`` (constructed path) if a
    directory scan is not possible.
    """
    if not multilaunch:
        return None
    try:
        for entry in os.listdir(multilaunch):
            if entry.lower() == "scripts":
                return os.path.join(multilaunch, entry)
    except OSError:
        pass
    return os.path.join(multilaunch, "Scripts")


def find_7zip() -> str | None:
    """Locate ``7z.exe``.

    Search order:
    1. ``_MEIPASS`` directory (bundled inside the exe).
    2. Alongside the exe / script.
    3. Standard ``Program Files`` locations.
    4. ``7z`` on ``PATH``.

    Returns the path or command string if found, otherwise ``None``.
    """
    import subprocess

    candidates: list[str] = []

    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(sys._MEIPASS, "7z.exe"))

    candidates += [
        os.path.join(_APP_DIR, "7z.exe"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]

    for c in candidates:
        if os.path.isfile(c):
            return c

    try:
        subprocess.call(
            ["7z", "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return "7z"
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Derived paths  (computed once at import time)
# ---------------------------------------------------------------------------

#: Absolute path to the multilaunch folder, or ``None`` if not found.
MULTILAUNCH: str | None = find_multilaunch()

#: Absolute path to ``multilaunch/Scripts``, or ``None``.
SCRIPTS_DIR: str | None = find_scripts_dir(MULTILAUNCH)

#: Path to ``theme.json`` — stored inside multilaunch when available,
#: otherwise falls back to the application directory.
THEME_FILE: str = (
    os.path.join(MULTILAUNCH, "dependencies", "theme.json")
    if MULTILAUNCH
    else os.path.join(_APP_DIR, "theme.json")
)

#: Path to ``components_local.json`` inside multilaunch (version tracking).
LOCAL_COMP_FILE: str = "components_local.json"