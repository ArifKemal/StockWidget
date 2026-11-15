# -*- mode: python ; coding: utf-8 -*-
# PyInstaller derleme tanımı: tek klasör (onedir) çıktısı.
# Kullanım: python -m PyInstaller --noconfirm --clean StockWidget.spec
import os

block_cipher = None

datas = [("stock.ico", ".")]
for extra in ("LICENSE", "README.md"):
    if os.path.exists(extra):
        datas.append((extra, "."))

a = Analysis(
    ["stock_widget.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["pystray._win32", "PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "numpy", "matplotlib", "pandas"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StockWidget",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="stock.ico",
    version="version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="StockWidget",
)
