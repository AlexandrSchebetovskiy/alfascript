@echo off
chcp 65001 >nul
title ALFAscript — сборка EXE

:: ── Переходим в папку где лежит этот bat (ВАЖНО) ─────────────────────────
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

:: ── Проверяем наличие app.py ──────────────────────────────────────────────
if not exist app.py (
    echo  [ОШИБКА] app.py не найден в текущей папке!
    echo  Убедись что build.bat лежит рядом с app.py
    pause & exit /b 1
)

:: ── Если index.html лежит рядом — кладём в templates\ автоматически ──────
if exist index.html (
    if not exist templates mkdir templates
    echo  [ИНФО] Перемещаем index.html в templates\...
    move /y index.html templates\index.html >nul
)

if not exist templates\index.html (
    echo  [ОШИБКА] templates\index.html не найден!
    echo  Положи index.html в папку templates\ рядом с build.bat
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
if exist alfascript.spec del /f /q alfascript.spec >nul 2>&1
echo        OK
echo.

:: ── Собираем EXE ──────────────────────────────────────────────────────────
echo  [3/3] Собираем EXE (это займёт 1-2 минуты)...
echo.

:: Иконка — если icon.ico есть рядом, используем её
set ICON_ARG=
if exist icon.ico set ICON_ARG=--icon=icon.ico

pyinstaller ^
  --onefile ^
  --windowed ^
  --name _ALFAscript ^
  %ICON_ARG% ^
  --add-data "templates;templates" ^
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
  --collect-all webview ^
  --collect-all flask ^
  app.py

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
