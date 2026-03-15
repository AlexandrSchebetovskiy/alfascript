"""
services/updater.py — Update checking and component downloading.

Provides:
- check_for_update()     — compare remote components.json with local versions.
- download_updates()     — download and install selected components (streaming
                           progress via state.push).
- _load_local_comp()     — read components_local.json from multilaunch.
- _save_local_comp()     — write components_local.json to multilaunch.
"""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

from datetime import datetime

from src import state
from src.config import UPDATE_FOLDER_URL
from src.paths import MULTILAUNCH, LOCAL_COMP_FILE, _APP_DIR, find_7zip


# ---------------------------------------------------------------------------
# Local component version store
# ---------------------------------------------------------------------------

def _load_local_comp() -> dict:
    """Read multilaunch/components_local.json. Returns {} on any error."""
    if not MULTILAUNCH:
        return {}
    path = os.path.join(MULTILAUNCH, LOCAL_COMP_FILE)
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f)
        result = {}
        for k, v in raw.items():
            if isinstance(v, dict):
                v = v.get("version") or v.get("ver") or v.get("date") or ""
            result[k] = str(v) if v is not None else None
        return result
    except Exception:
        return {}


def _save_local_comp(data: dict) -> None:
    """Write *data* to multilaunch/components_local.json."""
    if not MULTILAUNCH:
        return
    path = os.path.join(MULTILAUNCH, LOCAL_COMP_FILE)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        state.log(f"Не удалось сохранить {LOCAL_COMP_FILE}: {e}", "warn")


# ---------------------------------------------------------------------------
# Update check
# ---------------------------------------------------------------------------

