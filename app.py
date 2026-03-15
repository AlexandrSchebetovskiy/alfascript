# =============================================================================
#  ALFAscript 6.6.6  —  by FRUSTIK  (Flask + pywebview edition)
# =============================================================================

import os, sys, glob, ctypes, re, json, time, subprocess, threading, queue, shutil
from datetime import datetime
import urllib.request, urllib.error, urllib.parse
from flask import Flask, render_template, request, jsonify, Response, stream_with_context


# =============================================================================
#  НАСТРОЙКИ
# =============================================================================

CURRENT_VERSION   = "6.6.6"
CURRENT_DATE      = "04.03.2026"

def find_multilaunch():
    base = os.path.dirname(sys.executable if getattr(sys,'frozen',False) else os.path.abspath(__file__))
    candidate = os.path.join(base, "multilaunch")
    if os.path.isdir(candidate): return candidate
    if os.path.basename(base).lower() == "multilaunch": return base
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        path = f"{letter}:\\multilaunch"
        if os.path.isdir(path): return path
    return None

def _read_date_from_local_comp():
    """Читает дату билда из multilaunch\components_local.json (ключ main).
    Версия всегда фиксирована (CURRENT_VERSION), меняется только дата."""
    try:
        ml = find_multilaunch()
        if ml:
            path = os.path.join(ml, "components_local.json")
            if os.path.isfile(path):
                with open(path, encoding="utf-8-sig") as f:
                    data = json.load(f)
                main = data.get("main")
                if isinstance(main, dict):
                    date = main.get("version", "")
                elif isinstance(main, str):
                    date = main  # старый формат — строка напрямую
                else:
                    date = ""
                if date:
                    return date.strip()
    except Exception:
        pass
    return CURRENT_DATE

# Дата берётся из components_local.json (ключ main.version), версия всегда фиксирована
CURRENT_DATE = _read_date_from_local_comp()
UPDATE_FOLDER_URL = "https://disk.yandex.ru/d/Xq2vFGbe0n5dYA"

CPU_WARN = 85; CPU_CRIT = 95
GPU_WARN = 80; GPU_CRIT = 90
VRM_WARN = 90; VRM_CRIT = 110

TASKS = [
    ("ПОДГОТОВКА", [
        ("Включить профиль производительности", "10_nosleep.bat",        True),
        ("Установка драйверов SDI",             "11_runsdi.bat",         True),
        ("Проверка интернет соединения",        "01_inetnew.bat",        True),
    ]),
    ("НАСТРОЙКА", [
        ("Тёмная тема",                         "02_temad.bat",          False),
        ("Светлая тема",                        "02_temaw.bat",          False),
        ("Установка библиотек",                 "03_biblioteki.bat",     True),
        ("Создание ярлыков",                    "05_shortcuts.bat",      True),
        ("Активация Win + Office",              "07_aktiv.bat",          True),
        ("Установка Яндекс Браузера",           "13_yabrowser.bat",      True),
    ]),
    ("ТЕСТЫ", [
        ("AIDA + FurMark · 5 мин",              "04_tests.bat",          True),
        ("AIDA + FurMark · 5 часов",            "99_testnotimelimit.bat",False),
    ]),
    ("ОБСЛУЖИВАНИЕ", [
        ("Финальная очистка",                   "12_cleanup.bat",        True),
    ]),
]

PRESETS = {
    "⚡  Полный скрипт":          ["10_nosleep.bat","11_runsdi.bat","01_inetnew.bat","02_temad.bat","03_biblioteki.bat","05_shortcuts.bat","07_aktiv.bat","13_yabrowser.bat","04_tests.bat","12_cleanup.bat"],
    "📦  Мини (образ ALFA)":      ["11_runsdi.bat","10_nosleep.bat","01_inetnew.bat","04_tests.bat","07_aktiv.bat","13_yabrowser.bat","12_cleanup.bat"],
    "🌙  Без тестов — тёмная":    ["10_nosleep.bat","11_runsdi.bat","01_inetnew.bat","02_temad.bat","03_biblioteki.bat","05_shortcuts.bat","07_aktiv.bat","13_yabrowser.bat","12_cleanup.bat"],
    "☀️  Без тестов — светлая":   ["10_nosleep.bat","11_runsdi.bat","01_inetnew.bat","02_temaw.bat","03_biblioteki.bat","05_shortcuts.bat","07_aktiv.bat","13_yabrowser.bat","12_cleanup.bat"],
}

EXTRAS = [
    ("💾", "Бэкап драйверов",         "08_drv_backup.bat"),
    ("♻️", "Восстановление драйверов", "09_drv_restore.bat"),
    ("🖥️", "Менеджер дисков",          "06_dskmgr.bat"),
    ("🔑", "Ручная активация",         None),
    ("📋", "Просмотр журнала",         ":cmd:perfmon /rel"),
    ("🔬", "Диагностика",              ":portmgr:"),
    ("📦", "Установка программ",       ":softmgr:"),
]

# =============================================================================
#  ПУТИ
# =============================================================================

MULTILAUNCH = find_multilaunch()

if getattr(sys, 'frozen', False):
    _MEIPASS = sys._MEIPASS
    _APP_DIR  = os.path.dirname(sys.executable)
else:
    _MEIPASS = os.path.abspath(os.path.dirname(__file__))
    _APP_DIR  = _MEIPASS

_BASE_DIR   = _APP_DIR
_THEME_FILE = os.path.join(MULTILAUNCH, "dependencies", "theme.json") if MULTILAUNCH else os.path.join(_APP_DIR, "theme.json")

# =============================================================================
#  ХЕЛПЕРЫ: 7-Zip, components_local.json
# =============================================================================

LOCAL_COMP_FILE = "components_local.json"   # multilaunch\components_local.json

