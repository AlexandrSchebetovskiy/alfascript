"""
services/hardware.py — Hardware information via WMI and smartctl.

Provides:
- load_hw_info_bg()  — start background threads for WMI + SMART collection.
- get_hw_info()      — return the cached WMI data dict.
- get_smart()        — return the cached smartctl data dict.
- build_disks_payload() — combine WMI + SMART into the API response shape.
"""

import json
import logging
import os
import re
import subprocess
import threading

from src.paths import MULTILAUNCH


# ---------------------------------------------------------------------------
# PowerShell scripts (kept here, close to the code that uses them)
# ---------------------------------------------------------------------------

_PS_HW = (
    "$cpu = (Get-WmiObject Win32_Processor | Select-Object -First 1).Name.Trim();"
    "$mb = (Get-WmiObject Win32_BaseBoard | Select-Object -First 1);"
    "$mb_str = ($mb.Manufacturer.Trim() + ' ' + $mb.Product.Trim()).Trim();"
    "$ram_obj = Get-WmiObject Win32_PhysicalMemory;"
    "$ram_gb  = [math]::Round(($ram_obj | Measure-Object -Property Capacity -Sum).Sum / 1GB);"
    "$ram_mhz = ($ram_obj | Select-Object -First 1).Speed;"
    "$mem_type_code = ($ram_obj | Select-Object -First 1).SMBIOSMemoryType;"
    "$ddr = switch ($mem_type_code) { 24 {'DDR3'} 26 {'DDR4'} 34 {'DDR5'} default {'DDR?'} };"
    r'$ram_str = "${ram_gb}GB $ddr ${ram_mhz}MHz";'
    "$gpu_all = Get-WmiObject Win32_VideoController | Where-Object {"
    "  $_.Name -notmatch 'Virtual|Remote|Indirect|IDD|ParsecVDA|ZeroDisplay'"
    "};"
    "$gpu_pref = $gpu_all | Where-Object { $_.Name -match 'NVIDIA|AMD|Radeon|GeForce|Quadro|Arc' } | Select-Object -First 1;"
    "$gpu = if ($gpu_pref) { $gpu_pref.Name.Trim() }"
    "  elseif ($gpu_all) { ($gpu_all | Select-Object -First 1).Name.Trim() }"
    "  else { '---' };"
    "$sys_drive_letter = $env:SystemDrive.TrimEnd(':');"
    "$ldtp = Get-WmiObject Win32_LogicalDiskToPartition;"
    "$sys_part = $ldtp | Where-Object { ($_.Dependent -split([char]34))[1] -eq ($sys_drive_letter+':') };"
    "$sys_disk_idx = if ($sys_part) { ($sys_part.Antecedent -split 'Disk #')[1].Split(',')[0] } else { '0' };"
    "$all_disks = Get-WmiObject Win32_DiskDrive | Sort-Object Index;"
    "$msft_disks = Get-WmiObject -Namespace root\\Microsoft\\Windows\\Storage -Class MSFT_PhysicalDisk -ErrorAction SilentlyContinue;"
    "$disk_letters = @{};"
    "foreach ($lp in $ldtp) {"
    "  $didx = ($lp.Antecedent -split 'Disk #')[1].Split(',')[0];"
    "  $letter = ($lp.Dependent -split([char]34))[1];"
    "  if (-not $disk_letters.ContainsKey($didx)) { $disk_letters[$didx] = @() };"
    "  $disk_letters[$didx] += $letter"
    "};"
    "function Get-MediaStr($disk) {"
    "  $mt = 'UNK';"
    "  if ($disk.MediaType -match 'SSD|Solid') { $mt = 'SSD' }"
    "  elseif ($msft_disks) {"
    "    $md = $msft_disks | Where-Object { $_.FriendlyName -eq $disk.Model };"
    "    if ($md) { $mt = switch ($md.MediaType) { 4 {'SSD'} 3 {'HDD'} 5 {'NVMe'} default {'UNK'} } }"
    "  };"
    "  $gb = [math]::Round($disk.Size / 1GB);"
    "  $model = $disk.Model.Trim();"
    r'  $model = ($model -replace "(?i)\b(SSD|HDD|NVMe|Hard Drive|Solid State)\b","") -replace "\s+"," ";'
    r'  return "${gb}GB $mt ($model)"'
    "};"
    "$disk_lines = @(); $other_lines = @();"
    "foreach ($d in $all_disks) {"
    "  $info = Get-MediaStr $d;"
    "  $idx = [string]$d.Index;"
    "  if ($d.Index -eq [int]$sys_disk_idx) { $disk_lines += '[C:] ' + $info }"
    "  else {"
    "    $letters = $disk_letters[$idx];"
    "    $label = if ($letters) { '[' + ($letters -join ',') + ']' } else { '' };"
    "    $other_lines += if ($label) { $label + ' ' + $info } else { $info }"
    "  }"
    "};"
    "$all_disk_str = ($disk_lines + $other_lines) -join '~';"
    "$bios_obj = Get-WmiObject Win32_BIOS | Select-Object -First 1;"
    "$bios_date = '';"
    r"if ($bios_obj.ReleaseDate -match '^(\d{4})(\d{2})(\d{2})') { $bios_date = $Matches[3] + '.' + $Matches[2] + '.' + $Matches[1] };"
    r'Write-Output "CPU=$cpu|MB=$mb_str|RAM=$ram_str|GPU=$gpu|DISKS=$all_disk_str|BIOS=$bios_date"'
)


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_hw_info:  dict       = {}    # WMI data — populated by _fetch_hw_info_ps()
_hw_smart: dict | None = None  # smartctl data — None = not yet run


