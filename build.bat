@echo off
chcp 65001 >nul
title ALFAscript — сборка EXE

:: ── Переходим в папку где лежит этот bat ─────────────────────────────────
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║     ALFAscript — сборка в .exe           ║
echo  ╚══════════════════════════════════════════╝
echo.
echo  Папка сборки: %CD%
echo.

:: ── Проверяем Python ──────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ОШИБКА] Python не найден!
    echo  Установи Python 3.11+ с python.org ^(галочка "Add to PATH"^)
    pause & exit /b 1
)

:: ── Проверяем точку входа ─────────────────────────────────────────────────
if not exist main.py (
    echo  [ОШИБКА] main.py не найден!
    echo  Убедись что build.bat лежит рядом с main.py и папкой src\
    pause & exit /b 1
)

:: ── Проверяем структуру src\ ──────────────────────────────────────────────
if not exist src (
    echo  [ОШИБКА] Папка src\ не найдена!
    pause & exit /b 1
)

for %%F in (app.py config.py paths.py state.py theme.py webapi.py) do (
    if not exist src\%%F (
        echo  [ОШИБКА] src\%%F не найден!
        pause & exit /b 1
    )
)
for %%F in (routes\__init__.py routes\main.py routes\tasks.py routes\extras.py routes\updates.py routes\hardware.py routes\system.py) do (
    if not exist src\%%F (
        echo  [ОШИБКА] src\%%F не найден!
        pause & exit /b 1
    )
)
for %%F in (services\__init__.py services\system.py services\bat_runner.py services\aida.py services\hardware.py services\programs.py services\updater.py) do (
    if not exist src\%%F (
        echo  [ОШИБКА] src\%%F не найден!
        pause & exit /b 1
    )
)

if not exist src\static\css\base.css (
    echo  [ОШИБКА] static\css\base.css не найден!
    echo  Папка static\ должна лежать рядом с main.py
    pause ^& exit /b 1
)
:: ── Если index.html лежит рядом — кладём в src\templates\ автоматически ──
if exist index.html (
    if not exist src\templates mkdir src\templates
    echo  [ИНФО] Перемещаем index.html в src\templates\...
    move /y index.html src\templates\index.html >nul
)
if exist log.html (
    if not exist src\templates mkdir src\templates
    echo  [ИНФО] Перемещаем log.html в src\templates\...
    move /y log.html src\templates\log.html >nul
)

if not exist src\templates\index.html (
    echo  [ОШИБКА] src\templates\index.html не найден!
    echo  Положи index.html в папку src\templates\
    pause & exit /b 1
)

:: ── Устанавливаем зависимости ─────────────────────────────────────────────
echo  [1/3] Устанавливаем зависимости...
pip install flask pywebview pyinstaller --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [ОШИБКА] Не удалось установить пакеты!
    pause & exit /b 1
)
echo        OK
echo.

:: ── Чистим старую сборку ──────────────────────────────────────────────────
echo  [2/3] Очищаем предыдущую сборку...
if exist dist\_ALFAscript.exe del /f /q dist\_ALFAscript.exe >nul 2>&1
if exist build rmdir /s /q build >nul 2>&1
if exist _ALFAscript.spec del /f /q _ALFAscript.spec >nul 2>&1
echo        OK
echo.

:: ── Собираем EXE ──────────────────────────────────────────────────────────
echo  [3/3] Собираем EXE (это займёт 1-2 минуты)...
echo.

set ICON_ARG=
if exist src\icon.ico set ICON_ARG=--icon=src\icon.ico
if exist icon.ico     set ICON_ARG=--icon=icon.ico

pyinstaller ^
  --onefile ^
  --windowed ^
  --name _ALFAscript ^
  %ICON_ARG% ^
  --add-data "src\templates;templates" ^
  --add-data "src/static;static" ^
  --paths "src" ^
  --hidden-import webview ^
  --hidden-import webview.platforms.winforms ^
  --hidden-import flask ^
  --hidden-import flask.templating ^
  --hidden-import jinja2 ^
  --hidden-import jinja2.ext ^
  --hidden-import werkzeug ^
  --hidden-import werkzeug.serving ^
  --hidden-import werkzeug.debug ^
  --hidden-import clr ^
  --hidden-import pythonnet ^
  --hidden-import routes ^
  --hidden-import routes.main ^
  --hidden-import routes.tasks ^
  --hidden-import routes.extras ^
  --hidden-import routes.updates ^
  --hidden-import routes.hardware ^
  --hidden-import routes.system ^
  --hidden-import services ^
  --hidden-import services.system ^
  --hidden-import services.bat_runner ^
  --hidden-import services.aida ^
  --hidden-import services.hardware ^
  --hidden-import services.programs ^
  --hidden-import services.updater ^
  --collect-all webview ^
  --collect-all flask ^
  main.py

if errorlevel 1 (
    echo.
    echo  [ОШИБКА] Сборка завершилась с ошибкой!
    echo  Проверь вывод выше.
    pause & exit /b 1
)

:: ── Готово ────────────────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║  Готово!  dist\_ALFAscript.exe            ║
echo  ╚══════════════════════════════════════════╝
echo.
echo  Скопируй dist\_ALFAscript.exe рядом с папкой multilaunch.
echo.

:: ── Запускаем собранный EXE ───────────────────────────────────────────────
echo  Запускаем dist\_ALFAscript.exe...
start "" "dist\_ALFAscript.exe"

choice /t 7 /d y /n /m "Окно закроется через 7 сек... (нажми любую клавишу чтобы остаться)"
if errorlevel 2 pause