def check_for_update() -> dict:
    """Download components.json from Yandex Disk and compare with local versions.

    Returns a dict consumed directly by the UI via SSE 'update' event.
    On network/parse errors returns ``{"error": "<message>"}``.
    """
    try:
        import ssl as _ssl
        _ctx = _ssl.create_default_context()
        _ctx.check_hostname = False
        _ctx.verify_mode    = _ssl.CERT_NONE
        UA = "ALFAscript-Updater/1.0"

        def _get_dl_url(pk, path=""):
            url = (
                f"https://cloud-api.yandex.net/v1/disk/public/resources/download"
                f"?public_key={urllib.parse.quote(pk, safe='')}"
                + (f"&path={urllib.parse.quote(path, safe='')}" if path else "")
            )
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10, context=_ctx) as r:
                return json.loads(r.read())["href"]

        def _read_json(pk, path):
            direct = _get_dl_url(pk, path)
            req    = urllib.request.Request(direct, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
                return json.loads(r.read().decode("utf-8-sig"))

        def _read_txt(pk, path, keep_empty=False):
            direct = _get_dl_url(pk, path)
            req    = urllib.request.Request(direct, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10, context=_ctx) as r:
                raw = r.read().decode("utf-8-sig")
            lines = raw.splitlines()
            return [l.rstrip() for l in lines] if keep_empty else [l.strip() for l in lines if l.strip()]

        def _to_tuple(s):
            try:
                p = s.strip().split(".")
                if len(p) == 3:
                    if len(p[2]) == 4:   return (int(p[2]), int(p[1]), int(p[0]))
                    if len(p[0]) == 4:   return (int(p[0]), int(p[1]), int(p[2]))
            except Exception:
                pass
            return (0, 0, 0)

        def _fmt(s):
            if not isinstance(s, str):
                return str(s) if s is not None else ""
            try:
                p = s.strip().split(".")
                if len(p) == 3 and len(p[0]) == 4:
                    return f"{p[2]}.{p[1]}.{p[0]}"
            except Exception:
                pass
            return s

        # 1. Fetch remote manifest
        try:
            remote_comp = _read_json(UPDATE_FOLDER_URL, "/components.json")
        except Exception as e:
            return {"error": f"Не удалось загрузить components.json: {e}"}
        if not remote_comp:
            return {"error": "components.json пуст или недоступен"}

        # 2. Changelog
        changelog = None
        try:
            cl_lines = _read_txt(UPDATE_FOLDER_URL, "/changelog.txt", keep_empty=True)
            while cl_lines and not cl_lines[0]:  cl_lines.pop(0)
            while cl_lines and not cl_lines[-1]: cl_lines.pop()
            changelog = "\n".join(cl_lines) if cl_lines else None
        except Exception:
            pass

        # 3. Local versions
        local_comp = _load_local_comp()

        # 4. Compare
        updates_standard: list[dict] = []
        updates_heavy:    list[dict] = []
        total_dl_mb      = 0.0
        has_root_update  = False

        for key, rcomp in remote_comp.items():
            comp_type   = rcomp.get("type", "standard")
            remote_ver  = rcomp.get("version", "")
            local_ver   = local_comp.get(key)
            size_mb     = rcomp.get("size_mb", 0)
            not_installed = local_ver is None
            needs_update  = _to_tuple(remote_ver) > _to_tuple(local_ver or "") or not_installed

            entry = {
                "key":           key,
                "file":          rcomp.get("file", ""),
                "display_name":  rcomp.get("display_name", key),
                "remote_ver":    _fmt(remote_ver),
                "local_ver":     _fmt(local_ver) if local_ver else None,
                "size_mb":       size_mb,
                "needs_update":  needs_update,
                "not_installed": not_installed,
                "target":        rcomp.get("target", "."),
                "type":          comp_type,
            }

            if comp_type == "standard":
                updates_standard.append(entry)
                if needs_update:
                    total_dl_mb += size_mb
                    if key == "main":
                        has_root_update = True
            elif comp_type == "heavy":
                updates_heavy.append(entry)

        remote_root    = remote_comp.get("main", {})
        raw_ver        = remote_root.get("version", "")
        display_ver    = _fmt(raw_ver) if raw_ver and raw_ver != "unknown" else None
        local_root_ver = local_comp.get("main")

        return {
            "has_update":       any(c["needs_update"] for c in updates_standard),
            "has_root_update":  has_root_update,
            "has_heavy_update": any(c["needs_update"] for c in updates_heavy),
            "version":          display_ver,
            "date":             display_ver,
            "local_date":       _fmt(local_root_ver) if local_root_ver else None,
            "changelog":        changelog,
            "total_dl_mb":      round(total_dl_mb, 1),
            "standard":         updates_standard,
            "heavy":            updates_heavy,
            "folder":           "",
        }

    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Download + install
# ---------------------------------------------------------------------------

# Module-level flags so /api/cancel_update can reach them
_upd_cancel  = False
_upd_tmp_dir: str | None = None


def get_upd_tmp_dir() -> str | None:
    return _upd_tmp_dir


def cancel_download() -> None:
    """Signal the active download to abort and clean up its temp directory."""
    global _upd_cancel, _upd_tmp_dir
    _upd_cancel = True
    tmp = _upd_tmp_dir
    if tmp and os.path.isdir(tmp):
        try:
            shutil.rmtree(tmp, ignore_errors=True)
            state.log(f"Временные файлы удалены: {tmp}", "info")
        except Exception as ex:
            state.log(f"Не удалось удалить tmp: {ex}", "warn")
        _upd_tmp_dir = None
    state.push("upd_progress", {
        "text": "⏹  Скачивание отменено. Файлы удалены.",
        "pct": 0,
        "cancelled": True,
    })


def start_download_thread(keys_to_dl: list[str], comp_list: list[dict]) -> None:
    """Spawn a daemon thread that downloads and installs *keys_to_dl*."""
    threading.Thread(
        target=_download_bg,
        args=(keys_to_dl, comp_list),
        daemon=True,
    ).start()


def _download_bg(keys_to_dl: list[str], comp_list: list[dict]) -> None:
    global _upd_cancel, _upd_tmp_dir

    import ssl as _ssl
    _ctx = _ssl.create_default_context()
    _ctx.check_hostname = False
    _ctx.verify_mode    = _ssl.CERT_NONE
    UA = "ALFAscript-Updater/1.0"

    upd_log_path = os.path.join(_APP_DIR, "updatelog.txt")

    def _ulog(msg):
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            with open(upd_log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    def _get_dl_url(pk, path=""):
        url = (
            f"https://cloud-api.yandex.net/v1/disk/public/resources/download"
            f"?public_key={urllib.parse.quote(pk, safe='')}"
            + (f"&path={urllib.parse.quote(path, safe='')}" if path else "")
        )
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
            return json.loads(r.read())["href"]

    def _dl(url, dest, label, g_start, g_done_mb, g_total_mb):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60, context=_ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0
            with open(dest, "wb") as f:
                while True:
                    if _upd_cancel:
                        raise Exception("cancelled")
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done   += len(chunk)
                    elapsed = max(time.time() - g_start, 0.1)
                    spd     = ((g_done_mb * 1048576 + done) / elapsed) / 1048576
                    done_mb = done / 1048576
                    tot_mb  = total / 1048576 if total else 0
                    g_pct   = min(int((g_done_mb + done_mb) / g_total_mb * 95), 95) if g_total_mb > 0 else None
                    text    = (
                        f"{label}: {done_mb:.0f}/{tot_mb:.0f} МБ  •  {spd:.1f} МБ/с"
                        if tot_mb > 0 else
                        f"{label}: {done_mb:.0f} МБ  •  {spd:.1f} МБ/с"
                    )
                    state.push("upd_progress", {"text": text, "pct": g_pct})
        return done / 1048576

    def _extract(arc_path, out_dir):
        sz = find_7zip()
        if not sz:
            raise RuntimeError("7-Zip не найден — распаковка невозможна")
        proc = subprocess.Popen(
            [sz, "x", arc_path, f"-o{out_dir}", "-y", "-aoa"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"7z: код {proc.returncode} для {os.path.basename(arc_path)}")

    # Drive root = parent of multilaunch folder
    _ml        = MULTILAUNCH.rstrip("\\/")
    drive_root = os.path.dirname(_ml) or (os.path.splitdrive(_ml)[0] + os.sep)
    if not drive_root.endswith(os.sep):
        drive_root += os.sep

    to_download  = [c for c in comp_list if c["key"] in keys_to_dl]
    total_mb     = sum(c.get("size_mb", 0) for c in to_download)
    _upd_cancel  = False
    _upd_tmp_dir = None

    _ulog("=" * 48)
    _ulog(f"Запуск обновления: {', '.join(keys_to_dl)}")

    tmp_dir = None
    try:
        tmp_dir      = tempfile.mkdtemp(prefix="alfaupdate_")
        _upd_tmp_dir = tmp_dir
        done_mb      = 0.0
        g_start      = time.time()
        local_comp   = _load_local_comp()
        has_root     = False
        root_exe_tmp: str | None = None

        for i, comp in enumerate(to_download):
            key, filename = comp["key"], comp["file"]
            ver   = comp.get("remote_ver", "")
            label = comp.get("display_name", key)

            if _upd_cancel:
                raise Exception("cancelled")

            g_pct_dl = int(done_mb / total_mb * 95) if total_mb > 0 else None
            state.push("upd_progress", {
                "text":      f"[{i+1}/{len(to_download)}] Скачиваю: {label}…",
                "pct":       g_pct_dl,
                "component": key,
                "phase":     "download",
            })
            state.log(f"Скачиваю [{i + 1}/{len(to_download)}]: {filename}", "info")
            _ulog(f"Скачиваю [{i+1}/{len(to_download)}]: {filename}")

            dl_url   = _get_dl_url(UPDATE_FOLDER_URL, f"/{filename}")
            arc_path = os.path.join(tmp_dir, filename)
            dl_size  = _dl(dl_url, arc_path, label, g_start, done_mb, total_mb)
            done_mb += dl_size

            if os.path.getsize(arc_path) < 10 * 1024:
                raise RuntimeError(f"{filename} повреждён или скачался не полностью")
            state.log(f"{filename} — скачан ({dl_size:.0f} МБ)", "ok")
            _ulog(f"{filename} — скачан ({dl_size:.0f} МБ)")

            g_pct_ex = int(done_mb / total_mb * 95) if total_mb > 0 else None
            state.push("upd_progress", {
                "text":      f"[{i+1}/{len(to_download)}] Устанавливаю: {label}…",
                "pct":       g_pct_ex,
                "component": key,
                "phase":     "extract",
            })

            if key == "main":
                root_ext = os.path.join(tmp_dir, "root_ext")
                os.makedirs(root_ext, exist_ok=True)
                _extract(arc_path, root_ext)
                exe_name = "_ALFAscript.exe"
                for dirpath, _, files in os.walk(root_ext):
                    for fname in files:
                        if fname.lower() == exe_name.lower():
                            root_exe_tmp = os.path.join(dirpath, fname)
                            continue
                        src = os.path.join(dirpath, fname)
                        rel = os.path.relpath(src, root_ext)
                        dst = os.path.join(drive_root, rel)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        try:
                            shutil.copy2(src, dst)
                        except Exception as ce:
                            state.log(f"[WARN] не удалось скопировать {rel}: {ce}", "warn")
                has_root = True
                state.log("main — подготовлен (exe будет заменён после перезапуска)", "ok")
            else:
                _extract(arc_path, drive_root)
                state.log(f"{label} — установлен", "ok")

            local_comp[key] = ver
            _save_local_comp(local_comp)

            try:
                os.remove(arc_path)
            except Exception:
                pass

        state.push("upd_progress", {"text": "✓  Все компоненты установлены.", "pct": 100})
        state.log("═══ Обновление завершено успешно ═══", "ok")
        _ulog("═══ Обновление завершено успешно ═══")

        if has_root:
            _restart_after_update(
                root_exe_tmp=root_exe_tmp,
                drive_root=drive_root,
                tmp_dir=tmp_dir,
                upd_log_path=upd_log_path,
            )
        else:
            state.push("upd_progress", {
                "text":    "✓  Обновление применено. Перезапуск не требуется.",
                "pct":     100,
                "done":    True,
                "restart": False,
            })
            _upd_tmp_dir = None
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    except Exception as e:
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
        _upd_tmp_dir = None
        if str(e) == "cancelled":
            return
        state.log(f"Ошибка обновления: {e}", "err")
        _ulog(f"ОШИБКА: {e}")
        state.push("upd_progress", {"text": f"⚠  Ошибка: {e}", "pct": None, "error": True})


def _restart_after_update(
    root_exe_tmp: str | None,
    drive_root: str,
    tmp_dir: str,
    upd_log_path: str,
) -> None:
    """Write a BAT file that replaces the exe after the process exits, then quit."""
    global _upd_tmp_dir

    exe_dst  = os.path.join(drive_root, "_ALFAscript.exe")
    src_size = os.path.getsize(root_exe_tmp) if root_exe_tmp else 0

    state.push("upd_progress", {
        "text":    "Перезапуск ALFAscript…",
        "pct":     100,
        "done":    True,
        "restart": True,
    })
    state.log("Закрываю ALFAscript для замены exe…", "info")

    bat_path = os.path.join(_APP_DIR, "restart_alfa.bat")

    def _blog(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        return f'echo [{ts}] {msg} >> "{upd_log_path}"\n'

    bat_text = (
        "@echo off\n"
        "title ALFAscript Updater\n"
        + _blog("BAT START: waiting for _ALFAscript.exe to exit")
        + ":wait\n"
        "tasklist /fi \"imagename eq _ALFAscript.exe\" 2>nul"
        " | find /i \"_ALFAscript.exe\" >nul\n"
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\n"
        + _blog("BAT STEP 1: process exited, copying exe")
        + (
            f'copy /y "{root_exe_tmp}" "{exe_dst}"\n'
            f'if errorlevel 1 (echo [ERR] copy failed >> "{upd_log_path}" & goto :fail)\n'
            f'for %%F in ("{exe_dst}") do if %%~zF LSS {src_size} '
            f'(echo [ERR] size mismatch >> "{upd_log_path}" & goto :fail)\n'
            f'echo [OK] copy OK size={src_size} >> "{upd_log_path}"\n'
            if root_exe_tmp else ""
        )
        + _blog("BAT STEP 2: cleaning _MEI* from TEMP")
        + "for /d %%i in (\"%TEMP%\\_MEI*\") do rmdir /s /q \"%%i\" 2>nul\n"
        + "for /d %%i in (\"C:\\Windows\\Temp\\_MEI*\") do rmdir /s /q \"%%i\" 2>nul\n"
        + _blog("BAT STEP 3: removing tmp dir")
        + f'rmdir /s /q "{tmp_dir}" 2>nul\n'
        + _blog("BAT STEP 4: pause 3s for filesystem flush")
        + "ping -n 4 127.0.0.1 >nul\n"
        + _blog("BAT STEP 5: showing completion notification")
        + 'mshta "javascript:var s=new ActiveXObject(\'WScript.Shell\');'
          "s.Popup('Update done! Run _ALFAscript.exe',0,'ALFAscript Updater',64);close();\"\n"
        + _blog("BAT DONE")
        + f'del /f /q "{bat_path}"\n'
        + "goto :eof\n"
        + ":fail\n"
        + 'mshta "javascript:var s=new ActiveXObject(\'WScript.Shell\');'
          "s.Popup('Update FAILED! See updatelog.txt',0,'ALFAscript Updater',16);close();\"\n"
        + _blog("BAT FAIL: notified user")
        + f'del /f /q "{bat_path}"\n'
    )

    with open(bat_path, "w", encoding="cp1251", errors="replace") as bf:
        bf.write(bat_text)

    subprocess.Popen(["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    _upd_tmp_dir = None
    time.sleep(1.2)
    os._exit(0)