def get_hw_info() -> dict:
    """Return the cached WMI hardware info dict."""
    return _hw_info


def get_smart() -> dict | None:
    """Return the cached smartctl data dict (None if not yet collected)."""
    return _hw_smart


# ---------------------------------------------------------------------------
# Background initialisation
# ---------------------------------------------------------------------------

def load_hw_info_bg() -> None:
    """Start background threads to collect WMI data and SMART data."""
    threading.Thread(target=_fetch_hw_info_ps, daemon=True).start()
    threading.Thread(target=_fetch_smart,       daemon=True).start()


# ---------------------------------------------------------------------------
# WMI via PowerShell
# ---------------------------------------------------------------------------

def _fetch_hw_info_ps() -> None:
    global _hw_info
    out  = _run_ps(_PS_HW, timeout=20)
    info = {}
    for part in out.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            info[k.strip()] = v.strip()
    _hw_info = info


# ---------------------------------------------------------------------------
# SMART via smartctl
# ---------------------------------------------------------------------------

def _fetch_smart() -> None:
    global _hw_smart

    if not MULTILAUNCH:
        _hw_smart = {}
        return

    smartctl = os.path.join(MULTILAUNCH, "dependencies", "smartctl", "smartctl.exe")
    if not os.path.isfile(smartctl):
        _hw_smart = {}
        return

    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0

    # --scan returns devices with correct -d flags
    try:
        scan = subprocess.run(
            [smartctl, "--scan"], capture_output=True, text=True,
            timeout=10, startupinfo=si,
        )
        scan_lines = [l for l in scan.stdout.splitlines() if l.strip()]
    except Exception as e:
        logging.warning("[hardware] smartctl scan failed: %s", e)
        _hw_smart = {}
        return

    devices = []
    for line in scan_lines:
        parts = line.split()
        if not parts:
            continue
        dev   = parts[0]
        dtype = None
        for j, p in enumerate(parts):
            if p == "-d" and j + 1 < len(parts):
                dtype = parts[j + 1]
                break
        devices.append((dev, dtype))

    # WMI: model → drive letters mapping
    ps_models = (
        "$ldtp = Get-WmiObject Win32_LogicalDiskToPartition;"
        "$map = @{};"
        "foreach ($lp in $ldtp) {"
        "  $didx = ($lp.Antecedent -split 'Disk #')[1].Split(',')[0];"
        "  $letter = ($lp.Dependent -split([char]34))[1];"
        "  if (-not $map.ContainsKey($didx)) { $map[$didx] = @() };"
        "  $map[$didx] += $letter"
        "};"
        "$drives = Get-WmiObject Win32_DiskDrive | Sort-Object Index;"
        "foreach ($d in $drives) {"
        "  $idx = [string]$d.Index;"
        "  $lets = if ($map.ContainsKey($idx)) { ($map[$idx]) -join ',' } else { '' };"
        "  $model = $d.Model.Trim();"
        "  Write-Output ($lets + '|' + $model)"
        "}"
    )
    letter_by_model: dict[str, list[str]] = {}
    for line in _run_ps(ps_models, timeout=10).splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        lets_s, model_wmi = line.split("|", 1)
        letters = [x.strip() for x in lets_s.split(",") if x.strip()]
        nm      = re.sub(r"\s+", " ", model_wmi.strip().lower())
        letter_by_model[nm] = letters

    result: dict = {}
    seen_devs: set = set()

    for dev, dtype in devices:
        if dev in seen_devs:
            continue
        cmd = [smartctl, "-a", "-j", dev]
        if dtype:
            cmd += ["-d", dtype]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15, startupinfo=si,
            )
            data = json.loads(proc.stdout)
        except Exception:
            continue

        model  = data.get("model_name") or data.get("model_family") or ""
        ss     = data.get("smart_status", {})
        health = (
            "good"    if ss.get("passed") is True
            else "bad" if ss.get("passed") is False
            else "unknown"
        )
        temp  = _smart_temp(data)
        hours = _smart_hours(data)
        pct   = _smart_pct(data)

        if not model:
            continue

        letters = _match_letters(model, letter_by_model, result)
        key     = letters[0] if letters else f"__dev_{dev}__"
        result[key] = {
            "model":  model,
            "health": health,
            "pct":    pct,
            "temp":   temp,
            "hours":  hours,
        }
        seen_devs.add(dev)

    _hw_smart = result