def _find_7zip():
    """Ищет 7z.exe: _MEIPASS (встроен в exe) → рядом с exe → системный."""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(sys._MEIPASS, "7z.exe"))
    candidates += [
        os.path.join(_APP_DIR, "7z.exe"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    try:
        subprocess.call(["7z", "--help"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "7z"
    except FileNotFoundError:
        return None

def _load_local_comp() -> dict:
    """Читает multilaunch\\components_local.json. Возвращает {} если нет."""
    if not MULTILAUNCH:
        return {}
    path = os.path.join(MULTILAUNCH, LOCAL_COMP_FILE)
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f)
        # Нормализуем значения: если вдруг хранится объект — берём строку версии
        result = {}
        for k, v in raw.items():
            if isinstance(v, dict):
                v = v.get("version") or v.get("ver") or v.get("date") or ""
            result[k] = str(v) if v is not None else None
        return result
    except Exception:
        return {}

def _save_local_comp(data: dict):
    """Сохраняет components_local.json на флешку."""
    if not MULTILAUNCH:
        return
    path = os.path.join(MULTILAUNCH, LOCAL_COMP_FILE)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"Не удалось сохранить {LOCAL_COMP_FILE}: {e}", "warn")


def find_scripts_dir(ml):
    if not ml: return None
    try:
        for e in os.listdir(ml):
            if e.lower() == "scripts": return os.path.join(ml, e)
    except: pass
    return os.path.join(ml, "Scripts")

SCRIPTS_DIR = find_scripts_dir(MULTILAUNCH)

# =============================================================================
#  ПРАВА АДМИНИСТРАТОРА
# =============================================================================

def is_admin():
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except: return False

def run_as_admin():
    ctypes.windll.shell32.ShellExecuteW(None,"runas",sys.executable," ".join(sys.argv),None,1)
    sys.exit()

# =============================================================================
#  ТЕМА
# =============================================================================

# Палитра CSS-переменных для окна лога (синхронизация с index.html)
# Ключ: "{vstyle}_{vmode}"
_THEMES_DATA = {
    "default_dark":  {"bg":"#0f1117","glass":"#1a1d2e","border":"#2a2d3e","accent":"#7c3aed","text":"#e2e8f0","text_dim":"#64748b","green":"#22c55e","yellow":"#eab308","red":"#ef4444"},
    "default_light": {"bg":"#f1f5fb","glass":"#ffffff","border":"#e2e8f0","accent":"#7c3aed","text":"#0f172a","text_dim":"#64748b","green":"#059669","yellow":"#d97706","red":"#dc2626"},
    "latte_light":   {"bg":"#fdf8f0","glass":"rgba(255,251,243,.88)","border":"rgba(180,83,9,.15)","accent":"#b45309","text":"#1c0f00","text_dim":"#78350f","green":"#15803d","yellow":"#a16207","red":"#b91c1c"},
    "ocean_light":   {"bg":"#e0f2fe","glass":"rgba(255,255,255,.85)","border":"rgba(3,105,161,.18)","accent":"#0369a1","text":"#0c1a2e","text_dim":"#075985","green":"#0d6e3a","yellow":"#a16207","red":"#b91c1c"},
    "frost_dark":    {"bg":"#0d1520","glass":"rgba(30,41,59,.72)","border":"rgba(148,163,184,.2)","accent":"#818cf8","text":"#f1f5f9","text_dim":"#94a3b8","green":"#10b981","yellow":"#f59e0b","red":"#ef4444"},
    "frost_light":   {"bg":"#e8eeff","glass":"rgba(255,255,255,.7)","border":"rgba(199,210,254,.8)","accent":"#7c3aed","text":"#1e293b","text_dim":"#475569","green":"#059669","yellow":"#d97706","red":"#dc2626"},
    "meadow_light":  {"bg":"#f0fdf4","glass":"rgba(255,255,255,.85)","border":"rgba(22,163,74,.18)","accent":"#16a34a","text":"#052e16","text_dim":"#166534","green":"#16a34a","yellow":"#a16207","red":"#b91c1c"},
    "ember_dark":    {"bg":"#0d0200","glass":"rgba(20,8,0,.82)","border":"rgba(251,146,60,.18)","accent":"#fb923c","text":"#fef3c7","text_dim":"#d4a574","green":"#65a30d","yellow":"#eab308","red":"#ef4444"},
    "ember_light":   {"bg":"#fff7ed","glass":"#ffffff","border":"#fed7aa","accent":"#ea580c","text":"#431407","text_dim":"#9a3412","green":"#15803d","yellow":"#ca8a04","red":"#dc2626"},
    "sakura_dark":   {"bg":"#12020a","glass":"rgba(30,5,20,.84)","border":"rgba(249,168,212,.2)","accent":"#ec4899","text":"#fce7f3","text_dim":"#f9a8d4","green":"#34d399","yellow":"#fbbf24","red":"#f87171"},
    "sakura_light":  {"bg":"#fff5f9","glass":"rgba(255,255,255,.72)","border":"rgba(249,168,212,.65)","accent":"#db2777","text":"#500724","text_dim":"#9d174d","green":"#059669","yellow":"#d97706","red":"#dc2626"},
    "void_dark":     {"bg":"#08090a","glass":"#0d0e0f","border":"rgba(255,255,255,.07)","accent":"#94a3b8","text":"#e2e8f0","text_dim":"#475569","green":"#22c55e","yellow":"#eab308","red":"#ef4444"},
    "void_light":    {"bg":"#fafafa","glass":"#ffffff","border":"#e5e7eb","accent":"#6b7280","text":"#111827","text_dim":"#6b7280","green":"#059669","yellow":"#d97706","red":"#dc2626"},
    "matrix_dark":   {"bg":"#000500","glass":"rgba(0,5,0,.9)","border":"rgba(0,255,65,.16)","accent":"#00ff41","text":"#00ff41","text_dim":"#00aa2a","green":"#00ff41","yellow":"#ffe600","red":"#ff3333"},
    "matrix_light":  {"bg":"#f0fdf4","glass":"#ffffff","border":"#a7f3d0","accent":"#16a34a","text":"#052e16","text_dim":"#166534","green":"#059669","yellow":"#ca8a04","red":"#dc2626"},
    "sunset_dark":   {"bg":"#0a0108","glass":"rgba(15,3,5,.7)","border":"rgba(245,158,11,.18)","accent":"#f59e0b","text":"#fef3c7","text_dim":"#fbbf24","green":"#65a30d","yellow":"#eab308","red":"#ef4444"},
    "sunset_light":  {"bg":"#fff7ed","glass":"#ffffff","border":"#fde68a","accent":"#d97706","text":"#451a03","text_dim":"#92400e","green":"#15803d","yellow":"#ca8a04","red":"#dc2626"},
    "neon_dark":     {"bg":"#080014","glass":"rgba(18,0,34,.82)","border":"rgba(232,121,249,.2)","accent":"#e879f9","text":"#fdf4ff","text_dim":"#d8b4fe","green":"#4ade80","yellow":"#facc15","red":"#fb7185"},
    "abyss_dark":    {"bg":"#010810","glass":"rgba(1,14,32,.84)","border":"rgba(34,211,238,.16)","accent":"#22d3ee","text":"#e0f2fe","text_dim":"#7dd3fc","green":"#22c55e","yellow":"#fbbf24","red":"#f87171"},
    "blood_dark":    {"bg":"#0c0003","glass":"rgba(18,0,6,.84)","border":"rgba(244,63,94,.17)","accent":"#f43f5e","text":"#fff1f2","text_dim":"#fda4af","green":"#4ade80","yellow":"#fbbf24","red":"#f43f5e"},
    "aurora_dark":   {"bg":"#01080f","glass":"rgba(1,12,26,.76)","border":"rgba(16,185,129,.18)","accent":"#10b981","text":"#ecfdf5","text_dim":"#6ee7b7","green":"#10b981","yellow":"#fbbf24","red":"#f87171"},
    "coal_dark":     {"bg":"#0b0b0b","glass":"rgba(16,16,16,.92)","border":"rgba(161,161,170,.11)","accent":"#a1a1aa","text":"#f4f4f5","text_dim":"#a1a1aa","green":"#22c55e","yellow":"#eab308","red":"#ef4444"},
    "cloud_light":   {"bg":"#f0f9ff","glass":"rgba(255,255,255,.82)","border":"rgba(14,165,233,.2)","accent":"#0ea5e9","text":"#0c2340","text_dim":"#0369a1","green":"#0d9488","yellow":"#ca8a04","red":"#dc2626"},
    "peach_light":   {"bg":"#fff5f0","glass":"rgba(255,255,255,.86)","border":"rgba(249,115,22,.18)","accent":"#f97316","text":"#3b1003","text_dim":"#9a3412","green":"#15803d","yellow":"#ca8a04","red":"#dc2626"},
    "mint_light":    {"bg":"#f0fffe","glass":"rgba(255,255,255,.86)","border":"rgba(13,148,136,.18)","accent":"#0d9488","text":"#042f2e","text_dim":"#0f766e","green":"#15803d","yellow":"#ca8a04","red":"#dc2626"},
    "lavender_light":{"bg":"#faf5ff","glass":"rgba(255,255,255,.8)","border":"rgba(147,51,234,.18)","accent":"#9333ea","text":"#2d0a5e","text_dim":"#6b21a8","green":"#15803d","yellow":"#ca8a04","red":"#dc2626"},
    "gold_light":    {"bg":"#fffbeb","glass":"rgba(255,255,255,.86)","border":"rgba(217,119,6,.2)","accent":"#d97706","text":"#451a03","text_dim":"#92400e","green":"#15803d","yellow":"#d97706","red":"#dc2626"},
}

def _load_appearance():
    """Читает vstyle и vmode из файла настроек."""
    try:
        with open(_THEME_FILE,"r",encoding="utf-8") as f:
            d = json.load(f)
        return d.get("vstyle","default"), d.get("vmode","dark")
    except: pass
    return "default", "dark"

def _save_appearance(vstyle, vmode):
    """Сохраняет vstyle и vmode в файл настроек."""
    try:
        with open(_THEME_FILE,"w",encoding="utf-8") as f:
            json.dump({"vstyle": vstyle, "vmode": vmode}, f)
    except: pass

# =============================================================================
#  ЗАПУСК BAT
# =============================================================================

def run_bat(bat_path, log_cb, double_run=False):
    runs = 2 if double_run else 1
    last_rc = 0
    for run_num in range(runs):
        if double_run: log_cb(f"  Запуск {run_num+1} из 2...", "muted")
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            proc = subprocess.Popen(["cmd","/C",bat_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                shell=False, startupinfo=si, encoding=None,
                cwd=os.path.dirname(bat_path) or ".")
            for raw in proc.stdout:
                try: line = raw.decode("utf-8").rstrip()
                except:
                    try: line = raw.decode("cp866").rstrip()
                    except: line = raw.decode("utf-8",errors="replace").rstrip()
                line = line.lstrip("\ufeff\ufffe\x00")
                if not line.strip(): continue
                if any(x in line for x in ("[!]","ВНИМАНИЕ","Ошибка","ERROR","WARN")):
                    log_cb(line.strip(),"warn")
                elif "[i]" in line:
                    log_cb(line.replace("[i]","").strip(),"info")
                elif any(x in line for x in ("✓","выполнено","complete","завершен","завершён")):
                    log_cb(line.strip(),"ok")
                else:
                    log_cb(line.strip(),"muted")
            proc.wait()
            last_rc = proc.returncode
        except FileNotFoundError:
            log_cb(f"Файл не найден: {bat_path}","err"); return False,-1
        except Exception as e:
            log_cb(f"Ошибка запуска: {e}","err"); return False,-1
    return last_rc in (0,255), last_rc

# =============================================================================
#  AIDA64
# =============================================================================

def find_latest_aida_csv():
    dirs = [r'C:\Windows\Temp']
    for k in ('TEMP','TMP'):
        v = os.environ.get(k,'')
        if v and os.path.isdir(v) and v not in dirs: dirs.append(v)
    files = []
    for d in dirs: files.extend(glob.glob(os.path.join(d,'aida64_sst_*_stat.csv')))
    return max(files, key=os.path.getmtime) if files else None

def find_latest_aida_log_csv():
    dirs = [r'C:\Windows\Temp']
    for k in ('TEMP','TMP'):
        v = os.environ.get(k,'')
        if v and os.path.isdir(v) and v not in dirs: dirs.append(v)
    files = []
    for d in dirs: files.extend(glob.glob(os.path.join(d,'aida64_sst_*_log.csv')))
    return max(files, key=os.path.getmtime) if files else None

def parse_aida_stat_csv(csv_file):
    try:
        text = None
        for enc in ('utf-16','utf-16-le','utf-8-sig','utf-8'):
            try:
                with open(csv_file,encoding=enc,errors='strict') as f: text=f.read(); break
            except: continue
        if not text: return None
        lines = text.splitlines()
        if len(lines) < 9: return None
        def cell(line,i):
            p=line.split(';'); return p[i].strip() if i<len(p) else ''
        def pf(s):
            try: return float(s.replace(',','.'))
            except: return None
        start_str = cell(lines[4],1) if len(lines)>4 else ''
        end_str   = cell(lines[5],1) if len(lines)>5 else ''
        duration = '—'
        for fmt in ('%d.%m.%Y %H:%M:%S','%d.%m.%Y %H:%M','%Y-%m-%d %H:%M:%S'):
            try:
                t1=datetime.strptime(start_str,fmt); t2=datetime.strptime(end_str,fmt)
                s=abs((t2-t1).total_seconds()); duration=f'{int(s//60)} мин {int(s%60)} сек'; break
            except: continue
        result = {'cpu_max':None,'gpu_max':None,'gpu_hotspot_max':None,'vrm_max':None,
                  'cpu_power_max':None,'throttle':None,'duration':duration}
        cpu_cands=[]; gpu_val=None; gpu_hotspot=None; vrm_val=None; cpu_power=None
        for line in lines[8:]:
            if not line.strip(): continue
            name=cell(line,0).lower(); unit=cell(line,1); mx=pf(cell(line,5))
            if unit=='°C':
                if name in ('цп диод','cpu diode'): cpu_cands.append((0,mx))
                elif name in ('цп','cpu'): cpu_cands.append((1,mx))
                elif name in ('графический процессор','gpu'):
                    if gpu_val is None or (mx and mx>gpu_val): gpu_val=mx
                elif 'hotspot' in name:
                    if gpu_hotspot is None or (mx and mx>gpu_hotspot): gpu_hotspot=mx
                elif name in ('mos','vrm','дроссели'):
                    if vrm_val is None or (mx and mx>vrm_val): vrm_val=mx
            elif unit=='W':
                if name in ('весь цп','cpu power','cpu package power'):
                    if cpu_power is None or (mx and mx>cpu_power): cpu_power=mx
        if cpu_cands:
            cpu_cands.sort(key=lambda x:(x[0],-(x[1] or 0)))
            result['cpu_max']=int(cpu_cands[0][1]) if cpu_cands[0][1] else None
        result['gpu_max']        =int(gpu_val)     if gpu_val     else None
        result['gpu_hotspot_max']=int(gpu_hotspot) if gpu_hotspot else None
        result['vrm_max']        =int(vrm_val)     if vrm_val     else None
        result['cpu_power_max']  =int(cpu_power)   if cpu_power   else None
        if result['cpu_max'] is None and result['gpu_max'] is None: return None
        return result
    except: return None

def detect_cpu_throttle(log_file):
    try:
        text = None
        for enc in ('utf-16','utf-16-le','utf-8-sig','utf-8'):
            try:
                with open(log_file,encoding=enc,errors='strict') as f: text=f.read(); break
            except: continue
        if not text: return None
        lines = text.splitlines()
        if len(lines)<10: return None
        cpu_line=lines[1].lower() if len(lines)>1 else ''
        is_intel='intel' in cpu_line
        CPU_THROTTLE_TEMP=97.0 if is_intel else 92.0
        headers=lines[6].split(';'); units=lines[7].split(';')
        def find_col(name,unit):
            for i,(h,u) in enumerate(zip(headers,units)):
                if h.strip()==name and u.strip()==unit: return i
            return None
        col_load=find_col('ЦП','%')
        col_temp=find_col('ЦП','°C') if is_intel else find_col('ЦП диод','°C')
        if col_temp is None: col_temp=find_col('ЦП','°C')
        core_cols=[i for i,(h,u) in enumerate(zip(headers,units)) if 'Частота ядра ЦП' in h and u.strip()=='MHz']
        if not core_cols:
            agg=find_col('ЦП','MHz')
            if agg: core_cols=[agg]
        if col_load is None or not core_cols: return None
        def val(row,col):
            if col is None or col>=len(row): return None
            try: return float(row[col].strip().replace(',','.'))
            except: return None
        samples=[]
        for line in lines[8:]:
            if not line.strip(): continue
            row=line.split(';'); load=val(row,col_load)
            if load is None or load<90: continue
            freqs=[val(row,c) for c in core_cols]; freqs=[f for f in freqs if f and f>100]
            if not freqs: continue
            samples.append((sum(freqs)/len(freqs),val(row,col_temp)))
        if not samples: return None
        sorted_f=sorted(s[0] for s in samples); p90=sorted_f[max(0,int(len(sorted_f)*0.9)-1)]
        thresh=p90*0.8; throttle=None
        for avg_f,temp in samples:
            if avg_f<thresh:
                if temp and temp>=CPU_THROTTLE_TEMP: throttle='TEMP'; break
                else: throttle='VRM'
        return throttle
    except: return None

def get_temp_status(v,warn,crit):
    if v is None: return "ok"
    if v>=crit: return "crit"
    if v>=warn: return "warn"
    return "ok"

# =============================================================================
#  СКАНИРОВАНИЕ ПРОГРАММ
# =============================================================================

def scan_programs(folder, exclude_subfolders=None):
    """Сканирует папку и возвращает список программ (.exe/.msi) с иконками.
    exclude_subfolders — список имён подпапок для пропуска (регистронезависимо)."""
    if exclude_subfolders is None:
        exclude_subfolders = []
    exclude_lower = {e.lower() for e in exclude_subfolders}

    programs = []
    if not folder or not os.path.isdir(folder): return programs
    try:
        for entry in sorted(os.listdir(folder)):
            if entry.lower() in exclude_lower: continue
            entry_path = os.path.join(folder, entry)
            # Прямой файл в папке
            if os.path.isfile(entry_path):
                ext = os.path.splitext(entry)[1].lower()
                if ext in ('.exe', '.msi'):
                    programs.append({
                        "name": os.path.splitext(entry)[0],
                        "path": entry_path,
                        "icon": None,
                    })
                continue
            # Подпапка — ищем exe/msi + icon.png
            if os.path.isdir(entry_path):
                exe_path = None
                icon_path = None
                for icon_name in ("icon.png", "icon.ico", "Icon.png", "Icon.ico"):
                    candidate_icon = os.path.join(entry_path, icon_name)
                    if os.path.isfile(candidate_icon):
                        icon_path = candidate_icon
                        break
                # Проверяем launch.txt
                launch_txt = os.path.join(entry_path, "launch.txt")
                if os.path.isfile(launch_txt):
                    try:
                        with open(launch_txt, encoding='utf-8', errors='replace') as lf:
                            exe_name = lf.read().strip()
                        candidate = os.path.join(entry_path, exe_name)
                        if os.path.isfile(candidate): exe_path = candidate
                    except: pass
                if not exe_path:
                    for f in sorted(os.listdir(entry_path)):
                        ext = os.path.splitext(f)[1].lower()
                        if ext in ('.exe', '.msi'):
                            exe_path = os.path.join(entry_path, f)
                            break
                if exe_path:
                    programs.append({
                        "name": entry,
                        "path": exe_path,
                        "icon": icon_path,
                    })
    except: pass
    return programs

# =============================================================================
#  ОБНОВЛЕНИЯ
# =============================================================================

def check_for_update():
    """Скачивает components.json с Яндекс.Диска, сравнивает с локальными версиями.
    Возвращает dict со списком компонентов требующих обновления."""
    try:
        UA = "ALFAscript-Updater/1.0"
        import ssl as _ssl
        _ctx = _ssl.create_default_context()
        _ctx.check_hostname = False
        _ctx.verify_mode = _ssl.CERT_NONE

        def _get_dl_url(pk, path=""):
            url = (f"https://cloud-api.yandex.net/v1/disk/public/resources/download"
                   f"?public_key={urllib.parse.quote(pk, safe='')}")
            if path:
                url += f"&path={urllib.parse.quote(path, safe='')}"
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10, context=_ctx) as r:
                return json.loads(r.read())["href"]

        def _read_json(pk, path):
            direct = _get_dl_url(pk, path)
            req = urllib.request.Request(direct, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
                return json.loads(r.read().decode("utf-8-sig"))

        def _read_txt(pk, path, keep_empty=False):
            direct = _get_dl_url(pk, path)
            req = urllib.request.Request(direct, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10, context=_ctx) as r:
                raw = r.read().decode("utf-8-sig")
            lines = raw.splitlines()
            if keep_empty:
                return [l.rstrip() for l in lines]
            return [l.strip() for l in lines if l.strip()]

        def _to_tuple(s):
            """DD.MM.YYYY или YYYY.MM.DD → (yyyy, mm, dd)."""
            try:
                p = s.strip().split(".")
                if len(p) == 3:
                    if len(p[2]) == 4:      # DD.MM.YYYY
                        return (int(p[2]), int(p[1]), int(p[0]))
                    elif len(p[0]) == 4:    # YYYY.MM.DD
                        return (int(p[0]), int(p[1]), int(p[2]))
            except Exception:
                pass
            return (0, 0, 0)

        def _fmt(s):
            """YYYY.MM.DD → DD.MM.YYYY для отображения."""
            if not isinstance(s, str):
                return str(s) if s is not None else ""
            try:
                p = s.strip().split(".")
                if len(p) == 3 and len(p[0]) == 4:
                    return f"{p[2]}.{p[1]}.{p[0]}"
            except Exception:
                pass
            return s

        # ── 1. Скачиваем components.json ────────────────────────
        remote_comp = None
        try:
            remote_comp = _read_json(UPDATE_FOLDER_URL, "/components.json")
        except Exception as e:
            return {"error": f"Не удалось загрузить components.json: {e}"}

        if not remote_comp:
            return {"error": "components.json пуст или недоступен"}

        # ── 2. changelog ─────────────────────────────────────────
        changelog = None
        try:
            cl_lines = _read_txt(UPDATE_FOLDER_URL, "/changelog.txt", keep_empty=True)
            while cl_lines and not cl_lines[0]:  cl_lines.pop(0)
            while cl_lines and not cl_lines[-1]: cl_lines.pop()
            changelog = "\n".join(cl_lines) if cl_lines else None
        except Exception:
            pass

        # ── 3. Локальные версии ──────────────────────────────────
        local_comp = _load_local_comp()

        # ── 4. Сравниваем по компонентам ─────────────────────────
        updates_standard = []
        updates_heavy    = []
        total_dl_mb      = 0.0
        has_root_update  = False

        for key, rcomp in remote_comp.items():
            comp_type  = rcomp.get("type", "standard")
            remote_ver = rcomp.get("version", "")
            local_ver  = local_comp.get(key)
            size_mb    = rcomp.get("size_mb", 0)

            remote_t      = _to_tuple(remote_ver)
            local_t       = _to_tuple(local_ver) if local_ver else (0, 0, 0)
            not_installed = local_ver is None
            needs_update  = remote_t > local_t or not_installed

            entry = {
                "key":          key,
                "file":         rcomp.get("file", ""),
                "display_name": rcomp.get("display_name", key),
                "remote_ver":   _fmt(remote_ver),
                "local_ver":    _fmt(local_ver) if local_ver else None,
                "size_mb":      size_mb,
                "needs_update": needs_update,
                "not_installed": not_installed,
                "target":       rcomp.get("target", "."),
                "type":         comp_type,
            }

            if comp_type == "standard":
                updates_standard.append(entry)
                if needs_update:
                    total_dl_mb += size_mb
                    if key == "main":
                        has_root_update = True
            elif comp_type == "heavy":
                updates_heavy.append(entry)

        has_update       = any(c["needs_update"] for c in updates_standard)
        has_heavy_update = any(c["needs_update"] for c in updates_heavy)

        remote_root    = remote_comp.get("main", {})
        raw_ver        = remote_root.get("version", "")
        display_ver    = _fmt(raw_ver) if raw_ver and raw_ver != "unknown" else None
        local_root_ver = local_comp.get("main")
        display_local  = _fmt(local_root_ver) if local_root_ver else None

        return {
            "has_update":        has_update,
            "has_root_update":   has_root_update,
            "has_heavy_update":  has_heavy_update,
            "version":         display_ver,
            "date":            display_ver,          # обратная совместимость с UI
            "local_date":      display_local,
            "changelog":       changelog,
            "total_dl_mb":     round(total_dl_mb, 1),
            "standard":        updates_standard,
            "heavy":           updates_heavy,
            "folder":          "",                   # больше не используется
        }

    except Exception as e:
        return {"error": str(e)}

# =============================================================================
#  ДАННЫЕ О ЖЕЛЕЗЕ (WMI + smartctl)
# =============================================================================

_hw_info  = {}   # кэш WMI-данных
_hw_smart = None # кэш smartctl: None=ещё не запускался, {}=нет данных

_PS_HW = (
    "$cpu = (Get-WmiObject Win32_Processor | Select-Object -First 1).Name.Trim();"
    "$mb = (Get-WmiObject Win32_BaseBoard | Select-Object -First 1);"
    "$mb_str = ($mb.Manufacturer.Trim() + ' ' + $mb.Product.Trim()).Trim();"
    "$ram_obj = Get-WmiObject Win32_PhysicalMemory;"
    "$ram_gb  = [math]::Round(($ram_obj | Measure-Object -Property Capacity -Sum).Sum / 1GB);"
    "$ram_mhz = ($ram_obj | Select-Object -First 1).Speed;"
    "$mem_type_code = ($ram_obj | Select-Object -First 1).SMBIOSMemoryType;"
    "$ddr = switch ($mem_type_code) { 24 {'DDR3'} 26 {'DDR4'} 34 {'DDR5'} default {'DDR?'} };"
    r'$ram_str = "${ram_gb}GB $ddr ${ram_mhz}MHz";'
    "$gpu_all = Get-WmiObject Win32_VideoController | Where-Object {"
    "  $_.Name -notmatch 'Virtual|Remote|Indirect|IDD|ParsecVDA|ZeroDisplay'"
    "};"
    "$gpu_pref = $gpu_all | Where-Object { $_.Name -match 'NVIDIA|AMD|Radeon|GeForce|Quadro|Arc' } | Select-Object -First 1;"
    "$gpu = if ($gpu_pref) { $gpu_pref.Name.Trim() }"
    "  elseif ($gpu_all) { ($gpu_all | Select-Object -First 1).Name.Trim() }"
    "  else { '---' };"
    "$sys_drive_letter = $env:SystemDrive.TrimEnd(':');"
    "$ldtp = Get-WmiObject Win32_LogicalDiskToPartition;"
    "$sys_part = $ldtp | Where-Object { ($_.Dependent -split([char]34))[1] -eq ($sys_drive_letter+':') };"
    "$sys_disk_idx = if ($sys_part) { ($sys_part.Antecedent -split 'Disk #')[1].Split(',')[0] } else { '0' };"
    "$all_disks = Get-WmiObject Win32_DiskDrive | Sort-Object Index;"
    "$msft_disks = Get-WmiObject -Namespace root\\Microsoft\\Windows\\Storage -Class MSFT_PhysicalDisk -ErrorAction SilentlyContinue;"
    "$disk_letters = @{};"
    "foreach ($lp in $ldtp) {"
    "  $didx = ($lp.Antecedent -split 'Disk #')[1].Split(',')[0];"
    "  $letter = ($lp.Dependent -split([char]34))[1];"
    "  if (-not $disk_letters.ContainsKey($didx)) { $disk_letters[$didx] = @() };"
    "  $disk_letters[$didx] += $letter"
    "};"
    "function Get-MediaStr($disk) {"
    "  $mt = 'UNK';"
    "  if ($disk.MediaType -match 'SSD|Solid') { $mt = 'SSD' }"
    "  elseif ($msft_disks) {"
    "    $md = $msft_disks | Where-Object { $_.FriendlyName -eq $disk.Model };"
    "    if ($md) { $mt = switch ($md.MediaType) { 4 {'SSD'} 3 {'HDD'} 5 {'NVMe'} default {'UNK'} } }"
    "  };"
    "  $gb = [math]::Round($disk.Size / 1GB);"
    "  $model = $disk.Model.Trim();"
    r'  $model = ($model -replace "(?i)\b(SSD|HDD|NVMe|Hard Drive|Solid State)\b","") -replace "\s+"," ";'
    r'  return "${gb}GB $mt ($model)"'
    "};"
    "$disk_lines = @(); $other_lines = @();"
    "foreach ($d in $all_disks) {"
    "  $info = Get-MediaStr $d;"
    "  $idx = [string]$d.Index;"
    "  if ($d.Index -eq [int]$sys_disk_idx) { $disk_lines += '[C:] ' + $info }"
    "  else {"
    "    $letters = $disk_letters[$idx];"
    "    $label = if ($letters) { '[' + ($letters -join ',') + ']' } else { '' };"
    "    $other_lines += if ($label) { $label + ' ' + $info } else { $info }"
    "  }"
    "};"
    "$all_disk_str = ($disk_lines + $other_lines) -join '~';"
    "$bios_obj = Get-WmiObject Win32_BIOS | Select-Object -First 1;"
    "$bios_date = '';"
    r"if ($bios_obj.ReleaseDate -match '^(\d{4})(\d{2})(\d{2})') { $bios_date = $Matches[3] + '.' + $Matches[2] + '.' + $Matches[1] };"
    r'Write-Output "CPU=$cpu|MB=$mb_str|RAM=$ram_str|GPU=$gpu|DISKS=$all_disk_str|BIOS=$bios_date"'
)

_PS_LETTERS = (
    "$ldtp = Get-WmiObject Win32_LogicalDiskToPartition;"
    "$drives = Get-WmiObject Win32_DiskDrive;"
    "$map = @{};"
    "foreach ($lp in $ldtp) {"
    "  $didx = ($lp.Antecedent -split 'Disk #')[1].Split(',')[0];"
    "  $letter = ($lp.Dependent -split([char]34))[1];"
    "  if (-not $map.ContainsKey($didx)) { $map[$didx] = @() };"
    "  $map[$didx] += $letter"
    "};"
    "foreach ($d in $drives) {"
    "  $idx = [string]$d.Index;"
    "  $ser = $d.SerialNumber.Trim();"
    "  $lets = if ($map.ContainsKey($idx)) { ($map[$idx]) -join ',' } else { '' };"
    "  Write-Output ($idx + '=' + $lets + '|' + $ser)"
    "}"
)

def _run_ps(script, timeout=20):
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout, startupinfo=si
        )
        return r.stdout.strip()
    except Exception:
        return ""

def _fetch_hw_info_ps():
    """Собирает данные о железе через PowerShell/WMI."""
    out = _run_ps(_PS_HW, timeout=20)
    info = {}
    for part in out.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            info[k.strip()] = v.strip()
    return info

def _fetch_smart():
    """Запускает smartctl через --scan (для получения типов -d), возвращает
    {letter: {health,pct,temp,hours,model}} — матчинг по model_name vs WMI."""
    global _hw_smart
    if _hw_smart is not None:
        return _hw_smart
    if not MULTILAUNCH:
        _hw_smart = {}; return _hw_smart

    smartctl = os.path.join(MULTILAUNCH, "dependencies", "smartctl", "smartctl.exe")
    if not os.path.isfile(smartctl):
        _hw_smart = {}; return _hw_smart

    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0

    # --scan даёт устройства с правильными -d флагами: /dev/sda -d ata # ...
    try:
        scan = subprocess.run([smartctl, "--scan"], capture_output=True, text=True,
                              timeout=10, startupinfo=si)
        scan_lines = [l for l in scan.stdout.splitlines() if l.strip()]
    except Exception:
        _hw_smart = {}; return _hw_smart

    # Собираем пары (dev, type_flag) — берём только первый флаг -d
    devices = []
    for line in scan_lines:
        parts = line.split()
        if not parts:
            continue
        dev = parts[0]
        dtype = None
        for j, p in enumerate(parts):
            if p == "-d" and j+1 < len(parts):
                dtype = parts[j+1]; break
        devices.append((dev, dtype))

    # WMI: получаем модели дисков с их буквами разделов
    # Формат _PS_LETTERS уже есть — используем отдельный PS для моделей
    ps_models = (
        "$ldtp = Get-WmiObject Win32_LogicalDiskToPartition;"
        "$map = @{};"
        "foreach ($lp in $ldtp) {"
        "  $didx = ($lp.Antecedent -split 'Disk #')[1].Split(',')[0];"
        "  $letter = ($lp.Dependent -split([char]34))[1];"
        "  if (-not $map.ContainsKey($didx)) { $map[$didx] = @() };"
        "  $map[$didx] += $letter"
        "};"
        "$drives = Get-WmiObject Win32_DiskDrive | Sort-Object Index;"
        "foreach ($d in $drives) {"
        "  $idx = [string]$d.Index;"
        "  $lets = if ($map.ContainsKey($idx)) { ($map[$idx]) -join ',' } else { '' };"
        "  $model = $d.Model.Trim();"
        "  Write-Output ($lets + '|' + $model)"
        "}"
    )
    # letter_by_model: {norm_model: [letters]}
    letter_by_model = {}
    for line in _run_ps(ps_models, timeout=10).splitlines():
        line = line.strip()
        if '|' not in line:
            continue
        lets_s, model_wmi = line.split('|', 1)
        letters = [x.strip() for x in lets_s.split(',') if x.strip()]
        nm = re.sub(r'\s+', ' ', model_wmi.strip().lower())
        letter_by_model[nm] = letters


    result = {}
    seen_devs = set()
    for dev, dtype in devices:
        # Пропускаем дублирующие пути (csmi* — это тот же диск что и sda)
        if dev in seen_devs:
            continue
        cmd = [smartctl, "-a", "-j", dev]
        if dtype:
            cmd += ["-d", dtype]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=15, startupinfo=si)
            data = json.loads(proc.stdout)
        except Exception as e:
            continue

        model  = data.get("model_name") or data.get("model_family") or ""
        ss     = data.get("smart_status", {})
        health = "good" if ss.get("passed") is True else "bad" if ss.get("passed") is False else "unknown"
        temp   = None
        temp_o = data.get("temperature", {})
        if isinstance(temp_o.get("current"), (int, float)):
            temp = int(temp_o["current"])
        hours  = None
        pot    = data.get("power_on_time", {})
        if isinstance(pot.get("hours"), (int, float)):
            hours = int(pot["hours"])
        pct    = None
        nvme_l = data.get("nvme_smart_health_information_log", {})
        if isinstance(nvme_l.get("percentage_used"), (int, float)):
            pct = max(0, 100 - int(nvme_l["percentage_used"]))
        if pct is None:
            wear_names = {"Wear_Leveling_Count","Media_Wearout_Indicator","Percent_Lifetime_Remain",
                          "Available_Reservd_Space","SSD_Life_Left","Remaining_Lifetime_Perc"}
            wear_ids   = {173,177,231,232,233,241}
            for attr in data.get("ata_smart_attributes", {}).get("table", []):
                if attr.get("name","") in wear_names or attr.get("id",0) in wear_ids:
                    val = attr.get("value") or attr.get("raw",{}).get("value")
                    if isinstance(val,(int,float)) and 0 <= val <= 100:
                        pct = int(val); break

        if not model:
            continue

        # Матчинг по model_name: ищем в letter_by_model
        nm = re.sub(r'\s+', ' ', model.strip().lower())
        letters = letter_by_model.get(nm)
        if letters is None:
            # Частичное совпадение: model из smartctl может быть короче WMI
            for wmi_m, lets in letter_by_model.items():
                if nm in wmi_m or wmi_m in nm:
                    letters = lets; break
        if letters is None:
            # Последний резерв: порядковый номер среди незанятых записей
            used = set(result.keys())
            for lets in letter_by_model.values():
                key_try = lets[0] if lets else None
                if key_try and key_try not in used:
                    letters = lets; break

        key = letters[0] if letters else f"__dev_{dev}__"
        result[key] = {"model": model, "health": health, "pct": pct, "temp": temp, "hours": hours}
        seen_devs.add(dev)

    _hw_smart = result
    return result

def _load_hw_info_bg():
    """Фоновый старт: WMI + smartctl."""
    global _hw_info
    _hw_info = _fetch_hw_info_ps()
    _fetch_smart()

# =============================================================================
#  FLASK APP + СОСТОЯНИЕ
# =============================================================================

_template_folder = os.path.join(_MEIPASS, 'templates')
app = Flask(__name__, template_folder=_template_folder)

_state = {
    "running": False,
    "cancel":  False,
    "tasks":   {bat: default for cat,tasks in TASKS for name,bat,default in tasks},
    "active_preset": "⚡  Полный скрипт",
    "progress": 0,
    "status":   "Готов",
    "status_type": "idle",
    "test_results": None,
}
_clients = []
_clients_lock = threading.Lock()
_log_history = []          # буфер всех лог-записей (макс. 2000)
_LOG_HISTORY_MAX = 2000

def _push(msg_type, data):
    payload = json.dumps({"type":msg_type,"data":data}, ensure_ascii=False)
    with _clients_lock:
        clients = list(_clients)
    for q in clients:
        try: q.put_nowait(payload)
        except: pass

def _log(text, level="info"):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"ts": ts, "text": text, "level": level}
    with _clients_lock:
        _log_history.append(entry)
        if len(_log_history) > _LOG_HISTORY_MAX:
            del _log_history[0]
    _push("log", entry)

