"""README ekran görüntülerini gerçek uygulamadan üretir.

Ağa çıkmaz: `fetch_quote`/`fetch_series` sabit, gerçekçi sahte veriyle
değiştirilir; böylece görseller her çalıştırmada aynı çıkar ve piyasa kapalıyken
de üretilebilir. Tepsi kapatılır, ayarlar `build/shot-data` altında tutulur.

Kullanım:  python tools/screenshot.py
Çıktı:     docs/ekran-ana.png, docs/ekran-detay.png
"""
import json
import os
import random
import shutil
import sys
import time

from PIL import ImageGrab, ImageStat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SHOT_DIR = os.path.join(ROOT, "docs")
DATA_DIR = os.path.join(ROOT, "build", "shot-data")
BACKDROP = "#e4e8ee"
MARGIN = 26

SYMBOLS = ["AAPL", "MSFT", "NVDA", "GOOGL"]
PRICES = {"AAPL": 228.52, "MSFT": 512.30, "NVDA": 178.44, "GOOGL": 201.15}
CHANGES = {"AAPL": 1.24, "MSFT": -0.38, "NVDA": 2.61, "GOOGL": 0.72}
NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "GOOGL": "Alphabet Inc.",
}
EXT = {"AAPL": ("post", 0.42), "NVDA": ("post", 0.68)}
POSITIONS = {
    "AAPL": {"qty": 12, "avg": 185.4, "target": 250, "note": "uzun vade"},
    "MSFT": {"qty": 6, "avg": 405.2},
    "NVDA": {"qty": 8, "avg": 118.7, "target": 200},
}


def write_config():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "config.json"), "w",
              encoding="utf-8") as f:
        json.dump({
            "symbols": SYMBOLS,
            "theme": "gece",
            "opacity": 1.0,
            "density": "normal",
            "positions": POSITIONS,
            "portfolio_show_cost": True,
            "x": 150,
            "y": 140,
        }, f, indent=2)


def walk(seed, end, n=78, amp=0.012):
    """Sabit tohumla, sonu `end` olan gerçekçi bir gün içi eğri."""
    rnd = random.Random(seed)
    values, value = [], end * (1.0 - amp * 2)
    for _ in range(n):
        value *= 1.0 + rnd.uniform(-amp, amp) * 0.55
        values.append(value)
    scale = end / values[-1] if values[-1] else 1.0
    return [v * scale for v in values]


def make_quote(symbol, include_prepost=True):
    price = PRICES[symbol]
    pct = CHANGES[symbol]
    prev = price / (1.0 + pct / 100.0)
    closes = walk(symbol, price)
    ohlc, volumes, times = [], [], []
    now, step = int(time.time()), 300
    for i, close in enumerate(closes):
        opener = closes[i - 1] if i else prev
        ohlc.append((opener, max(opener, close) * 1.0016,
                     min(opener, close) * 0.9984, close))
        volumes.append(int(600_000 + abs(close - opener) * 2_500_000
                           + (i % 7) * 90_000))
        times.append(now - (len(closes) - i) * step)
    quote = {
        "symbol": symbol,
        "name": NAMES[symbol],
        "currency": "USD",
        "exchange": "NasdaqGS",
        "market_state": "REGULAR",
        "timezone": "America/New_York",
        "quote_ts": now - 90,
        "price": price,
        "prev_close": prev,
        "change_pct": pct,
        "change_abs": price - prev,
        "ext_session": None,
        "ext_price": None,
        "ext_change_pct": None,
        "ext_change_abs": None,
        "open": round(closes[0], 2),
        "day_high": round(max(closes), 2),
        "day_low": round(min(closes), 2),
        "high_52w": round(price * 1.28, 2),
        "low_52w": round(price * 0.61, 2),
        "volume": 48_312_400,
        "spark": closes,
        "spark_times": times,
        "spark_volumes": volumes,
        "spark_ohlc": ohlc,
    }
    if include_prepost and symbol in EXT:
        session, extra = EXT[symbol]
        quote["ext_session"] = session
        quote["ext_price"] = round(price * (1.0 + extra / 100.0), 2)
        quote["ext_change_pct"] = round(pct + extra, 2)
        quote["ext_change_abs"] = round(quote["ext_price"] - prev, 2)
    return quote


