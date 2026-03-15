"""
services/bat_runner.py — BAT file execution and task runner thread.

Provides:
- run_bat()     — run a single .bat file, stream output to a log callback.
- run_tasks()   — run the full ordered task list, updating shared state.
"""

import os
import subprocess
import threading
from typing import Callable

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False

from src.paths import SCRIPTS_DIR
from src import state


# ---------------------------------------------------------------------------
# Single BAT execution
# ---------------------------------------------------------------------------

def run_bat(
    bat_path: str,
    log_cb: Callable[[str, str], None],
    double_run: bool = False,
) -> tuple[bool, int]:
    """Execute a BAT file and stream its output through *log_cb*.

    Args:
        bat_path:   Absolute path to the .bat file.
        log_cb:     Callable(text, level) used to emit log lines.
        double_run: If True, the file is run twice (used for SDI driver install).

    Returns:
        ``(success, return_code)`` where success is True when the exit code
        is 0 or 255.  Returns ``(False, -1)`` on launch errors.
    """
    runs = 2 if double_run else 1
    last_rc = 0

    for run_num in range(runs):
        if double_run:
            log_cb(f"  Запуск {run_num + 1} из 2...", "muted")
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0

            proc = subprocess.Popen(
                ["cmd", "/C", bat_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                startupinfo=si,
                encoding=None,
                cwd=os.path.dirname(bat_path) or ".",
            )

            for raw in proc.stdout:
                line = _decode_line(raw)
                if not line.strip():
                    continue
                log_cb(line.strip(), _classify_line(line))

            proc.wait()
            last_rc = proc.returncode

        except FileNotFoundError:
            log_cb(f"Файл не найден: {bat_path}", "err")
            return False, -1
        except Exception as e:
            log_cb(f"Ошибка запуска: {e}", "err")
            return False, -1

    return last_rc in (0, 255), last_rc


# ---------------------------------------------------------------------------
# Task runner (background thread)
# ---------------------------------------------------------------------------

def start_run_thread(tasks_to_run: list[tuple[str, str]]) -> None:
    """Spawn a daemon thread that executes *tasks_to_run* sequentially.

    Args:
        tasks_to_run: List of ``(display_name, bat_filename)`` pairs.
    """
    threading.Thread(
        target=_run_thread,
        args=(tasks_to_run,),
        daemon=True,
    ).start()


def _run_thread(tasks_to_run: list[tuple[str, str]]) -> None:
    total  = len(tasks_to_run)
    errors = 0

    for i, (name, bat) in enumerate(tasks_to_run):
        if state._state["cancel"]:
            state.log("⏹ Выполнение отменено", "warn")
            break

        pct = int(i / total * 100)
        state._state["progress"] = pct
        state.push("status", {
            "running":  True,
            "text":     f"{name}...",
            "type":     "running",
            "progress": pct,
            "step":     f"{i + 1}/{total}",
        })
        state.log(f"▶ [{i + 1}/{total}] {name}", "info")

        bat_path    = os.path.join(SCRIPTS_DIR, bat)
        double_run  = bat == "11_runsdi.bat"
        ok, rc      = run_bat(bat_path, state.log, double_run=double_run)

        if ok:
            state.log(f"✓ {name} — выполнено", "ok")
        else:
            errors     += 1
            code_str    = f"код {rc}" if rc != -1 else "файл не найден"
            state.log(f"✗ {name} — ошибка ({code_str})", "err")

        # Parse AIDA64 results after stress-test bats
        if bat in ("04_tests.bat", "99_testnotimelimit.bat"):
            _process_aida_results()

    # ── Finalise ────────────────────────────────────────────────────────────
    state._state["running"] = False
    state._state["cancel"]  = False
    state._state["progress"] = 100

    if errors:
        state.log(f"═══ Завершено с ошибками ({errors}) ═══", "warn")
        state.push("status", {
            "running":  False,
            "text":     f"Завершено с ошибками ({errors})",
            "type":     "warn",
            "progress": 100,
        })
    else:
        state.log("═══ Все задачи выполнены успешно ═══", "ok")
        state.push("status", {
            "running":  False,
            "text":     "Все задачи выполнены ✓",
            "type":     "done",
            "progress": 100,
        })

    if _HAS_WINSOUND:
        try:
            import winsound
            beep = winsound.MB_ICONASTERISK if not errors else winsound.MB_ICONEXCLAMATION
            winsound.MessageBeep(beep)
        except Exception:
            pass


def _process_aida_results() -> None:
    """Read the latest AIDA64 CSV and push results to connected clients."""
    from src.services.aida import (
        find_latest_aida_csv,
        find_latest_aida_log_csv,
        parse_aida_stat_csv,
        detect_cpu_throttle,
    )
    try:
        af  = find_latest_aida_csv()
        alf = find_latest_aida_log_csv()
        if af:
            state.log(f"Читаю отчёт AIDA64: {os.path.basename(af)}", "info")
            result = parse_aida_stat_csv(af)
            if result:
                if alf:
                    result["throttle"] = detect_cpu_throttle(alf)
                state._state["test_results"] = result
                state.push("test_results", result)
            else:
                state.log("Не удалось разобрать отчёт AIDA64", "warn")
        else:
            state.log("Отчёт AIDA64 не найден", "warn")
    except Exception as e:
        state.log(f"Ошибка чтения AIDA64: {e}", "warn")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _decode_line(raw: bytes) -> str:
    """Decode a raw byte line from a subprocess, trying UTF-8 then CP866."""
    for enc in ("utf-8", "cp866"):
        try:
            return raw.decode(enc).rstrip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").rstrip()


def _classify_line(line: str) -> str:
    """Map a log line to a severity level based on its content."""
    if any(x in line for x in ("[!]", "ВНИМАНИЕ", "Ошибка", "ERROR", "WARN")):
        return "warn"
    if "[i]" in line:
        return "info"
    if any(x in line for x in ("✓", "выполнено", "complete", "завершен", "завершён")):
        return "ok"
    return "muted"
