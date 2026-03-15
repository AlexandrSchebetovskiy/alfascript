"""
services/programs.py — Scanning folders for launchable programs.

Provides:
- scan_programs()  — return a list of program dicts from a directory.
"""

import os


def scan_programs(
    folder: str,
    exclude_subfolders: list[str] | None = None,
) -> list[dict]:
    """Scan *folder* and return a list of launchable program entries.

    Each entry is a dict with keys:
        name  — display name (filename without extension, or folder name).
        path  — absolute path to the .exe or .msi file.
        icon  — absolute path to icon.png/ico, or None.

    Subfolders are searched for an exe/msi; a ``launch.txt`` file inside a
    subfolder can specify which executable to launch. Subfolders listed in
    *exclude_subfolders* are skipped (case-insensitive).
    """
    if exclude_subfolders is None:
        exclude_subfolders = []

    exclude_lower = {e.lower() for e in exclude_subfolders}
    programs: list[dict] = []

    if not folder or not os.path.isdir(folder):
        return programs

    try:
        for entry in sorted(os.listdir(folder)):
            if entry.lower() in exclude_lower:
                continue

            entry_path = os.path.join(folder, entry)

            # Direct file in the folder root
            if os.path.isfile(entry_path):
                ext = os.path.splitext(entry)[1].lower()
                if ext in (".exe", ".msi"):
                    programs.append({
                        "name": os.path.splitext(entry)[0],
                        "path": entry_path,
                        "icon": None,
                    })
                continue

            # Subfolder — look for exe/msi and optional icon
            if os.path.isdir(entry_path):
                exe_path  = _find_exe_in_folder(entry_path)
                icon_path = _find_icon_in_folder(entry_path)
                if exe_path:
                    programs.append({
                        "name": entry,
                        "path": exe_path,
                        "icon": icon_path,
                    })
    except OSError:
        pass

    return programs


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_icon_in_folder(folder: str) -> str | None:
    """Return the path to the first icon file found in *folder*, or None."""
    for icon_name in ("icon.png", "icon.ico", "Icon.png", "Icon.ico"):
        candidate = os.path.join(folder, icon_name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _find_exe_in_folder(folder: str) -> str | None:
    """Return the path to the executable to launch from *folder*.

    Resolution order:
    1. ``launch.txt`` inside the folder specifies the filename.
    2. First ``.exe`` or ``.msi`` found (sorted alphabetically).
    """
    # 1. launch.txt
    launch_txt = os.path.join(folder, "launch.txt")
    if os.path.isfile(launch_txt):
        try:
            with open(launch_txt, encoding="utf-8", errors="replace") as f:
                exe_name = f.read().strip()
            candidate = os.path.join(folder, exe_name)
            if os.path.isfile(candidate):
                return candidate
        except OSError:
            pass

    # 2. First exe/msi
    try:
        for f in sorted(os.listdir(folder)):
            if os.path.splitext(f)[1].lower() in (".exe", ".msi"):
                return os.path.join(folder, f)
    except OSError:
        pass

    return None
