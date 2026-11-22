# -*- mode: python ; coding: utf-8 -*-
# PyInstaller derleme tanımı: TEK DOSYA (onefile) çıktısı.
# Ana indirme budur: StockWidget.exe — indir, çift tıkla, kurulum yok.
# Kullanım (kök dizinden):
#   python -m PyInstaller --noconfirm --clean --distpath dist-onefile packaging/StockWidget-onefile.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
block_cipher = None

datas = [(os.path.join(ROOT, "assets", "stock.ico"), "assets")]
for extra in ("LICENSE", "README.md"):
    path = os.path.join(ROOT, extra)
    if os.path.exists(path):
        datas.append((path, "."))

a = Analysis(
    [os.path.join(ROOT, "stock_widget.py")],
    pathex=[ROOT],
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
    icon=os.path.join(ROOT, "assets", "stock.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
)