# ---------------------------------------------------------------------------
# Disk payload builder (used by /api/hw_info route)
# ---------------------------------------------------------------------------

def build_disks_payload() -> list[dict]:
    """Combine WMI disk strings with SMART data into a list for the API."""
    disks_raw    = _hw_info.get("DISKS", "")
    disk_entries = [d.strip() for d in disks_raw.split("~") if d.strip()]
    smart        = _hw_smart or {}
    disks_out    = []

    for i, d in enumerate(disk_entries):
        disk_letter = None
        lm = re.search(r"\[([A-Z]:)", d)
        if lm:
            disk_letter = lm.group(1)

        s = smart.get(disk_letter) if disk_letter else None

        if s is None:
            for k, v in smart.items():
                if isinstance(k, int):
                    used = any(
                        smart.get(l2) is v
                        for l2 in smart
                        if isinstance(l2, str) and not l2.startswith("__")
                    )
                    if not used:
                        s = v
                        break

        if s is None and f"__dev{i}__" in smart:
            s = smart.get(f"__dev{i}__")

        disks_out.append({
            "label":  f"Диск {i + 1}" if i > 0 else "Диск",
            "info":   d,
            "health": s["health"] if s else None,
            "pct":    s["pct"]    if s else None,
            "temp":   s["temp"]   if s else None,
            "hours":  s["hours"]  if s else None,
        })

    return disks_out


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _run_ps(script: str, timeout: int = 20) -> str:
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout, startupinfo=si,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _smart_temp(data: dict) -> int | None:
    temp_o = data.get("temperature", {})
    if isinstance(temp_o.get("current"), (int, float)):
        return int(temp_o["current"])
    return None


def _smart_hours(data: dict) -> int | None:
    pot = data.get("power_on_time", {})
    if isinstance(pot.get("hours"), (int, float)):
        return int(pot["hours"])
    return None


def _smart_pct(data: dict) -> int | None:
    nvme_l = data.get("nvme_smart_health_information_log", {})
    if isinstance(nvme_l.get("percentage_used"), (int, float)):
        return max(0, 100 - int(nvme_l["percentage_used"]))

    wear_names = {
        "Wear_Leveling_Count", "Media_Wearout_Indicator",
        "Percent_Lifetime_Remain", "Available_Reservd_Space",
        "SSD_Life_Left", "Remaining_Lifetime_Perc",
    }
    wear_ids = {173, 177, 231, 232, 233, 241}
    for attr in data.get("ata_smart_attributes", {}).get("table", []):
        if attr.get("name", "") in wear_names or attr.get("id", 0) in wear_ids:
            val = attr.get("value") or attr.get("raw", {}).get("value")
            if isinstance(val, (int, float)) and 0 <= val <= 100:
                return int(val)
    return None


def _match_letters(
    model: str,
    letter_by_model: dict[str, list[str]],
    result: dict,
) -> list[str] | None:
    """Find drive letters for a smartctl model string via WMI model map."""
    nm      = re.sub(r"\s+", " ", model.strip().lower())
    letters = letter_by_model.get(nm)

    if letters is None:
        for wmi_m, lets in letter_by_model.items():
            if nm in wmi_m or wmi_m in nm:
                letters = lets
                break

    if letters is None:
        used = set(result.keys())
        for lets in letter_by_model.values():
            key_try = lets[0] if lets else None
            if key_try and key_try not in used:
                letters = lets
                break

    return letters