# =============================================================================
#  FLASK ROUTES
# =============================================================================

@app.route("/")
def index():
    vstyle, vmode = _load_appearance()
    return render_template("index.html",
        tasks=TASKS, presets=list(PRESETS.keys()),
        extras=EXTRAS, version=CURRENT_VERSION, date=CURRENT_DATE,
        state=_state, multilaunch=MULTILAUNCH, is_admin=is_admin(),
        vstyle=vstyle, vmode=vmode)

@app.route("/log")
def log_window():
    vstyle, vmode = _load_appearance()
    return render_template("log.html",
        version=CURRENT_VERSION,
        themes=_THEMES_DATA,
        theme=f"{vstyle}_{vmode}")

def _get_os_ver():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        def _rv(name):
            try: return winreg.QueryValueEx(key, name)[0]
            except: return None
        major   = _rv("CurrentMajorVersionNumber")
        build   = int(_rv("CurrentBuildNumber") or 0)
        display = _rv("DisplayVersion") or _rv("ReleaseId") or ""
        winreg.CloseKey(key)
        if major is not None:
            ver = "11" if int(major) >= 10 and build >= 22000 else str(major)
            return f"Windows {ver} ({display})" if display else f"Windows {ver}"
    except Exception:
        pass
    return "Windows"

_net_status_cache = "..."  # заполняется фоновым потоком

