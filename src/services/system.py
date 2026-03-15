"""
services/system.py — OS-level helpers.

Covers: admin rights, UAC, Windows Defender exclusions,
network connectivity, OS version string.

No Flask, no _state mutations. All functions are pure or have
clearly documented side-effects (registry writes, PowerShell calls).
"""

import ctypes
import os
import subprocess
import sys
import time
import threading

from src.paths import _APP_DIR, _MEIPASS, MULTILAUNCH


# ---------------------------------------------------------------------------
# Admin rights
# ---------------------------------------------------------------------------

def is_admin() -> bool:
    """Return True if the current process has administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_as_admin() -> None:
    """Re-launch the current process with UAC elevation, then exit."""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit()


# ---------------------------------------------------------------------------
# OS version
# ---------------------------------------------------------------------------

def get_os_version() -> str:
    """Return a human-readable Windows version string, e.g. 'Windows 11 (23H2)'."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        )

        def _rv(name):
            try:
                return winreg.QueryValueEx(key, name)[0]
            except Exception:
                return None

        major   = _rv("CurrentMajorVersionNumber")
        build   = int(_rv("CurrentBuildNumber") or 0)
        display = _rv("DisplayVersion") or _rv("ReleaseId") or ""
        winreg.CloseKey(key)

        if major is not None:
            ver = "11" if int(major) >= 10 and build >= 22000 else str(major)
            return f"Windows {ver} ({display})" if display else f"Windows {ver}"
    except Exception:
        pass
    return "Windows"


# ---------------------------------------------------------------------------
# UAC
# ---------------------------------------------------------------------------

def get_uac_status() -> str:
    """Return 'Включён' or 'Выключен'.

    UAC is considered disabled when:
    - EnableLUA == 0  (fully disabled), OR
    - ConsentPromptBehaviorAdmin == 0  (slider at minimum — never notify)
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
        )
        enable_lua = winreg.QueryValueEx(key, "EnableLUA")[0]
        try:
            consent = winreg.QueryValueEx(key, "ConsentPromptBehaviorAdmin")[0]
        except FileNotFoundError:
            consent = 2  # default — prompt
        winreg.CloseKey(key)

        if enable_lua == 0 or consent == 0:
            return "Выключен"
        return "Включён"
    except Exception:
        return "—"


def disable_uac() -> tuple[bool, str]:
    """Set ConsentPromptBehaviorAdmin=0 (slider to minimum).

    Returns (success, error_message). On success error_message is ''.
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "ConsentPromptBehaviorAdmin", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        return True, ""
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Windows Defender exclusions
# ---------------------------------------------------------------------------

def _defender_target_paths() -> list[str]:
    """Return the list of folders that should be excluded from Defender scans."""
    return [p for p in (_APP_DIR, _MEIPASS) if p]


def _is_path_excluded(excl_lower: str, target: str) -> bool:
    """Return True if *target* (or any parent) is covered by *excl_lower*.

    Args:
        excl_lower: Pipe-separated list of excluded paths, already lowercased.
        target:     Path to check.
    """
    t = target.rstrip("\\").lower()
    for p in excl_lower.split("|"):
        p = p.strip().rstrip("\\")
        if not p:
            continue
        if t == p or t.startswith(p + "\\"):
            return True
    return False


def get_defender_exclusion_status() -> str:
    """Return the Defender exclusion status for the target paths.

    Returns one of: 'Добавлены', 'Частично', 'Не добавлены', 'Отключён', '—'.
    """
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                "(Get-MpPreference).ExclusionPath -join '|'",
            ],
            capture_output=True, text=True, timeout=8, startupinfo=si,
        )
        stderr = result.stderr.strip().lower()
        if "800106ba" in stderr or "800106b5" in stderr:
            return "Отключён"
        if result.returncode != 0:
            return "—"

        excl     = result.stdout.strip().lower()
        paths    = _defender_target_paths()
        statuses = [_is_path_excluded(excl, p) for p in paths]

        if all(statuses):
            return "Добавлены"
        if any(statuses):
            return "Частично"
        return "Не добавлены"
    except Exception:
        return "—"


def apply_defender_exclusions() -> tuple[bool, str, bool]:
    """Add the target paths to Defender's exclusion list.

    Returns ``(ok, message, disabled)`` where:
    - ``ok``       — True on success.
    - ``message``  — On success: comma-joined added paths. On failure: error text.
    - ``disabled`` — True when Defender is not running (not an error).
    """
    if not is_admin():
        return False, "Требуются права администратора", False

    try:
        paths  = _defender_target_paths()
        ps_cmd = "; ".join(f'Add-MpPreference -ExclusionPath "{p}"' for p in paths)
        si     = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        result = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15, startupinfo=si,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "800106ba" in stderr.lower() or "800106b5" in stderr.lower():
                return False, "Defender отключён на этой системе", True
            return False, stderr or "неизвестная ошибка PowerShell", False
        return True, ", ".join(paths), False
    except Exception as e:
        return False, str(e), False


# ---------------------------------------------------------------------------
# Network status  (runs in a background thread, result cached in module var)
# ---------------------------------------------------------------------------

_net_status: str = "..."


def get_net_status() -> str:
    """Return the last cached network status string."""
    return _net_status


def start_net_monitor() -> None:
    """Start a background thread that pings ya.ru every 30 seconds."""
    threading.Thread(target=_net_monitor_loop, daemon=True).start()


def _net_monitor_loop() -> None:
    global _net_status
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    while True:
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "2000", "ya.ru"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=si,
            )
            _net_status = "Подключена" if result.returncode == 0 else "Нет связи"
        except Exception:
            _net_status = "Нет связи"
        time.sleep(30)


# ---------------------------------------------------------------------------
# SDI driver date
# ---------------------------------------------------------------------------

def get_sdi_date() -> str | None:
    """Return a string like 'от 03.2026' based on the newest file in SDI drivers dir."""
    if not MULTILAUNCH:
        return None
    drivers_dir = os.path.join(MULTILAUNCH, "SDI_RUS", "drivers")
    if not os.path.isdir(drivers_dir):
        return None
    try:
        latest_mtime = None
        for entry in os.scandir(drivers_dir):
            if entry.is_file(follow_symlinks=False):
                mtime = entry.stat().st_mtime
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
        if latest_mtime:
            from datetime import datetime
            dt = datetime.fromtimestamp(latest_mtime)
            return f"от {dt.month:02d}.{dt.year}"
    except Exception:
        pass
    return None
