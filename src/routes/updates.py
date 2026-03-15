"""
routes/updates.py — Update management routes.

    /api/check_update      → trigger async update check (result via SSE)
    /api/download_update   → download + install selected components
    /api/cancel_update     → abort an in-progress download
"""

import threading

from flask import Blueprint, jsonify, request

from src import state
from src.services.updater import (
    cancel_download,
    check_for_update,
    get_upd_tmp_dir,
    start_download_thread,
)
from src.paths import MULTILAUNCH

bp = Blueprint("routes_updates", __name__)


@bp.route("/api/check_update")
def api_check_update():
    def _t():
        result = check_for_update()
        state.push("update", result)

    threading.Thread(target=_t, daemon=True).start()
    return jsonify({"ok": True})


@bp.route("/api/download_update", methods=["POST"])
def api_download_update():
    data       = request.json or {}
    keys_to_dl = data.get("components", [])
    comp_list  = data.get("remote_comp", [])

    if not keys_to_dl or not comp_list:
        return jsonify({"ok": False, "error": "Не указаны компоненты для загрузки"})

    to_download = [c for c in comp_list if c["key"] in keys_to_dl]
    if not to_download:
        return jsonify({"ok": False, "error": "Нет компонентов для загрузки"})

    if not MULTILAUNCH:
        return jsonify({"ok": False, "error": "multilaunch не найден"})

    # Guard against concurrent downloads
    if get_upd_tmp_dir():
        return jsonify({"ok": False, "error": "Загрузка уже выполняется"})

    start_download_thread(keys_to_dl, comp_list)
    return jsonify({"ok": True})


@bp.route("/api/cancel_update", methods=["POST"])
def api_cancel_update():
    state.log("Скачивание отменено пользователем", "warn")
    cancel_download()
    return jsonify({"ok": True})