def _refresh_net_status():
    global _net_status_cache
    _si = subprocess.STARTUPINFO()
    _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _si.wShowWindow = 0
    while True:
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "2000", "ya.ru"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                startupinfo=_si
            )
            _net_status_cache = "Подключена" if result.returncode == 0 else "Нет связи"
        except Exception:
            _net_status_cache = "Нет связи"
        time.sleep(30)

def _get_net_status():
    return _net_status_cache

def _get_sdi_date():
    if not MULTILAUNCH:
        return None
    drivers_dir = os.path.join(MULTILAUNCH, "SDI_RUS", "drivers")
    if not os.path.isdir(drivers_dir):
        return None
    try:
        latest_mtime = None
        for entry in os.scandir(drivers_dir):
            if entry.is_file(follow_symlinks=False):
                mtime = entry.stat().st_mtime
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
        if latest_mtime:
            dt = datetime.fromtimestamp(latest_mtime)
            return f"от {dt.month:02d}.{dt.year}"
    except Exception:
        pass
    return None

def _get_uac_status():
    """
    Возвращает 'Включён' или 'Выключен'.
    UAC считается выключенным если:
      - EnableLUA == 0  (полное отключение)
      - ИЛИ ConsentPromptBehaviorAdmin == 0 (ползунок на минимуме — 'Никогда не уведомлять')
    """
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System")
        enable_lua = winreg.QueryValueEx(key, "EnableLUA")[0]
        try:
            consent = winreg.QueryValueEx(key, "ConsentPromptBehaviorAdmin")[0]
        except FileNotFoundError:
            consent = 2  # дефолт = уведомлять
        winreg.CloseKey(key)
        if enable_lua == 0 or consent == 0:
            return "Выключен"
        return "Включён"
    except Exception:
        return "—"

