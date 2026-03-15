"""
routes/hardware.py — Hardware information route.

    /api/hw_info  → combined WMI + SMART data for the hardware tooltip
"""

from flask import Blueprint, jsonify

from src.services.hardware import get_hw_info, get_smart, build_disks_payload

bp = Blueprint("routes_hardware", __name__)


@bp.route("/api/hw_info")
def api_hw_info():
    hw   = get_hw_info()
    return jsonify({
        "ok":              True,
        "ready":           bool(hw),
        "cpu":             hw.get("CPU",  "—"),
        "mb":              hw.get("MB",   "—"),
        "ram":             hw.get("RAM",  "—"),
        "gpu":             hw.get("GPU",  "—"),
        "bios":            hw.get("BIOS", "—"),
        "disks":           build_disks_payload(),
        "smart_available": get_smart() is not None,
    })