def make_series(symbol, tf):
    """1H / 1A / 1Y sekmeleri için sabit sahte seri."""
    count = {"1H": 110, "1A": 62, "1Y": 150}[tf]
    step = {"1H": 1800, "1A": 86400, "1Y": 86400}[tf]
    price = PRICES[symbol]
    now = int(time.time())
    closes = walk("%s-%s" % (symbol, tf), price, count, amp=0.02)
    ohlc, volumes, times = [], [], []
    for i, close in enumerate(closes):
        opener = closes[i - 1] if i else close
        ohlc.append((opener, max(opener, close) * 1.004,
                     min(opener, close) * 0.996, close))
        volumes.append(int(2_000_000 + (i % 5) * 400_000))
        times.append(now - (count - i) * step)
    return {"closes": closes, "times": times,
            "volumes": volumes, "ohlc": ohlc}


def grab(app, tk, boxes, name, top=None):
    """boxes: [(x, y, w, h), ...]; birleşimi arka planla birlikte kırpar."""
    x1 = min(b[0] for b in boxes) - MARGIN
    y1 = min(b[1] for b in boxes) - MARGIN
    x2 = max(b[0] + b[2] for b in boxes) + MARGIN
    y2 = max(b[1] + b[3] for b in boxes) + MARGIN
    backdrop = tk.Toplevel(app.root)
    backdrop.overrideredirect(True)
    backdrop.configure(bg=BACKDROP)
    backdrop.geometry("%dx%d+%d+%d" % (x2 - x1, y2 - y1, x1, y1))
    # Arka plan topmost OLMAMALI: aksi halde widget'ı örtüp boş görüntü
    # yakalanmasına yol açıyor (topmost pencereler arasında z-sırası garanti
    # değil). Widget zaten topmost; arka planı onun altına indir.
    backdrop.attributes("-topmost", False)
    backdrop.lower(app.root)
    for window in (app.root, top):
        if window is not None:
            try:
                window.lift()
            except tk.TclError:
                pass
    app.root.update_idletasks()
    app.root.update()
    time.sleep(0.3)
    image = ImageGrab.grab(bbox=(x1, y1, x2, y2)).convert("RGB")
    # Boş/tek renk yakalama, iyi README görsellerini ezmesin.
    if max(ImageStat.Stat(image).stddev) < 3.0:
        print("uyarı: %s boş yakalandı; dosya korundu" % name)
        try:
            backdrop.destroy()
        except tk.TclError:
            pass
        return False
    image.save(os.path.join(SHOT_DIR, name))
    print("yazıldı: docs/%s" % name)
    try:
        backdrop.destroy()
    except tk.TclError:
        pass
    return True


def stop(app):
    try:
        app.stop_flag.set()
        app.wake.set()
        app.root.quit()
        app.root.destroy()
    except Exception:
        pass


def main():
    os.environ["SW_DISABLE_TRAY"] = "1"
    os.environ["SW_SCALE"] = "2.0"
    os.environ.pop("SW_SMOKE", None)
    os.makedirs(SHOT_DIR, exist_ok=True)
    write_config()
    os.environ["SW_DATA_DIR"] = DATA_DIR

    import tkinter as tk
    import stock_widget as sw

    sw.fetch_quote = make_quote
    sw.fetch_series = make_series
    # Gerçek kısayol kaydı, çalışan kopyayla çakışıp "kaydedilemedi" gösterirdi.
    sw.hotkey_loop = lambda events, stop_flag: events.put("registered")

    app = sw.StockWidget()
    app.check_updates = lambda silent=False: None
    app.root.update_idletasks()
    app.root.update()
    app.apply_data({sym: make_quote(sym) for sym in SYMBOLS}, False)
    app.root.geometry("+150+140")
    app.root.update()

    box = (app.root.winfo_rootx(), app.root.winfo_rooty(),
           app.root.winfo_width(), app.root.winfo_height())
    ok = grab(app, tk, [box], "ekran-ana.png")

    app.open_detail("AAPL")
    for _ in range(30):
        app.root.update()
        time.sleep(0.03)
    panel = app._detail
    if panel is not None:
        pbox = (panel.win.winfo_rootx(), panel.win.winfo_rooty(),
                panel.win.winfo_width(), panel.win.winfo_height())
        ok = grab(app, tk, [box, pbox], "ekran-detay.png",
                  top=panel.win) and ok

    stop(app)
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    if not ok:
        print("görüntü yakalanamadı; mevcut dosyalar korundu")
        return 1
    print("tamam")
    return 0


if __name__ == "__main__":
    sys.exit(main())
