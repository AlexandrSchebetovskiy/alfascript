"""
services/aida.py — AIDA64 report parsing.

Provides:
- find_latest_aida_csv()      — locate the most recent stat CSV in TEMP.
- find_latest_aida_log_csv()  — locate the most recent log CSV in TEMP.
- parse_aida_stat_csv()       — parse temperatures / power from a stat CSV.
- detect_cpu_throttle()       — detect throttling events in a log CSV.
"""

import glob
import logging
import os
from datetime import datetime


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _aida_temp_dirs() -> list[str]:
    dirs = [r"C:\Windows\Temp"]
    for key in ("TEMP", "TMP"):
        v = os.environ.get(key, "")
        if v and os.path.isdir(v) and v not in dirs:
            dirs.append(v)
    return dirs


def find_latest_aida_csv() -> str | None:
    """Return the path to the most recently modified AIDA64 stat CSV, or None."""
    files = []
    for d in _aida_temp_dirs():
        files.extend(glob.glob(os.path.join(d, "aida64_sst_*_stat.csv")))
    return max(files, key=os.path.getmtime) if files else None


def find_latest_aida_log_csv() -> str | None:
    """Return the path to the most recently modified AIDA64 log CSV, or None."""
    files = []
    for d in _aida_temp_dirs():
        files.extend(glob.glob(os.path.join(d, "aida64_sst_*_log.csv")))
    return max(files, key=os.path.getmtime) if files else None


# ---------------------------------------------------------------------------
# Stat CSV parser
# ---------------------------------------------------------------------------

