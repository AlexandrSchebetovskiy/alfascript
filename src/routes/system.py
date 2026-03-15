"""
routes/system.py — System settings routes.

    /api/disable_uac             → set UAC slider to minimum
    /api/add_defender_exclusions → add app paths to Defender exclusions
    /api/vstyle                  → persist selected visual theme
"""

from flask import Blueprint, jsonify, request

from src import state
from src.services.system import (
    apply_defender_exclusions,
    disable_uac,
    get_defender_exclusion_status,
    get_uac_status,
)
from src.theme import save_appearance

bp = Blueprint("routes_system", __name__)


@bp.route("/api/disable_uac", methods=["POST"])
def api_disable_uac():
    ok, err = disable_uac()
    if ok:
        state.log("UAC отключён (ползунок на минимум). Перезагрузка не требуется.", "ok")
        return jsonify({"ok": True, "uac_status": get_uac_status()})
    state.log(f"Ошибка отключения UAC: {err}", "err")
    return jsonify({"ok": False, "error": err})


@bp.route("/api/add_defender_exclusions", methods=["POST"])
def api_add_defender_exclusions():
    ok, msg, disabled = apply_defender_exclusions()
    if ok:
        state.log(f"Defender: добавлены исключения → {msg}", "ok")
        return jsonify({"ok": True, "status": get_defender_exclusion_status(), "added": msg})
    if disabled:
        state.log("Defender: служба отключена — исключения не требуются", "info")
        return jsonify({"ok": True, "status": "Отключён", "disabled": True})
    state.log(f"Defender: ошибка — {msg}", "err")
    return jsonify({"ok": False, "error": msg})


@bp.route("/api/vstyle", methods=["POST"])
def api_vstyle():
    data   = request.json or {}
    vstyle = data.get("vstyle", "default")
    vmode  = data.get("vmode",  "dark")
    save_appearance(vstyle, vmode)
    return jsonify({"ok": True})