@app.route("/api/state")
def api_state():
    vstyle, vmode = _load_appearance()
    return jsonify({
        "tasks": _state["tasks"],
        "active_preset": _state["active_preset"], "running": _state["running"],
        "status": _state["status"], "status_type": _state["status_type"],
        "progress": _state["progress"], "test_results": _state["test_results"],
        "multilaunch": MULTILAUNCH, "is_admin": is_admin(),
        "os_ver":     _get_os_ver(),
        "net_ok":     _get_net_status(),
        "sdi_date":   _get_sdi_date(),
        "uac_status": _get_uac_status(),
        "defender_excl": _get_defender_exclusion_status(),
        "vstyle":     vstyle,
        "vmode":      vmode,
        "thresholds": {
            "cpu_warn": CPU_WARN, "cpu_crit": CPU_CRIT,
            "gpu_warn": GPU_WARN, "gpu_crit": GPU_CRIT,
            "vrm_warn": VRM_WARN, "vrm_crit": VRM_CRIT,
        },
    })

@app.route("/api/disable_uac", methods=["POST"])
def api_disable_uac():
    """Отключает уведомления UAC: ConsentPromptBehaviorAdmin=0 (ползунок на минимум)."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "ConsentPromptBehaviorAdmin", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        _log("UAC отключён (ползунок на минимум). Перезагрузка не требуется.", "ok")
        return jsonify({"ok": True, "uac_status": _get_uac_status()})
    except Exception as e:
        _log(f"Ошибка отключения UAC: {e}", "err")
        return jsonify({"ok": False, "error": str(e)})


def _defender_target_paths():
    """Возвращает список папок для исключений Defender.
    - _APP_DIR      — папка рядом с exe на флешке (там лежат multilaunch, логи и т.д.)
    - _MEIPASS      — папка распаковки PyInstaller в %TEMP% (там python312.dll и т.д.)
    """
    paths = [_APP_DIR, _MEIPASS]
    return [p for p in paths if p]

def _is_path_excluded(excl_lower: str, target: str) -> bool:
    """Проверяет покрыт ли target (или любой его родитель) строкой исключений."""
    t = target.rstrip("\\").lower()
    for p in excl_lower.split("|"):
        p = p.strip().rstrip("\\")
        if not p:
            continue
        # exact match или target начинается с исключения (т.е. папка-родитель добавлена)
        if t == p or t.startswith(p + "\\"):
            return True
    return False

def _get_defender_exclusion_status():
    """Проверяет добавлены ли целевые папки в исключения Defender.
    Возвращает: 'Добавлены' / 'Частично' / 'Не добавлены' / 'Отключён' / '—'
    """
    try:
        _si2 = subprocess.STARTUPINFO()
        _si2.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si2.wShowWindow = 0
        result = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
             "(Get-MpPreference).ExclusionPath -join '|'"],
            capture_output=True, text=True, timeout=8, startupinfo=_si2
        )
        stderr = result.stderr.strip().lower()
        # Defender выключен — служба не запущена
        if "800106ba" in stderr or "800106b5" in stderr:
            return "Отключён"
        if result.returncode != 0:
            return "—"
        excl = result.stdout.strip().lower()
        paths = _defender_target_paths()
        statuses = [_is_path_excluded(excl, p) for p in paths]
        if all(statuses):  return "Добавлены"
        if any(statuses):  return "Частично"
        return "Не добавлены"
    except Exception:
        return "—"

def _apply_defender_exclusions():
    """Добавляет целевые папки в исключения Defender.
    Вызывается при старте (фоновый поток) и через API.
    Возвращает (ok: bool, message: str, disabled: bool).
    disabled=True означает что Defender выключен — это не ошибка.
    """
    if not is_admin():
        return False, "Требуются права администратора", False
    try:
        paths = _defender_target_paths()
        ps_cmd = "; ".join(f'Add-MpPreference -ExclusionPath "{p}"' for p in paths)
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0
        result = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15, startupinfo=_si
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # 0x800106ba — служба WinDefend не запущена (Defender отключён)
            # 0x800106b5 — аналогичная ошибка на некоторых системах
            if "800106ba" in stderr.lower() or "800106b5" in stderr.lower():
                return False, "Defender отключён на этой системе", True
            err = stderr or "неизвестная ошибка PowerShell"
            return False, err, False
        return True, ", ".join(paths), False
    except Exception as e:
        return False, str(e), False

@app.route("/api/add_defender_exclusions", methods=["POST"])
def api_add_defender_exclusions():
    """Вручную добавляет исключения Defender (из UI)."""
    ok, msg, disabled = _apply_defender_exclusions()
    if ok:
        _log(f"Defender: добавлены исключения → {msg}", "ok")
        return jsonify({"ok": True, "status": _get_defender_exclusion_status(), "added": msg})
    elif disabled:
        _log("Defender: служба отключена — исключения не требуются", "info")
        return jsonify({"ok": True, "status": "Отключён", "disabled": True})
    else:
        _log(f"Defender: ошибка — {msg}", "err")
        return jsonify({"ok": False, "error": msg})

@app.route("/api/vstyle", methods=["POST"])
def api_vstyle():
    """Сохраняет выбранный визуальный стиль и режим (dark/light)."""
    data = request.json or {}
    vstyle = data.get("vstyle", "default")
    vmode  = data.get("vmode",  "dark")
    _save_appearance(vstyle, vmode)
    return jsonify({"ok": True})

@app.route("/api/preset", methods=["POST"])
def api_preset():
    name = request.json.get("preset")
    if name not in PRESETS: return jsonify({"ok":False}),400
    bats = set(PRESETS[name])
    for bat in _state["tasks"]: _state["tasks"][bat] = bat in bats
    _state["active_preset"]=name
    _log(f"Применён пресет: {name.strip()}","info")
    return jsonify({"ok":True,"tasks":_state["tasks"]})

@app.route("/api/tasks", methods=["POST"])
def api_tasks():
    data=request.json.get("tasks",{})
    for bat,val in data.items():
        if bat in _state["tasks"]: _state["tasks"][bat]=bool(val)
    return jsonify({"ok":True})

@app.route("/api/run", methods=["POST"])
def api_run():
    if _state["running"]: return jsonify({"ok":False,"error":"Уже запущено"})
    if not MULTILAUNCH:   return jsonify({"ok":False,"error":"Папка multilaunch не найдена!"})
    tasks_to_run=[]
    for cat,tasks in TASKS:
        for name,bat,_ in tasks:
            if _state["tasks"].get(bat): tasks_to_run.append((name,bat))
    if not tasks_to_run: return jsonify({"ok":False,"error":"Выберите хотя бы одну задачу!"})
    _state["running"]=True; _state["cancel"]=False; _state["progress"]=0
    _push("status",{"running":True,"text":"Запуск...","type":"running","progress":0})
    threading.Thread(target=_run_thread,args=(tasks_to_run,),daemon=True).start()
    return jsonify({"ok":True})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    if _state["running"]:
        _state["cancel"]=True
        _log("⏹ Запрошена отмена — текущий шаг доработает до конца","warn")
        _push("status",{"running":True,"text":"Отмена...","type":"warn","progress":_state["progress"]})
    return jsonify({"ok":True})

@app.route("/api/extra", methods=["POST"])
def api_extra():
    bat  = request.json.get("bat")
    name = request.json.get("name","")
    # Ручная активация
    if bat is None:
        try:
            subprocess.Popen(["powershell","-ExecutionPolicy","Bypass","-NoExit",
                              "-Command","irm https://get.activated.win | iex"],
                              creationflags=subprocess.CREATE_NEW_CONSOLE)
            _log("▶ Запущена: Ручная активация","info")
        except Exception as e: _log(f"Ошибка: {e}","err")
        return jsonify({"ok":True})
    if isinstance(bat,str) and bat.startswith(":cmd:"):
        cmd=bat[5:]
        try: subprocess.Popen(cmd,shell=True); _log(f"▶ Запущен: {name}","info")
        except Exception as e: _log(f"Ошибка: {e}","err")
        return jsonify({"ok":True})
    if isinstance(bat,str) and bat.startswith(":softmgr:"):
        return jsonify({"ok":True,"action":"softmgr"})
    if isinstance(bat,str) and bat.startswith(":portmgr:"):
        return jsonify({"ok":True,"action":"portmgr"})
    # Обычный bat
    if _state["running"]: return jsonify({"ok":False,"error":"Уже запущено"})
    if not SCRIPTS_DIR:   return jsonify({"ok":False,"error":"scripts не найден"})
    bat_path = os.path.join(SCRIPTS_DIR,bat)
    _log(f"▶ Запуск: {name}","info")
    def _t():
        ok,rc = run_bat(bat_path,_log)
        _log(f"{'✓' if ok else '✗'} {name} — {'выполнено' if ok else f'ошибка (код {rc})'}","ok" if ok else "err")
    threading.Thread(target=_t,daemon=True).start()
    return jsonify({"ok":True})

@app.route("/api/soft_programs")
def api_soft_programs():
    """Программы из multilaunch/soft/ + тяжёлые из multilaunch/heavy/."""
    if not MULTILAUNCH: return jsonify({"ok":False,"programs":[],"folder":None})
    soft_dir   = os.path.join(MULTILAUNCH,"soft")
    programs   = scan_programs(soft_dir)  # portable и heavy теперь не в soft/
    heavy_dir  = os.path.join(MULTILAUNCH,"heavy")
    local_comp = _load_local_comp()
    if os.path.isdir(heavy_dir):
        try:
            for entry in sorted(os.listdir(heavy_dir)):
                entry_path = os.path.join(heavy_dir, entry)
                if not os.path.isdir(entry_path): continue
                exe_path = icon_path = None
                for icon_name in ("icon.png","icon.ico","Icon.png","Icon.ico"):
                    c = os.path.join(entry_path, icon_name)
                    if os.path.isfile(c): icon_path = c; break
                launch_txt = os.path.join(entry_path,"launch.txt")
                if os.path.isfile(launch_txt):
                    try:
                        with open(launch_txt, encoding='utf-8', errors='replace') as lf:
                            exe_name = lf.read().strip()
                        c = os.path.join(entry_path, exe_name)
                        if os.path.isfile(c): exe_path = c
                    except: pass
                if not exe_path:
                    for f in sorted(os.listdir(entry_path)):
                        if os.path.splitext(f)[1].lower() in ('.exe','.msi'):
                            exe_path = os.path.join(entry_path, f); break
                comp_key = f"heavy_{entry}"
                programs.append({
                    "name":      entry,
                    "path":      exe_path,
                    "icon":      icon_path,
                    "installed": exe_path is not None,
                    "comp_key":  comp_key,
                    "local_ver": local_comp.get(comp_key),
                })
        except: pass
    return jsonify({"ok":True,"programs":programs,"title":"Установка программ","folder":soft_dir})


@app.route("/api/diag_programs")
def api_diag_programs():
    if not MULTILAUNCH: return jsonify({"ok":False,"programs":[],"folder":None})
    port_dir = os.path.join(MULTILAUNCH,"portable")
    programs = scan_programs(port_dir)
    return jsonify({"ok":True,"programs":programs,"title":"Диагностика","folder":port_dir})

@app.route("/api/launch_program", methods=["POST"])
def api_launch_program():
    path = request.json.get("path","")
    if not path or not os.path.isfile(path):
        return jsonify({"ok":False,"error":"Файл не найден"})
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".msi":
            subprocess.Popen(["msiexec","/i",path],cwd=os.path.dirname(path))
        else:
            subprocess.Popen([path],cwd=os.path.dirname(path))
        name = os.path.splitext(os.path.basename(path))[0]
        _log(f"▶ Запущена программа: {name}","info")
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)})

@app.route("/api/open_folder", methods=["POST"])
def api_open_folder():
    path = request.json.get("path","")
    if path and os.path.isdir(path):
        try: subprocess.Popen(f'explorer "{path}"'); return jsonify({"ok":True})
        except Exception as e: return jsonify({"ok":False,"error":str(e)})
    return jsonify({"ok":False,"error":"Папка не найдена"})

@app.route("/api/hw_info")
def api_hw_info():
    """Возвращает данные о железе + SMART для hover-тултипа."""
    disks_raw = _hw_info.get("DISKS", "")
    disk_entries = [d.strip() for d in disks_raw.split("~") if d.strip()]
    smart = _hw_smart or {}
    disks_out = []
    for i, d in enumerate(disk_entries):
        # Берём SMART по букве первого раздела (C:, D: и т.д.)
        # Если буквы нет (нет раздела) — пробуем __devN__ ключ
        disk_letter = None
        lm = re.search(r'\[([A-Z]:)', d)
        if lm: disk_letter = lm.group(1)
        s = smart.get(disk_letter) if disk_letter else None
        if s is None:
            # диск без буквы: ищем по int-индексу (внешние, нераздел. диски)
            for k, v in smart.items():
                if isinstance(k, int):
                    used = any(
                        smart.get(l2) is v
                        for l2 in [x for x in smart if isinstance(x, str) and not x.startswith('__')]
                    )
                    if not used:
                        s = v; break
        if s is None and f"__dev{i}__" in smart:
            s = smart.get(f"__dev{i}__")
        disks_out.append({
            "label": f"Диск {i+1}" if i > 0 else "Диск",
            "info": d,
            "health": s["health"] if s else None,
            "pct":    s["pct"]    if s else None,
            "temp":   s["temp"]   if s else None,
            "hours":  s["hours"]  if s else None,
        })
    return jsonify({
        "ok":    True,
        "ready": bool(_hw_info),
        "cpu":   _hw_info.get("CPU",  "—"),
        "mb":    _hw_info.get("MB",   "—"),
        "ram":   _hw_info.get("RAM",  "—"),
        "gpu":   _hw_info.get("GPU",  "—"),
        "bios":  _hw_info.get("BIOS", "—"),
        "disks": disks_out,
        "smart_available": _hw_smart is not None,
    })

@app.route("/api/icon")
def api_icon():
    """Отдаёт файл иконки программы по абсолютному пути."""
    import base64, mimetypes
    path = request.args.get("path", "")
    if not path or not os.path.isfile(path):
        return "", 404
    # Разрешаем только файлы из папки multilaunch
    if MULTILAUNCH and not path.lower().startswith(MULTILAUNCH.lower()):
        return "", 403
    try:
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as f:
            data = f.read()
        from flask import Response as _R
        return _R(data, mimetype=mime, headers={"Cache-Control": "max-age=3600"})
    except:
        return "", 500

# Глобальные флаги для управления скачиванием обновления
_upd_cancel = False
_upd_tmp_dir = None

@app.route("/api/cancel_update", methods=["POST"])
def api_cancel_update():
    """Отменяет скачивание обновления и удаляет временную папку."""
    global _upd_cancel, _upd_tmp_dir
    _upd_cancel = True
    _log("Скачивание отменено пользователем", "warn")
    tmp = _upd_tmp_dir
    if tmp and os.path.isdir(tmp):
        try:
            shutil.rmtree(tmp, ignore_errors=True)
            _log(f"Временные файлы удалены: {tmp}", "info")
        except Exception as ex:
            _log(f"Не удалось удалить tmp: {ex}", "warn")
        _upd_tmp_dir = None
    _push("upd_progress", {"text":"⏹  Скачивание отменено. Файлы удалены.","pct":0,"cancelled":True})
    return jsonify({"ok":True})

@app.route("/api/download_update", methods=["POST"])
def api_download_update():
    """Скачивает и устанавливает компоненты обновления.
    Принимает JSON:
      {
        "components": ["main","soft",...],  ← ключи компонентов
        "remote_comp": [{key,file,remote_ver,size_mb,target,display_name}, ...]
      }
    """
    global _upd_cancel, _upd_tmp_dir
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

    # Защита от одновременного запуска двух загрузок
    if _upd_tmp_dir and os.path.isdir(_upd_tmp_dir):
        return jsonify({"ok": False, "error": "Загрузка уже выполняется"})

    # Корень флешки — родитель папки multilaunch, гарантируем trailing sep
    _ml = MULTILAUNCH.rstrip("\\/")
    drive_root = os.path.dirname(_ml)
    if not drive_root:
        drive_root = os.path.splitdrive(_ml)[0] + os.sep
    if not drive_root.endswith(os.sep):
        drive_root += os.sep

    _upd_cancel  = False
    _upd_tmp_dir = None

    upd_log_path = os.path.join(_APP_DIR, "updatelog.txt")

    def _bg():
        global _upd_cancel, _upd_tmp_dir
        import urllib.request as _ur, time as _t, tempfile, ssl as _ssl

        def _ulog(msg):
            """Пишет строку в updatelog.txt рядом с exe."""
            try:
                ts = datetime.now().strftime("%H:%M:%S")
                with open(upd_log_path, "a", encoding="utf-8") as _f:
                    _f.write(f"[{ts}] {msg}\n")
            except Exception:
                pass

        _ulog("=" * 48)
        _ulog(f"Запуск обновления: {', '.join(keys_to_dl)}")
        UA = "ALFAscript-Updater/1.0"
        _ctx = _ssl.create_default_context()
        _ctx.check_hostname = False
        _ctx.verify_mode = _ssl.CERT_NONE

        def _get_dl_url(pk, path=""):
            url = (f"https://cloud-api.yandex.net/v1/disk/public/resources/download"
                   f"?public_key={urllib.parse.quote(pk, safe='')}"
                   + (f"&path={urllib.parse.quote(path, safe='')}" if path else ""))
            req = _ur.Request(url, headers={"User-Agent": UA})
            with _ur.urlopen(req, timeout=15, context=_ctx) as r:
                return json.loads(r.read())["href"]

        def _dl(url, dest, label, g_start, g_done_mb, g_total_mb):
            req = _ur.Request(url, headers={"User-Agent": UA})
            with _ur.urlopen(req, timeout=60, context=_ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                done  = 0
                with open(dest, "wb") as f:
                    while True:
                        if _upd_cancel: raise Exception("cancelled")
                        chunk = resp.read(65536)
                        if not chunk: break
                        f.write(chunk)
                        done += len(chunk)
                        elapsed = max(_t.time() - g_start, 0.1)
                        spd     = ((g_done_mb * 1048576 + done) / elapsed) / 1048576
                        done_mb = done / 1048576
                        tot_mb  = total / 1048576 if total else 0
                        g_pct   = min(int((g_done_mb + done_mb) / g_total_mb * 95), 95) if g_total_mb > 0 else None
                        text    = (f"{label}: {done_mb:.0f}/{tot_mb:.0f} МБ  •  {spd:.1f} МБ/с"
                                   if tot_mb > 0 else
                                   f"{label}: {done_mb:.0f} МБ  •  {spd:.1f} МБ/с")
                        _push("upd_progress", {"text": text, "pct": g_pct})
            return done / 1048576

        def _extract(arc_path, out_dir):
            sz = _find_7zip()
            if not sz: raise RuntimeError("7-Zip не найден — распаковка невозможна")
            proc = subprocess.Popen(
                [sz, "x", arc_path, f"-o{out_dir}", "-y", "-aoa"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"7z: код {proc.returncode} для {os.path.basename(arc_path)}")

        tmp_dir = None
        try:
            tmp_dir      = tempfile.mkdtemp(prefix="alfaupdate_")
            _upd_tmp_dir = tmp_dir
            total_mb     = sum(c.get("size_mb", 0) for c in to_download)
            done_mb      = 0.0
            g_start      = _t.time()
            local_comp   = _load_local_comp()
            has_root     = False
            root_exe_tmp = None   # путь к новому exe в tmp (если root обновлялся)

            for i, comp in enumerate(to_download):
                key, filename = comp["key"], comp["file"]
                ver   = comp.get("remote_ver", "")
                label = comp.get("display_name", key)

                if _upd_cancel: raise Exception("cancelled")

                # Прогресс скачивания
                g_pct_dl = int(done_mb / total_mb * 95) if total_mb > 0 else None
                _push("upd_progress", {"text": f"[{i+1}/{len(to_download)}] Скачиваю: {label}…",
                                        "pct": g_pct_dl, "component": key, "phase": "download"})
                _log(f"Скачиваю [{i+1}/{len(to_download)}]: {filename}", "info")
                _ulog(f"Скачиваю [{i+1}/{len(to_download)}]: {filename}")

                dl_url   = _get_dl_url(UPDATE_FOLDER_URL, f"/{filename}")
                arc_path = os.path.join(tmp_dir, filename)
                dl_size  = _dl(dl_url, arc_path, label, g_start, done_mb, total_mb)
                done_mb += dl_size

                # Минимум 10 КБ — защита от пустого/битого архива
                if os.path.getsize(arc_path) < 10 * 1024:
                    raise RuntimeError(f"{filename} повреждён или скачался не полностью")
                _log(f"{filename} — скачан ({dl_size:.0f} МБ)", "ok")
                _ulog(f"{filename} — скачан ({dl_size:.0f} МБ)")

                # Прогресс установки
                g_pct_ex = int(done_mb / total_mb * 95) if total_mb > 0 else None
                _push("upd_progress", {"text": f"[{i+1}/{len(to_download)}] Устанавливаю: {label}…",
                                        "pct": g_pct_ex, "component": key, "phase": "extract"})

                if key == "main":
                    # ── Root: извлекаем во временную папку ─────────────────
                    # _ALFAscript.exe заблокирован Windows — нельзя перезаписать напрямую.
                    # Остальные файлы (version.txt, ico, html) сразу копируем на флешку.
                    root_ext = os.path.join(tmp_dir, "root_ext")
                    os.makedirs(root_ext, exist_ok=True)
                    _extract(arc_path, root_ext)

                    # Копируем всё кроме exe прямо сейчас
                    exe_name = "_ALFAscript.exe"
                    for dirpath, _, files in os.walk(root_ext):
                        for fname in files:
                            if fname.lower() == exe_name.lower():
                                root_exe_tmp = os.path.join(dirpath, fname)
                                continue   # exe — отложим до перезапуска
                            src = os.path.join(dirpath, fname)
                            rel = os.path.relpath(src, root_ext)
                            dst = os.path.join(drive_root, rel)
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            try:
                                shutil.copy2(src, dst)
                            except Exception as ce:
                                _log(f"[WARN] не удалось скопировать {rel}: {ce}", "warn")

                    has_root = True
                    _log("main — подготовлен (exe будет заменён после перезапуска)", "ok")
                else:
                    # ── Обычный компонент: распаковываем прямо на флешку ───
                    _extract(arc_path, drive_root)
                    _log(f"{label} — установлен", "ok")

                local_comp[key] = ver
                _save_local_comp(local_comp)

                try: os.remove(arc_path)
                except Exception: pass

            _push("upd_progress", {"text": "✓  Все компоненты установлены.", "pct": 100})
            _log("═══ Обновление завершено успешно ═══", "ok")
            _ulog("═══ Обновление завершено успешно ═══")

            if has_root:
                # Нужно заменить exe и перезапустить
                exe_dst = os.path.join(drive_root, "_ALFAscript.exe")
                _push("upd_progress", {"text": "Перезапуск ALFAscript…",
                                        "pct": 100, "done": True, "restart": True})
                _log("Закрываю ALFAscript для замены exe…", "info")

                bat_path = os.path.join(_APP_DIR, "restart_alfa.bat")
                src_size = os.path.getsize(root_exe_tmp) if root_exe_tmp else 0

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
                    + (f'copy /y "{root_exe_tmp}" "{exe_dst}"\n'
                       + f'if errorlevel 1 (echo [ERR] copy failed >> "{upd_log_path}" & goto :fail)\n'
                       + f'for %%F in ("{exe_dst}") do if %%~zF LSS {src_size} (echo [ERR] size mismatch %%~zF vs {src_size} >> "{upd_log_path}" & goto :fail)\n'
                       + f'echo [OK] copy OK size={src_size} >> "{upd_log_path}"\n'
                       if root_exe_tmp else "")
                    + _blog("BAT STEP 2: cleaning _MEI* from TEMP")
                    + "for /d %%i in (\"%TEMP%\\_MEI*\") do rmdir /s /q \"%%i\" 2>nul\n"
                    # Также чистим system TEMP на случай если предыдущий запуск был elevated
                    + "for /d %%i in (\"C:\\Windows\\Temp\\_MEI*\") do rmdir /s /q \"%%i\" 2>nul\n"
                    + _blog("BAT STEP 3: removing tmp dir")
                    + f'rmdir /s /q "{tmp_dir}" 2>nul\n'
                    + _blog("BAT STEP 4: pause 3s for filesystem flush")
                    + "ping -n 4 127.0.0.1 >nul\n"
                    # explorer.exe всегда запускает в чистом пользовательском контексте —
                    # не наследует elevation от bat, получает правильный %TEMP%, UAC сам запросится
                    + _blog("BAT STEP 5: showing completion notification")
                    + 'mshta "javascript:var s=new ActiveXObject(\'WScript.Shell\');s.Popup(\'Update done! Run _ALFAscript.exe\',0,\'ALFAscript Updater\',64);close();"\n'
                    + _blog("BAT DONE")
                    + f'del /f /q "{bat_path}"\n'
                    + "goto :eof\n"
                    + ":fail\n"
                    + 'mshta "javascript:var s=new ActiveXObject(\'WScript.Shell\');s.Popup(\'Update FAILED! See updatelog.txt\',0,\'ALFAscript Updater\',16);close();"\n'
                    + _blog("BAT FAIL: notified user")
                    + f'del /f /q "{bat_path}"\n'
                )
                with open(bat_path, "w", encoding="cp1251", errors="replace") as bf:
                    bf.write(bat_text)
                subprocess.Popen(["cmd", "/c", bat_path],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
                _upd_tmp_dir = None
                _t.sleep(1.2)
                os._exit(0)
            else:
                # Root не менялся — без перезапуска
                _push("upd_progress", {"text": "✓  Обновление применено. Перезапуск не требуется.",
                                        "pct": 100, "done": True, "restart": False})
                _upd_tmp_dir = None
                try: shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception: pass

        except Exception as e:
            if tmp_dir and os.path.isdir(tmp_dir):
                try: shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception: pass
            _upd_tmp_dir = None
            if str(e) == "cancelled": return
            _log(f"Ошибка обновления: {e}", "err")
            _ulog(f"ОШИБКА: {e}")
            _push("upd_progress", {"text": f"⚠  Ошибка: {e}", "pct": None, "error": True})

    threading.Thread(target=_bg, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/save_log", methods=["POST"])
def api_save_log():
    """Сохраняет лог в log.txt рядом с exe."""
    try:
        lines = request.json.get("lines", [])
        log_path = os.path.join(_APP_DIR, "log.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return jsonify({"ok": True, "path": log_path})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/open_readme")
def api_open_readme():
    """Открывает README_ALFAscript.html в браузере."""
    if not MULTILAUNCH:
        return jsonify({"ok":False,"error":"multilaunch не найден"})
    readme = os.path.join(MULTILAUNCH,"dependencies","README_ALFAscript.html")
    if not os.path.isfile(readme):
        return jsonify({"ok":False,"error":f"Файл не найден: {readme}"})
    try:
        import webbrowser
        webbrowser.open(f"file:///{readme.replace(os.sep,'/')}")
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)})

@app.route("/api/check_update")
def api_check_update():
    def _t():
        result=check_for_update(); _push("update",result)
    threading.Thread(target=_t,daemon=True).start()
    return jsonify({"ok":True})

@app.route("/api/stream")
def api_stream():
    import queue as Q
    q = Q.Queue()
    with _clients_lock:
        _clients.append(q)
        history_snapshot = list(_log_history)
    def generate():
        try:
            # Отправляем текущее состояние
            yield f"data: {json.dumps({'type':'state','data':{'running':_state['running'],'status':_state['status'],'progress':_state['progress']}})}\n\n"
            # Отправляем историю логов чтобы окно лога не было пустым
            if history_snapshot:
                yield f"data: {json.dumps({'type':'log_history','data':history_snapshot}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    msg=q.get(timeout=15)
                    yield f"data: {msg}\n\n"
                except Q.Empty:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            with _clients_lock:
                if q in _clients: _clients.remove(q)
    return Response(stream_with_context(generate()),mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# =============================================================================
#  ПОТОК ВЫПОЛНЕНИЯ ЗАДАЧ
# =============================================================================

def _run_thread(tasks_to_run):
    total=len(tasks_to_run); errors=0
    for i,(name,bat) in enumerate(tasks_to_run):
        if _state["cancel"]: _log("⏹ Выполнение отменено","warn"); break
        pct=int(i/total*100); _state["progress"]=pct
        _push("status",{"running":True,"text":f"{name}...","type":"running","progress":pct,"step":f"{i+1}/{total}"})
        _log(f"▶ [{i+1}/{total}] {name}","info")
        bat_path=os.path.join(SCRIPTS_DIR,bat)
        double=(bat=="11_runsdi.bat")
        ok,rc=run_bat(bat_path,_log,double_run=double)
        if ok: _log(f"✓ {name} — выполнено","ok")
        else:
            errors+=1
            code_str=f"код {rc}" if rc!=-1 else "файл не найден"
            _log(f"✗ {name} — ошибка ({code_str})","err")
        # AIDA после теста
        if bat in ("04_tests.bat","99_testnotimelimit.bat"):
            try:
                af=find_latest_aida_csv(); alf=find_latest_aida_log_csv()
                if af:
                    _log(f"Читаю отчёт AIDA64: {os.path.basename(af)}","info")
                    result=parse_aida_stat_csv(af)
                    if result:
                        if alf: result["throttle"]=detect_cpu_throttle(alf)
                        _state["test_results"]=result
                        _push("test_results",result)
                    else: _log("Не удалось разобрать отчёт AIDA64","warn")
                else: _log("Отчёт AIDA64 не найден","warn")
            except Exception as e: _log(f"Ошибка чтения AIDA64: {e}","warn")
    _state["running"]=False; _state["cancel"]=False; _state["progress"]=100
    if errors:
        _log(f"═══ Завершено с ошибками ({errors}) ═══","warn")
        _push("status",{"running":False,"text":f"Завершено с ошибками ({errors})","type":"warn","progress":100})
    else:
        _log("═══ Все задачи выполнены успешно ═══","ok")
        _push("status",{"running":False,"text":"Все задачи выполнены ✓","type":"done","progress":100})
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK if not errors else winsound.MB_ICONEXCLAMATION)
    except: pass

# =============================================================================
#  PYWEBVIEW JS API
# =============================================================================

class WebAPI:
    """Методы вызываемые из JS через pywebview.api.*"""
    _log_win = None  # ссылка на открытое окно лога

    def open_log(self):
        try:
            import webview, ctypes
            # Если окно уже открыто — закрываем
            if WebAPI._log_win is not None:
                try:
                    WebAPI._log_win.destroy()
                except Exception:
                    pass
                WebAPI._log_win = None
                _push("log_window", {"open": False})
                return
            # Получаем позицию и размер основного окна
            x, y, w, h = 0, 0, 1200, 720
            try:
                wins = webview.windows
                if wins:
                    mw = wins[0]
                    x = getattr(mw, 'x', 0) or 0
                    y = getattr(mw, 'y', 0) or 0
                    w = getattr(mw, 'width', 1200) or 1200
                    h = getattr(mw, 'height', 720) or 720
            except Exception:
                pass
            log_w = 480
            log_h = h
            log_x = x + w  # справа от основного
            win = webview.create_window(
                title="Лог выполнения",
                url="http://127.0.0.1:5757/log",
                width=log_w, height=log_h,
                x=log_x, y=y,
                resizable=True,
                background_color="#00000000",
                transparent=True,
            )
            WebAPI._log_win = win
            # Когда пользователь закрывает окно вручную — сбрасываем флаг
            def _on_closed():
                WebAPI._log_win = None
                _push("log_window", {"open": False})
            try:
                win.events.closed += _on_closed
            except Exception:
                pass
            _push("log_window", {"open": True})
        except Exception as e:
            print(f"[log window] {e}")
            try:
                import webview
                win = webview.create_window(
                    title="Лог выполнения",
                    url="http://127.0.0.1:5757/log",
                    width=480, height=680,
                    resizable=True,
                    background_color="#0f1117",
                )
                WebAPI._log_win = win
                try:
                    def _on_closed():
                        WebAPI._log_win = None
                        _push("log_window", {"open": False})
                    win.events.closed += _on_closed
                except Exception:
                    pass
                _push("log_window", {"open": True})
            except Exception as e2:
                print(f"[log window fallback] {e2}")

# =============================================================================
#  ТОЧКА ВХОДА
# =============================================================================

def start_flask():
    app.run(host="127.0.0.1",port=5757,debug=False,use_reloader=False,threaded=True)

if __name__ == "__main__":
    if not is_admin():
        run_as_admin(); sys.exit()

    threading.Thread(target=_load_hw_info_bg, daemon=True).start()
    threading.Thread(target=_refresh_net_status, daemon=True).start()
    _log(f"ALFAscript {CURRENT_VERSION} инициализирован","ok")
    _log("Права администратора: ОК" if is_admin() else "Нет прав администратора!","ok" if is_admin() else "err")
    if MULTILAUNCH: _log(f"Найдено: {MULTILAUNCH}","ok")
    else: _log("ВНИМАНИЕ: папка multilaunch не найдена!","warn")

    def _auto_defender():
        """Проверяет исключения Defender при старте и добавляет если нужно."""
        try:
            status = _get_defender_exclusion_status()
            if status == "Добавлены":
                _log("Defender: исключения уже добавлены", "ok")
                return
            if status == "Отключён":
                _log("Defender: служба отключена — исключения не требуются", "info")
                return
            _log("Defender: добавляю исключения для флешки и _MEIPASS…", "info")
            ok, msg, disabled = _apply_defender_exclusions()
            if disabled:
                _log("Defender: служба отключена — исключения не требуются", "info")
            elif ok:
                _log(f"Defender: исключения добавлены → {msg}", "ok")
            else:
                _log(f"Defender: не удалось добавить исключения — {msg}", "warn")
        except Exception as e:
            _log(f"Defender: ошибка при старте — {e}", "warn")
    threading.Thread(target=_auto_defender, daemon=True).start()

    flask_thread = threading.Thread(target=start_flask,daemon=True)
    flask_thread.start()
    time.sleep(0.8)

    def _auto_check_update():
        time.sleep(3)  # ждём пока SSE-клиент подключится
        _log("Проверка обновлений...", "info")
        result = check_for_update()
        _push("update", result)
        if result.get("has_update"):
            _log(f"! Доступно обновление multilaunch: {result.get('version','')} — откройте меню ℹ", "warn")
        elif result.get("has_heavy_update"):
            _log("Доступны обновления тяжёлых компонентов — откройте меню ℹ", "warn")
        elif result.get("error"):
            _log(f"Проверка обновлений: {result['error']}", "warn")
        else:
            _log("Обновлений нет", "ok")
    threading.Thread(target=_auto_check_update, daemon=True).start()

    try:
        import webview
        api = WebAPI()
        webview.create_window(
            title=f"ALFAscript {CURRENT_VERSION}",
            url="http://127.0.0.1:5757",
            width=1200, height=720,
            min_size=(900,560),
            resizable=True,
            background_color="#0f1117",
            js_api=api,
        )
        webview.start(debug=False)
    except ImportError:
        import webbrowser
        webbrowser.open("http://127.0.0.1:5757")
        print("pywebview не найден — открываю в браузере.")
        flask_thread.join()