"""
routes/extras.py — Extra toolbar actions and program management routes.

    /api/extra            → run an extra action (bat, shell cmd, or special)
    /api/soft_programs    → list installable programs (soft/ + heavy/)
    /api/diag_programs    → list diagnostic/portable programs
    /api/launch_program   → launch a program by path
    /api/open_folder      → open a folder in Explorer
    /api/icon             → serve a program icon file
"""

import os
import subprocess

from flask import Blueprint, Response, jsonify, request

from src import state
from src.paths import MULTILAUNCH, SCRIPTS_DIR
from src.services.bat_runner import run_bat
from src.services.programs import scan_programs
from src.services.updater import _load_local_comp

bp = Blueprint("routes_extras", __name__)


@bp.route("/api/extra", methods=["POST"])
def api_extra():
    bat  = request.json.get("bat")
    name = request.json.get("name", "")

    # Manual activation via online script
    if bat is None:
        try:
            subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-NoExit",
                 "-Command", "irm https://get.activated.win | iex"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            state.log("▶ Запущена: Ручная активация", "info")
        except Exception as e:
            state.log(f"Ошибка: {e}", "err")
        return jsonify({"ok": True})

    if isinstance(bat, str) and bat.startswith(":cmd:"):
        cmd = bat[5:]
        try:
            subprocess.Popen(cmd, shell=True)
            state.log(f"▶ Запущен: {name}", "info")
        except Exception as e:
            state.log(f"Ошибка: {e}", "err")
        return jsonify({"ok": True})

    if isinstance(bat, str) and bat.startswith(":softmgr:"):
        return jsonify({"ok": True, "action": "softmgr"})

    if isinstance(bat, str) and bat.startswith(":portmgr:"):
        return jsonify({"ok": True, "action": "portmgr"})

    # Regular bat file
    if state.get_state("running"):
        return jsonify({"ok": False, "error": "Уже запущено"})
    if not SCRIPTS_DIR:
        return jsonify({"ok": False, "error": "scripts не найден"})

    bat_path = os.path.join(SCRIPTS_DIR, bat)
    state.log(f"▶ Запуск: {name}", "info")

    import threading
    def _t():
        ok, rc = run_bat(bat_path, state.log)
        state.log(
            f"{'✓' if ok else '✗'} {name} — {'выполнено' if ok else f'ошибка (код {rc})'}",
            "ok" if ok else "err",
        )
    threading.Thread(target=_t, daemon=True).start()
    return jsonify({"ok": True})


@bp.route("/api/soft_programs")
def api_soft_programs():
    if not MULTILAUNCH:
        return jsonify({"ok": False, "programs": [], "folder": None})

    soft_dir  = os.path.join(MULTILAUNCH, "soft")
    programs  = scan_programs(soft_dir)
    heavy_dir = os.path.join(MULTILAUNCH, "heavy")
    local_comp = _load_local_comp()

    if os.path.isdir(heavy_dir):
        try:
            for entry in sorted(os.listdir(heavy_dir)):
                entry_path = os.path.join(heavy_dir, entry)
                if not os.path.isdir(entry_path):
                    continue
                exe_path = icon_path = None
                for icon_name in ("icon.png", "icon.ico", "Icon.png", "Icon.ico"):
                    c = os.path.join(entry_path, icon_name)
                    if os.path.isfile(c):
                        icon_path = c
                        break
                launch_txt = os.path.join(entry_path, "launch.txt")
                if os.path.isfile(launch_txt):
                    try:
                        with open(launch_txt, encoding="utf-8", errors="replace") as lf:
                            exe_name = lf.read().strip()
                        c = os.path.join(entry_path, exe_name)
                        if os.path.isfile(c):
                            exe_path = c
                    except Exception:
                        pass
                if not exe_path:
                    for f in sorted(os.listdir(entry_path)):
                        if os.path.splitext(f)[1].lower() in (".exe", ".msi"):
                            exe_path = os.path.join(entry_path, f)
                            break
                comp_key = f"heavy_{entry}"
                programs.append({
                    "name":      entry,
                    "path":      exe_path,
                    "icon":      icon_path,
                    "installed": exe_path is not None,
                    "comp_key":  comp_key,
                    "local_ver": local_comp.get(comp_key),
                })
        except Exception:
            pass

    return jsonify({"ok": True, "programs": programs, "title": "Установка программ", "folder": soft_dir})


@bp.route("/api/diag_programs")
def api_diag_programs():
    if not MULTILAUNCH:
        return jsonify({"ok": False, "programs": [], "folder": None})
    port_dir = os.path.join(MULTILAUNCH, "portable")
    programs = scan_programs(port_dir)
    return jsonify({"ok": True, "programs": programs, "title": "Диагностика", "folder": port_dir})


@bp.route("/api/launch_program", methods=["POST"])
def api_launch_program():
    path = request.json.get("path", "")
    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "error": "Файл не найден"})
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".msi":
            subprocess.Popen(["msiexec", "/i", path], cwd=os.path.dirname(path))
        else:
            subprocess.Popen([path], cwd=os.path.dirname(path))
        name = os.path.splitext(os.path.basename(path))[0]
        state.log(f"▶ Запущена программа: {name}", "info")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@bp.route("/api/open_folder", methods=["POST"])
def api_open_folder():
    path = request.json.get("path", "")
    if path and os.path.isdir(path):
        try:
            subprocess.Popen(f'explorer "{path}"')
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": False, "error": "Папка не найдена"})


@bp.route("/api/icon")
def api_icon():
    """Serve a program icon file by absolute path (restricted to multilaunch folder)."""
    import mimetypes
    path = request.args.get("path", "")
    if not path or not os.path.isfile(path):
        return "", 404
    if MULTILAUNCH and not path.lower().startswith(MULTILAUNCH.lower()):
        return "", 403
    try:
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as f:
            data = f.read()
        return Response(data, mimetype=mime, headers={"Cache-Control": "max-age=3600"})
    except Exception:
        return "", 500
