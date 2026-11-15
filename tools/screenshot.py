"""README için ekran görüntüsü üretir (gerçek uygulamayı çalıştırır).

Kullanım:  python tools/screenshot.py
Çıktı:     docs/ekran-ana.png, docs/ekran-detay.png
"""
import json
import os
import sys
import time

from PIL import ImageGrab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SHOT_DIR = os.path.join(ROOT, "docs")
DATA_DIR = os.path.join(ROOT, "build", "shot-data")
SYMBOLS = ["AAPL", "MSFT", "NVDA", "GOOGL"]
POSITIONS = {
    "AAPL": {"qty": 12, "avg": 185.4},
    "MSFT": {"qty": 6, "avg": 405.2},
    "NVDA": {"qty": 8, "avg": 118.7},
}


def main():
    os.makedirs(SHOT_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "config.json"), "w", encoding="utf-8") as f:
        json.dump({
            "symbols": SYMBOLS,
            "theme": "gece",
            "opacity": 1.0,
            "density": "normal",
            "positions": POSITIONS,
            "x": 200,
            "y": 150,
        }, f, indent=2)
    os.environ["SW_DATA_DIR"] = DATA_DIR
    os.environ.pop("SW_SMOKE", None)

    import tkinter as tk
    import stock_widget as sw

    app = sw.StockWidget()

    # Nötr arka plan: widget'ın yuvarlak köşeleri bu zeminin üstünde görünür.
    backdrop = tk.Toplevel(app.root)
    backdrop.overrideredirect(True)
    backdrop.configure(bg="#e6e9ef")
    try:
        sm = __import__("ctypes").windll.user32.GetSystemMetrics
        backdrop.geometry("%dx%d+0+0" % (sm(0), sm(1)))
    except Exception:
        pass
    backdrop.lift()
    backdrop.update_idletasks()
    app.root.lift()

    app.root.geometry("+200+150")
    app.root.update()

    deadline = time.time() + 35
    while time.time() < deadline:
        app.root.update()
        time.sleep(0.05)
        if len(app.last) >= len(SYMBOLS):
            break
    if not app.last:
        print("Veri alınamadı (ağ?). Ekran görüntüsü üretilmedi.")
        app.exit_app()
        return 1

    app.root.update()
    time.sleep(0.5)

    x0 = app.root.winfo_rootx()
    y0 = app.root.winfo_rooty()
    w = app.root.winfo_width()
    h = app.root.winfo_height()
    margin = 28
    main_bbox = (x0 - margin, y0 - margin, x0 + w + margin, y0 + h + margin)
    ImageGrab.grab(bbox=main_bbox).save(os.path.join(SHOT_DIR, "ekran-ana.png"))
    print("yazıldı: docs/ekran-ana.png")

    app.open_detail(SYMBOLS[0])
    for _ in range(40):
        app.root.update()
        time.sleep(0.05)

    panel = app._detail
    if panel is not None:
        px, py = panel.win.winfo_rootx(), panel.win.winfo_rooty()
        pw, ph = panel.win.winfo_width(), panel.win.winfo_height()
        left = min(x0, px) - margin
        top = min(y0, py) - margin
        right = max(x0 + w, px + pw) + margin
        bottom = max(y0 + h, py + ph) + margin
        ImageGrab.grab(bbox=(left, top, right, bottom)).save(
            os.path.join(SHOT_DIR, "ekran-detay.png"))
        print("yazıldı: docs/ekran-detay.png")

    try:
        backdrop.destroy()
    except tk.TclError:
        pass
    app.exit_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
