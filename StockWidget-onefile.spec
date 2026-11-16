# -*- mode: python ; coding: utf-8 -*-
# PyInstaller derleme tanımı: TEK DOSYA (onefile) çıktısı.
# Ana indirme budur: StockWidget.exe — indir, çift tıkla, kurulum yok.
# Kullanım: python -m PyInstaller --noconfirm --clean --distpath dist-onefile StockWidget-onefile.spec
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

# onefile: binaries/datas EXE içine gömülür, ayrı COLLECT yok.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="StockWidget",
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
    icon="stock.ico",
    version="version_info.txt",
)
