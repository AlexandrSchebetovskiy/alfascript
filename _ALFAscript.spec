# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('src\\templates', 'templates'), ('src/static', 'static')]
binaries = []
hiddenimports = ['webview', 'webview.platforms.winforms', 'flask', 'flask.templating', 'jinja2', 'jinja2.ext', 'werkzeug', 'werkzeug.serving', 'werkzeug.debug', 'clr', 'pythonnet', 'routes', 'routes.main', 'routes.tasks', 'routes.extras', 'routes.updates', 'routes.hardware', 'routes.system', 'services', 'services.system', 'services.bat_runner', 'services.aida', 'services.hardware', 'services.programs', 'services.updater']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('flask')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='_ALFAscript',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
