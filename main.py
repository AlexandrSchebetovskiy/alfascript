"""
main.py — ALFAscript entry point.

Responsibilities (nothing else):
1. Require administrator privileges.
2. Start background service threads.
3. Start the Flask server thread.
4. Launch the pywebview window (or fall back to a browser tab).
"""

import sys
import threading
import time

from src.app import create_app
from src.config  import CURRENT_VERSION
from src.paths import MULTILAUNCH
from src.services.hardware import load_hw_info_bg
from src.services.system import (
    apply_defender_exclusions,
    get_defender_exclusion_status,
    is_admin,
    run_as_admin,
    start_net_monitor,
)
from src.services.updater import check_for_update
from src.webapi import WebAPI
from src import state

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FLASK_HOST = "127.0.0.1"
_FLASK_PORT = 5757
_FLASK_URL  = f"http://{_FLASK_HOST}:{_FLASK_PORT}"


# ---------------------------------------------------------------------------
# Background threads
# ---------------------------------------------------------------------------

def _auto_defender() -> None:
    """Add Defender exclusions at startup if not already present."""
    status = get_defender_exclusion_status()
    if status == "Добавлены":
        state.log("Defender: исключения уже добавлены", "ok")
        return
    if status == "Отключён":
        state.log("Defender: служба отключена — исключения не требуются", "info")
        return
    state.log("Defender: добавляю исключения для флешки и _MEIPASS…", "info")
    ok, msg, disabled = apply_defender_exclusions()
    if disabled:
        state.log("Defender: служба отключена — исключения не требуются", "info")
    elif ok:
        state.log(f"Defender: исключения добавлены → {msg}", "ok")
    else:
        state.log(f"Defender: не удалось добавить исключения — {msg}", "warn")


def _auto_check_update() -> None:
    """Check for updates 3 seconds after launch (gives SSE client time to connect)."""
    time.sleep(3)
    state.log("Проверка обновлений...", "info")
    result = check_for_update()
    state.push("update", result)
    if result.get("has_update"):
        state.log(f"! Доступно обновление multilaunch: {result.get('version', '')} — откройте меню ℹ", "warn")
    elif result.get("has_heavy_update"):
        state.log("Доступны обновления тяжёлых компонентов — откройте меню ℹ", "warn")
    elif result.get("error"):
        state.log(f"Проверка обновлений: {result['error']}", "warn")
    else:
        state.log("Обновлений нет", "ok")


def _start_background_threads() -> None:
    """Spawn all daemon threads that should run for the lifetime of the app."""
    load_hw_info_bg()                                                    # WMI + smartctl
    start_net_monitor()                                                  # ping ya.ru every 30s
    threading.Thread(target=_auto_defender,      daemon=True).start()   # Defender exclusions
    threading.Thread(target=_auto_check_update,  daemon=True).start()   # update check


# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------

def _start_flask() -> threading.Thread:
    """Create the Flask app, start it in a daemon thread, return the thread."""
    app = create_app()

    def _run():
        app.run(
            host=_FLASK_HOST,
            port=_FLASK_PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
        )

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Startup log
# ---------------------------------------------------------------------------

def _log_startup() -> None:
    state.log(f"ALFAscript {CURRENT_VERSION} инициализирован", "ok")
    if is_admin():
        state.log("Права администратора: ОК", "ok")
    else:
        state.log("Нет прав администратора!", "err")
    if MULTILAUNCH:
        state.log(f"Найдено: {MULTILAUNCH}", "ok")
    else:
        state.log("ВНИМАНИЕ: папка multilaunch не найдена!", "warn")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not is_admin():
        run_as_admin()
        sys.exit()

    _log_startup()
    _start_background_threads()

    flask_thread = _start_flask()
    time.sleep(0.8)  # let Flask bind before webview opens the URL

    try:
        import webview

        api = WebAPI()
        webview.create_window(
            title=f"ALFAscript {CURRENT_VERSION}",
            url=_FLASK_URL,
            width=1200,
            height=720,
            min_size=(900, 560),
            resizable=True,
            background_color="#0f1117",
            js_api=api,
        )
        webview.start(debug=False)

    except ImportError:
        import webbrowser
        webbrowser.open(_FLASK_URL)
        print("pywebview не найден — открываю в браузере.")
        flask_thread.join()


if __name__ == "__main__":
    main()