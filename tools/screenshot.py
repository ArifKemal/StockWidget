"""README ekran görüntülerini gerçek uygulamadan üretir.

Ağa çıkmaz: `fetch_quote`/`fetch_series` sabit, gerçekçi sahte veriyle
değiştirilir; böylece görseller her çalıştırmada aynı çıkar ve piyasa kapalıyken
de üretilebilir. Tepsi kapatılır, ayarlar `build/shot-data` altında tutulur.

Kullanım:  python tools/screenshot.py
Çıktı:     docs/ekran-ana.png, ekran-detay.png, ekran-ayarlar.png,
           ekran-portfoy.png, ekran-alarm.png
"""
import json
import os
import random
import shutil
import sys
import time

from PIL import ImageGrab

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
ALARMS = {"AAPL": {"above": 240, "below": 200}, "NVDA": {"pct": 3}}


def write_config():
    payload = {
        "symbols": SYMBOLS,
        "theme": "gece",
        "opacity": 1.0,
        "density": "normal",
        "positions": POSITIONS,
        "alarms": ALARMS,
        "sort_mode": "manual",
        "portfolio_show_cost": True,
        "x": 150,
        "y": 140,
    }
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "config.json"), "w",
              encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


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
    now = int(time.time())
    step = 300
    for i, close in enumerate(closes):
        opener = closes[i - 1] if i else prev
        high = max(opener, close) * 1.0016
        low = min(opener, close) * 0.9984
        ohlc.append((opener, high, low, close))
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
    price = PRICES[symbol]
    step = {"1H": 1800, "1A": 86400, "1Y": 86400}[tf]
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


class Shooter:
    """Arka planı pencere bbox'ına kurup ekran görüntüsü alır."""

    def __init__(self, app, tk):
        self.app = app
        self.tk = tk
        self.backdrop = None

    def _drop_backdrop(self):
        if self.backdrop is not None:
            try:
                self.backdrop.destroy()
            except self.tk.TclError:
                pass
            self.backdrop = None

    def grab(self, boxes, name, top=None):
        """boxes: [(x, y, w, h), ...]; birleşim kırpılır."""
        x1 = min(b[0] for b in boxes) - MARGIN
        y1 = min(b[1] for b in boxes) - MARGIN
        x2 = max(b[0] + b[2] for b in boxes) + MARGIN
        y2 = max(b[1] + b[3] for b in boxes) + MARGIN
        self._drop_backdrop()
        self.backdrop = self.tk.Toplevel(self.app.root)
        self.backdrop.overrideredirect(True)
        self.backdrop.configure(bg=BACKDROP)
        self.backdrop.attributes("-topmost", True)
        self.backdrop.geometry("%dx%d+%d+%d" % (x2 - x1, y2 - y1, x1, y1))
        self.backdrop.lift()
        try:
            self.app.root.lift()
        except self.tk.TclError:
            pass
        if top is not None:
            try:
                top.lift()
            except self.tk.TclError:
                pass
        self.app.root.update_idletasks()
        self.app.root.update()
        time.sleep(0.25)
        path = os.path.join(SHOT_DIR, name)
        ImageGrab.grab(bbox=(x1, y1, x2, y2)).save(path)
        print("yazıldı: docs/%s" % name)
        self._drop_backdrop()
        return path


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def expand_scrollable(dlg, tk):
    """Kısa pencerede kayan içeriği tam boy göster; kaydırma çubuğunu gizle."""
    for widget in _walk(dlg):
        if isinstance(widget, tk.Canvas):
            bbox = widget.bbox("all")
            if bbox and bbox[3] > widget.winfo_height():
                widget.configure(height=bbox[3] - bbox[1] + 4)
    dlg.update_idletasks()
    for widget in _walk(dlg):
        if isinstance(widget, tk.Scrollbar):
            try:
                widget.pack_forget()
                widget.grid_forget()
            except tk.TclError:
                pass
    width = max(dlg.winfo_width(), dlg.winfo_reqwidth())
    height = max(dlg.winfo_height(), dlg.winfo_reqheight())
    dlg.geometry("%dx%d" % (width, height))
    dlg.update_idletasks()


def new_app(sw, scale):
    os.environ["SW_SCALE"] = "%.2f" % scale
    app = sw.StockWidget()
    app.check_updates = lambda silent=False: None
    app.root.update_idletasks()
    app.root.update()
    data = {sym: make_quote(sym) for sym in SYMBOLS}
    app.apply_data(data, False)
    app.root.update_idletasks()
    app.root.update()
    return app


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

    # --- 1) kart + detay paneli (2x) ---
    app = new_app(sw, 2.0)
    shoot = Shooter(app, tk)
    app.root.geometry("+150+140")
    app.root.update()

    box = (app.root.winfo_rootx(), app.root.winfo_rooty(),
           app.root.winfo_width(), app.root.winfo_height())
    shoot.grab([box], "ekran-ana.png")

    app.open_detail("AAPL")
    for _ in range(30):
        app.root.update()
        time.sleep(0.03)
    panel = app._detail
    if panel is not None:
        pbox = (panel.win.winfo_rootx(), panel.win.winfo_rooty(),
                panel.win.winfo_width(), panel.win.winfo_height())
        shoot.grab([box, pbox], "ekran-detay.png", top=panel.win)
    stop(app)

    # --- 1b) açık tema kartı ---
    app = new_app(sw, 2.0)
    shoot = Shooter(app, tk)
    app.set_theme("acik")
    app.root.geometry("+150+140")
    app.root.update()
    box = (app.root.winfo_rootx(), app.root.winfo_rooty(),
           app.root.winfo_width(), app.root.winfo_height())
    shoot.grab([box], "ekran-acik.png")
    app.set_theme("gece")        # sonraki aşama koyu temayla devam etsin
    stop(app)

    # --- 2) pencereler (1.5x) ---
    app = new_app(sw, 1.5)
    shoot = Shooter(app, tk)
    app.root.geometry("+150+140")
    app.root.update()
    app.root.withdraw()          # kart, iletişim kutularının üstüne binmesin

    for opener, anchor, name in (
            ("open_settings_editor", (110, 40), "ekran-ayarlar.png"),
            ("open_portfolio_editor", (110, 40), "ekran-portfoy.png")):
        dlg = getattr(app, opener)()
        dlg.update_idletasks()
        expand_scrollable(dlg, tk)
        dlg.geometry("+%d+%d" % anchor)
        dlg.update_idletasks()
        dlg.update()
        dbox = (dlg.winfo_rootx(), dlg.winfo_rooty(),
                dlg.winfo_width(), dlg.winfo_height())
        shoot.grab([dbox], name, top=dlg)
        dlg.destroy()
        app.root.update()

    stop(app)
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    print("tamam")
    return 0


if __name__ == "__main__":
    sys.exit(main())