def parse_aida_stat_csv(csv_file: str) -> dict | None:
    """Parse an AIDA64 statistics CSV and return a results dict.

    Returns ``None`` if the file cannot be parsed or contains no useful data.

    Result keys:
        cpu_max, gpu_max, gpu_hotspot_max, vrm_max,
        cpu_power_max, throttle (None — set later by detect_cpu_throttle),
        duration.
    """
    try:
        text = _read_csv(csv_file)
        if not text:
            return None

        lines = text.splitlines()
        if len(lines) < 9:
            return None

        def cell(line, i):
            parts = line.split(";")
            return parts[i].strip() if i < len(parts) else ""

        def pf(s):
            try:
                return float(s.replace(",", "."))
            except (ValueError, AttributeError):
                return None

        # Duration
        start_str = cell(lines[4], 1) if len(lines) > 4 else ""
        end_str   = cell(lines[5], 1) if len(lines) > 5 else ""
        duration  = _parse_duration(start_str, end_str)

        result = {
            "cpu_max":         None,
            "gpu_max":         None,
            "gpu_hotspot_max": None,
            "vrm_max":         None,
            "cpu_power_max":   None,
            "throttle":        None,
            "duration":        duration,
        }

        cpu_cands   = []
        gpu_val     = None
        gpu_hotspot = None
        vrm_val     = None
        cpu_power   = None

        for line in lines[8:]:
            if not line.strip():
                continue
            name = cell(line, 0).lower()
            unit = cell(line, 1)
            mx   = pf(cell(line, 5))

            if unit == "°C":
                if name in ("цп диод", "cpu diode"):
                    cpu_cands.append((0, mx))
                elif name in ("цп", "cpu"):
                    cpu_cands.append((1, mx))
                elif name in ("графический процессор", "gpu"):
                    if gpu_val is None or (mx and mx > gpu_val):
                        gpu_val = mx
                elif "hotspot" in name:
                    if gpu_hotspot is None or (mx and mx > gpu_hotspot):
                        gpu_hotspot = mx
                elif name in ("mos", "vrm", "дроссели"):
                    if vrm_val is None or (mx and mx > vrm_val):
                        vrm_val = mx
            elif unit == "W":
                if name in ("весь цп", "cpu power", "cpu package power"):
                    if cpu_power is None or (mx and mx > cpu_power):
                        cpu_power = mx

        if cpu_cands:
            cpu_cands.sort(key=lambda x: (x[0], -(x[1] or 0)))
            result["cpu_max"] = int(cpu_cands[0][1]) if cpu_cands[0][1] else None

        result["gpu_max"]         = int(gpu_val)     if gpu_val     else None
        result["gpu_hotspot_max"] = int(gpu_hotspot) if gpu_hotspot else None
        result["vrm_max"]         = int(vrm_val)     if vrm_val     else None
        result["cpu_power_max"]   = int(cpu_power)   if cpu_power   else None

        if result["cpu_max"] is None and result["gpu_max"] is None:
            return None

        return result
    except Exception as e:
        logging.warning("[aida] parse_aida_stat_csv failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Throttle detection
# ---------------------------------------------------------------------------

def detect_cpu_throttle(log_file: str) -> str | None:
    """Detect CPU throttling events in an AIDA64 log CSV.

    Returns 'TEMP', 'VRM', or None.
    """
    try:
        text = _read_csv(log_file)
        if not text:
            return None

        lines = text.splitlines()
        if len(lines) < 10:
            return None

        cpu_line = lines[1].lower() if len(lines) > 1 else ""
        is_intel = "intel" in cpu_line
        CPU_THROTTLE_TEMP = 97.0 if is_intel else 92.0

        headers = lines[6].split(";")
        units   = lines[7].split(";")

        def find_col(name, unit):
            for i, (h, u) in enumerate(zip(headers, units)):
                if h.strip() == name and u.strip() == unit:
                    return i
            return None

        col_load = find_col("ЦП", "%")
        col_temp = (
            find_col("ЦП диод", "°C") if not is_intel else find_col("ЦП", "°C")
        )
        if col_temp is None:
            col_temp = find_col("ЦП", "°C")

        core_cols = [
            i for i, (h, u) in enumerate(zip(headers, units))
            if "Частота ядра ЦП" in h and u.strip() == "MHz"
        ]
        if not core_cols:
            agg = find_col("ЦП", "MHz")
            if agg:
                core_cols = [agg]

        if col_load is None or not core_cols:
            return None

        def val(row, col):
            if col is None or col >= len(row):
                return None
            try:
                return float(row[col].strip().replace(",", "."))
            except (ValueError, AttributeError):
                return None

        samples = []
        for line in lines[8:]:
            if not line.strip():
                continue
            row  = line.split(";")
            load = val(row, col_load)
            if load is None or load < 90:
                continue
            freqs = [val(row, c) for c in core_cols]
            freqs = [f for f in freqs if f and f > 100]
            if not freqs:
                continue
            samples.append((sum(freqs) / len(freqs), val(row, col_temp)))

        if not samples:
            return None

        sorted_f = sorted(s[0] for s in samples)
        p90      = sorted_f[max(0, int(len(sorted_f) * 0.9) - 1)]
        thresh   = p90 * 0.8

        for avg_f, temp in samples:
            if avg_f < thresh:
                if temp and temp >= CPU_THROTTLE_TEMP:
                    return "TEMP"
                return "VRM"

        return None
    except Exception as e:
        logging.warning("[aida] detect_cpu_throttle failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _read_csv(path: str) -> str | None:
    """Read a CSV file trying common encodings used by AIDA64."""
    for enc in ("utf-16", "utf-16-le", "utf-8-sig", "utf-8"):
        try:
            with open(path, encoding=enc, errors="strict") as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def _parse_duration(start_str: str, end_str: str) -> str:
    """Return a human-readable duration string, or '—' on failure."""
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            t1 = datetime.strptime(start_str, fmt)
            t2 = datetime.strptime(end_str, fmt)
            s  = abs((t2 - t1).total_seconds())
            return f"{int(s // 60)} мин {int(s % 60)} сек"
        except (ValueError, TypeError):
            continue
    return "—"
