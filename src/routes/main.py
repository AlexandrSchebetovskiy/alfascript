"""
routes/main.py — Core page and streaming routes.

Blueprints:
    /              → index page
    /log           → floating log window page
    /api/state     → full application state snapshot
    /api/stream    → SSE event stream
    /api/save_log  → persist log to log.txt
    /api/open_readme → open README in browser
"""

import json
import queue as Q
import os

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from src import state
from src.config import CURRENT_VERSION, CURRENT_DATE, TASKS, EXTRAS
from src.paths import MULTILAUNCH, _APP_DIR
from src.theme import THEMES_DATA, load_appearance
from src.services.system import (
    get_os_version,
    get_net_status,
    get_sdi_date,
    get_uac_status,
    get_defender_exclusion_status,
    is_admin,
)
from src.config import CPU_WARN, CPU_CRIT, GPU_WARN, GPU_CRIT, VRM_WARN, VRM_CRIT

bp = Blueprint("routes_main", __name__)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route("/")
def index():
    vstyle, vmode = load_appearance()
    from src.config import PRESETS
    return render_template(
        "index.html",
        tasks=TASKS,
        presets=list(PRESETS.keys()),
        extras=EXTRAS,
        version=CURRENT_VERSION,
        date=CURRENT_DATE,
        state=state._state,
        multilaunch=MULTILAUNCH,
        is_admin=is_admin(),
        vstyle=vstyle,
        vmode=vmode,
    )


@bp.route("/log")
def log_window():
    vstyle, vmode = load_appearance()
    return render_template(
        "log.html",
        version=CURRENT_VERSION,
        themes=THEMES_DATA,
        theme=f"{vstyle}_{vmode}",
    )


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

@bp.route("/api/state")
def api_state():
    vstyle, vmode = load_appearance()
    return jsonify({
        "tasks":          state._state["tasks"],
        "active_preset":  state._state["active_preset"],
        "running":        state._state["running"],
        "status":         state._state["status"],
        "status_type":    state._state["status_type"],
        "progress":       state._state["progress"],
        "test_results":   state._state["test_results"],
        "multilaunch":    MULTILAUNCH,
        "is_admin":       is_admin(),
        "os_ver":         get_os_version(),
        "net_ok":         get_net_status(),
        "sdi_date":       get_sdi_date(),
        "uac_status":     get_uac_status(),
        "defender_excl":  get_defender_exclusion_status(),
        "vstyle":         vstyle,
        "vmode":          vmode,
        "thresholds": {
            "cpu_warn": CPU_WARN, "cpu_crit": CPU_CRIT,
            "gpu_warn": GPU_WARN, "gpu_crit": GPU_CRIT,
            "vrm_warn": VRM_WARN, "vrm_crit": VRM_CRIT,
        },
    })


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

@bp.route("/api/stream")
def api_stream():
    q = Q.Queue()
    history_snapshot = state.add_client(q)

    def generate():
        try:
            # Send current run state immediately on connect
            yield (
                f"data: {json.dumps({'type': 'state', 'data': {'running': state._state['running'], 'status': state._state['status'], 'progress': state._state['progress']}})}\n\n"
            )
            # Replay log history so a freshly opened log window isn't empty
            if history_snapshot:
                yield (
                    f"data: {json.dumps({'type': 'log_history', 'data': history_snapshot}, ensure_ascii=False)}\n\n"
                )
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield f"data: {msg}\n\n"
                except Q.Empty:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            state.remove_client(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

@bp.route("/api/save_log", methods=["POST"])
def api_save_log():
    try:
        lines    = request.json.get("lines", [])
        log_path = os.path.join(_APP_DIR, "log.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return jsonify({"ok": True, "path": log_path})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@bp.route("/api/open_readme")
def api_open_readme():
    if not MULTILAUNCH:
        return jsonify({"ok": False, "error": "multilaunch не найден"})
    readme = os.path.join(MULTILAUNCH, "dependencies", "README_ALFAscript.html")
    if not os.path.isfile(readme):
        return jsonify({"ok": False, "error": f"Файл не найден: {readme}"})
    try:
        import webbrowser
        webbrowser.open(f"file:///{readme.replace(os.sep, '/')}")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
