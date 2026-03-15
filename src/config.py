"""
config.py — Static configuration for ALFAscript.

All constants, task definitions, presets, extras, and temperature
thresholds live here. Nothing in this module has side-effects on import.
"""

import json
import os

from paths import MULTILAUNCH, LOCAL_COMP_FILE, _APP_DIR


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

CURRENT_VERSION = "6.6.6"

#: Default build date — overwritten at runtime by ``get_current_date()``.
_DEFAULT_DATE = "04.03.2026"


def get_current_date() -> str:
    """Return the build date.

    Reads ``main.version`` from ``multilaunch/components_local.json`` when
    available; falls back to ``_DEFAULT_DATE`` otherwise.
    """
    try:
        if MULTILAUNCH:
            path = os.path.join(MULTILAUNCH, LOCAL_COMP_FILE)
            if os.path.isfile(path):
                with open(path, encoding="utf-8-sig") as f:
                    data = json.load(f)
                main = data.get("main")
                if isinstance(main, dict):
                    date = main.get("version", "")
                elif isinstance(main, str):
                    date = main  # legacy format — bare string
                else:
                    date = ""
                if date:
                    return date.strip()
    except Exception:
        pass
    return _DEFAULT_DATE


#: Build date resolved at import time.
CURRENT_DATE: str = get_current_date()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

UPDATE_FOLDER_URL = "https://disk.yandex.ru/d/Xq2vFGbe0n5dYA"


# ---------------------------------------------------------------------------
# Temperature thresholds
# ---------------------------------------------------------------------------

CPU_WARN = 85
CPU_CRIT = 95
GPU_WARN = 80
GPU_CRIT = 90
VRM_WARN = 90
VRM_CRIT = 110


# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------
# Structure: list of (category_name, [(display_name, bat_filename, default_enabled)])

TASKS: list[tuple[str, list[tuple[str, str, bool]]]] = [
    ("ПОДГОТОВКА", [
        ("Включить профиль производительности", "10_nosleep.bat",         True),
        ("Установка драйверов SDI",              "11_runsdi.bat",          True),
        ("Проверка интернет соединения",         "01_inetnew.bat",         True),
    ]),
    ("НАСТРОЙКА", [
        ("Тёмная тема",                          "02_temad.bat",           False),
        ("Светлая тема",                         "02_temaw.bat",           False),
        ("Установка библиотек",                  "03_biblioteki.bat",      True),
        ("Создание ярлыков",                     "05_shortcuts.bat",       True),
        ("Активация Win + Office",               "07_aktiv.bat",           True),
        ("Установка Яндекс Браузера",            "13_yabrowser.bat",       True),
    ]),
    ("ТЕСТЫ", [
        ("AIDA + FurMark · 5 мин",               "04_tests.bat",           True),
        ("AIDA + FurMark · 5 часов",             "99_testnotimelimit.bat", False),
    ]),
    ("ОБСЛУЖИВАНИЕ", [
        ("Финальная очистка",                    "12_cleanup.bat",         True),
    ]),
]


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------
# Maps preset display name → ordered list of bat filenames to enable.

PRESETS: dict[str, list[str]] = {
    "⚡  Полный скрипт": [
        "10_nosleep.bat", "11_runsdi.bat", "01_inetnew.bat",
        "02_temad.bat", "03_biblioteki.bat", "05_shortcuts.bat",
        "07_aktiv.bat", "13_yabrowser.bat", "04_tests.bat", "12_cleanup.bat",
    ],
    "📦  Мини (образ ALFA)": [
        "11_runsdi.bat", "10_nosleep.bat", "01_inetnew.bat",
        "04_tests.bat", "07_aktiv.bat", "13_yabrowser.bat", "12_cleanup.bat",
    ],
    "🌙  Без тестов — тёмная": [
        "10_nosleep.bat", "11_runsdi.bat", "01_inetnew.bat",
        "02_temad.bat", "03_biblioteki.bat", "05_shortcuts.bat",
        "07_aktiv.bat", "13_yabrowser.bat", "12_cleanup.bat",
    ],
    "☀️  Без тестов — светлая": [
        "10_nosleep.bat", "11_runsdi.bat", "01_inetnew.bat",
        "02_temaw.bat", "03_biblioteki.bat", "05_shortcuts.bat",
        "07_aktiv.bat", "13_yabrowser.bat", "12_cleanup.bat",
    ],
}


# ---------------------------------------------------------------------------
# Extras (toolbar quick-actions)
# ---------------------------------------------------------------------------
# Structure: list of (icon, display_name, bat_or_action)
# bat_or_action meanings:
#   str ending in .bat   → run that bat from SCRIPTS_DIR
#   None                 → manual activation (inline PowerShell)
#   ":cmd:<shell_cmd>"   → run shell command directly
#   ":portmgr:"          → open port/diagnostics manager UI
#   ":softmgr:"          → open software manager UI

EXTRAS: list[tuple[str, str, str | None]] = [
    ("💾", "Бэкап драйверов",          "08_drv_backup.bat"),
    ("♻️", "Восстановление драйверов",  "09_drv_restore.bat"),
    ("🖥️", "Менеджер дисков",           "06_dskmgr.bat"),
    ("🔑", "Ручная активация",          None),
    ("📋", "Просмотр журнала",          ":cmd:perfmon /rel"),
    ("🔬", "Диагностика",               ":portmgr:"),
    ("📦", "Установка программ",        ":softmgr:"),
]


# ---------------------------------------------------------------------------
# Helpers derived from TASKS (convenience — avoids re-computing elsewhere)
# ---------------------------------------------------------------------------

def default_task_states() -> dict[str, bool]:
    """Return ``{bat_filename: default_enabled}`` for every task."""
    return {
        bat: default
        for _cat, tasks in TASKS
        for _name, bat, default in tasks
    }