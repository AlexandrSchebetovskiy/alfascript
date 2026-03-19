"""
routes/tasks.py — Task execution routes.

    /api/run     → start the selected tasks
    /api/stop    → request cancellation
    /api/preset  → apply a named preset
    /api/tasks   → toggle individual task checkboxes
"""

from flask import Blueprint, jsonify, request

from src import state
from src.config import TASKS, PRESETS
from src.paths import MULTILAUNCH
from src.services.bat_runner import start_run_thread

bp = Blueprint("routes_tasks", __name__)


@bp.route("/api/run", methods=["POST"])
def api_run():
    if state._state["running"]:
        return jsonify({"ok": False, "error": "Уже запущено"})
    if not MULTILAUNCH:
        return jsonify({"ok": False, "error": "Папка multilaunch не найдена!"})

    tasks_to_run = []
    for _cat, tasks in TASKS:
        for item in tasks:
            if isinstance(item, dict) and item.get("type") == "dropdown":
                for label, bat in item["options"]:
                    if state._state["tasks"].get(bat):
                        tasks_to_run.append((f"{item['name']} › {label}", bat))
            else:
                name, bat, _ = item
                if state._state["tasks"].get(bat):
                    tasks_to_run.append((name, bat))
    if not tasks_to_run:
        return jsonify({"ok": False, "error": "Выберите хотя бы одну задачу!"})

    state._state["running"] = True
    state._state["cancel"]  = False
    state._state["progress"] = 0
    state.push("status", {"running": True, "text": "Запуск...", "type": "running", "progress": 0})
    start_run_thread(tasks_to_run)
    return jsonify({"ok": True})


@bp.route("/api/stop", methods=["POST"])
def api_stop():
    if state._state["running"]:
        state._state["cancel"] = True
        state.log("⏹ Запрошена отмена — текущий шаг доработает до конца", "warn")
        state.push("status", {
            "running":  True,
            "text":     "Отмена...",
            "type":     "warn",
            "progress": state._state["progress"],
        })
    return jsonify({"ok": True})


@bp.route("/api/preset", methods=["POST"])
def api_preset():
    name = request.json.get("preset")
    if name not in PRESETS:
        return jsonify({"ok": False}), 400

    bats = set(PRESETS[name])
    for bat in state._state["tasks"]:
        state._state["tasks"][bat] = bat in bats
    state._state["active_preset"] = name
    state.log(f"Применён пресет: {name.strip()}", "info")
    return jsonify({"ok": True, "tasks": state._state["tasks"]})


@bp.route("/api/tasks", methods=["POST"])
def api_tasks():
    data = request.json.get("tasks", {})
    for bat, val in data.items():
        if bat in state._state["tasks"]:
            state._state["tasks"][bat] = bool(val)
    return jsonify({"ok": True})
