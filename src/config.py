"""
config.py — Static configuration for ALFAscript.

All constants, task definitions, presets, extras, and temperature
thresholds live here. Nothing in this module has side-effects on import.
"""

import json
import os

from src.paths import MULTILAUNCH, LOCAL_COMP_FILE, _APP_DIR


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

CURRENT_VERSION = "6.6.6"

#: Default build date — overwritten at runtime by ``get_current_date()``.
_DEFAULT_DATE = "16.03.2026"


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
# Structure: list of (category_name, [items])
# Each item is either:
#   - a tuple (display_name, bat_filename, default_enabled)  — simple checkbox
#   - a dict returned by dropdown()                           — dropdown selector


def dropdown(
    name: str,
    options: list[tuple[str, str]],
    default: str | None = None,
) -> dict:
    """Create a dropdown task item.

    Args:
        name:    Display name shown in the task row.
        options: List of ``(label, bat_filename)`` pairs.
        default: bat_filename selected by default, or ``None`` for none.
    """
    return {"type": "dropdown", "name": name, "options": options, "default": default}


TASKS: list = [
    ("ПОДГОТОВКА", [
        ("Включить профиль производительности", "10_nosleep.bat",         True),
        ("Установка драйверов SDI",              "11_runsdi.bat",          True),
        ("Проверка интернет соединения",         "01_inetnew.bat",         True),
    ]),
    ("НАСТРОЙКА", [
        dropdown("Тема Windows", [("Тёмная", "02_temad.bat"), ("Светлая", "02_temaw.bat")]),
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
#   str ending in .bat         → run that bat from SCRIPTS_DIR
#   None / ACTION_ACTIVATE     → manual activation (inline PowerShell)
#   ACTION_CMD + "<shell_cmd>" → run shell command directly
#   ACTION_PORTMGR             → open port/diagnostics manager UI
#   ACTION_SOFTMGR             → open software manager UI

ACTION_CMD     = ":cmd:"
ACTION_SOFTMGR = ":softmgr:"
ACTION_PORTMGR = ":portmgr:"

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
    result: dict[str, bool] = {}
    for _cat, tasks in TASKS:
        for item in tasks:
            if isinstance(item, dict) and item.get("type") == "dropdown":
                default_bat = item.get("default")
                for _label, bat in item["options"]:
                    result[bat] = (bat == default_bat)
            else:
                _name, bat, default = item
                result[bat] = default
    return result
# ---------------------------------------------------------------------------
# JSON override  (MULTILAUNCH/config_override.json)
# ---------------------------------------------------------------------------
# All keys are optional. Missing keys leave the defaults above untouched.
#
# Expected JSON shape:
# {
#   "temps": {
#     "CPU_WARN": 80, "CPU_CRIT": 90,
#     "GPU_WARN": 75, "GPU_CRIT": 85,
#     "VRM_WARN": 85, "VRM_CRIT": 100
#   },
#   "tasks": [
#     ["CATEGORY", [
#       ["Display name", "bat_file.bat", true]
#     ]]
#   ],
#   "presets": {
#     "⚡  Полный скрипт": ["10_nosleep.bat", "..."]
#   },
#   "extras": [
#     ["💾", "Label", "bat_or_action_or_null"]
#   ]
# }

def _load_overrides() -> None:
    if not MULTILAUNCH:
        return
    path = os.path.join(MULTILAUNCH, "config_override.json")
    if not os.path.isfile(path):
        return

    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"[config] Warning: could not read config_override.json — {exc}")
        return

    import sys
    _mod = sys.modules[__name__]

    # -- Temperature thresholds (now lowercase keys in JSON) --------------
    _TEMP_MAP = {
        "cpu_warn": "CPU_WARN", "cpu_crit": "CPU_CRIT",
        "gpu_warn": "GPU_WARN", "gpu_crit": "GPU_CRIT",
        "vrm_warn": "VRM_WARN", "vrm_crit": "VRM_CRIT",
    }
    for json_key, attr in _TEMP_MAP.items():
        if json_key in data:
            value = data[json_key]
            if isinstance(value, (int, float)):
                setattr(_mod, attr, value)
            else:
                print(f"[config] Warning: {json_key} must be a number, got {value!r} — skipped")

    # -- TASKS (objects with category/items/name/bat/enabled) -------------
    if "tasks" in data:
        try:
            def _parse_item(item: dict):
                if item.get("type") == "dropdown":
                    return dropdown(
                        str(item["name"]),
                        [(str(o["label"]), str(o["bat"])) for o in item["options"]],
                        item.get("default"),
                    )
                return (str(item["name"]), str(item["bat"]), bool(item["enabled"]))

            _mod.TASKS = [
                (str(entry["category"]), [_parse_item(i) for i in entry["items"]])
                for entry in data["tasks"]
            ]
        except Exception as exc:
            print(f"[config] Warning: could not apply tasks override — {exc}")

    # -- PRESETS (unchanged — already correct format) ---------------------
    if "presets" in data:
        try:
            raw: dict = data["presets"]
            if not isinstance(raw, dict):
                raise TypeError("presets must be a JSON object")
            _mod.PRESETS = {
                str(k): [str(bat) for bat in v]
                for k, v in raw.items()
            }
        except Exception as exc:
            print(f"[config] Warning: could not apply presets override — {exc}")

    # -- EXTRAS (objects with icon/name/action) ---------------------------
    if "extras" in data:
        try:
            _mod.EXTRAS = [
                (str(e["icon"]), str(e["name"]), None if e["action"] is None else str(e["action"]))
                for e in data["extras"]
            ]
        except Exception as exc:
            print(f"[config] Warning: could not apply extras override — {exc}")


_load_overrides()