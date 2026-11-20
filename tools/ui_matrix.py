"""Tema x yoğunluk x DPI matrisi için hızlı GUI duman testi.

Gerçek bir monitör DPI'si değiştirmeden `SW_SCALE` ile ölçek denenir; tray
kapatılır ve ağa çıkılmaz. Amaç: her kombinasyonda Tk'nin istisna atmaması
ve kartın makul boyutta çizilmesi.

Kullanım: python tools/ui_matrix.py
"""
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SW_DISABLE_TRAY"] = "1"

DATA = tempfile.mkdtemp(prefix="sw-ui-matrix-")
os.environ["SW_DATA_DIR"] = DATA
with open(os.path.join(DATA, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"symbols": ["AAPL", "MSFT", "NVDA"], "x": 100, "y": 100,
               "positions": {"AAPL": {"qty": 2, "avg": 100, "target": 200}},
               "alarms": {"AAPL": {"above": 999}}}, f)

import stock_widget as sw  # noqa: E402  (env/SW_DATA_DIR once ayarlanmalı)


def quote(symbol, include_prepost=True):
    price = {"AAPL": 150.0, "MSFT": 300.0, "NVDA": 120.0}[symbol]
    prev = price * 0.98
    return {
        "symbol": symbol, "name": symbol + " Inc", "currency": "USD",
        "exchange": "Nasdaq", "market_state": "REGULAR",
        "timezone": "America/New_York", "quote_ts": time.time(),
        "price": price, "prev_close": prev,
        "change_pct": (price / prev - 1) * 100, "change_abs": price - prev,
        "ext_session": None, "ext_price": None, "ext_change_pct": None,
        "ext_change_abs": None, "open": prev, "day_high": price,
        "day_low": prev, "high_52w": price, "low_52w": prev,
        "volume": 100000,
        "spark": [prev, (prev + price) / 2, price],
        "spark_times": [0, 60, 120], "spark_volumes": [1, 1, 1],
        "spark_ohlc": [(prev, price, prev, price)] * 3,
    }


sw.fetch_quote = quote
print("scale  tema    yogunluk  boyut")


def run_scale(scale):
    os.environ["SW_SCALE"] = str(scale)
    app = sw.StockWidget()
    try:
        for theme in sw.THEME_ORDER:
            app.set_theme(theme)
            for density in ("normal", "compact"):
                app.set_density(density)
                app.root.update_idletasks()
                app.root.update()
                w = app.root.winfo_width()
                h = app.root.winfo_height()
                assert w >= int(260 * scale), (scale, theme, density, w)
                assert h >= int(120 * scale), (scale, theme, density, h)
                bbox = app.canvas.bbox("all")
                assert bbox and bbox[2] > 0 and bbox[3] > 0, bbox
                print("%-6s %-7s %-8s %dx%d" % (scale, theme, density, w, h))
        # Alarm/portföy pencereleri de bu ölçekte açılabilmeli
        dlg = app.open_alarm_editor()
        dlg.update_idletasks()
        assert dlg.winfo_width() > 100
        dlg.destroy()
        dlg = app.open_portfolio_editor()
        dlg.update_idletasks()
        assert dlg.winfo_width() > 100
        dlg.destroy()
        dlg = app.open_settings_editor()
        dlg.update_idletasks()
        assert dlg.winfo_width() > 100
        # Alt bardaki Semboller/Portföy/Alarmlar/Kapat sığmalı
        assert dlg.winfo_reqwidth() <= dlg.winfo_width() + 1, (
            dlg.winfo_reqwidth(), dlg.winfo_width())
        dlg.destroy()
    finally:
        app.exit_app()


try:
    for value in (0.75, 1.0, 1.25, 1.5, 2.0):
        run_scale(value)
finally:
    shutil.rmtree(DATA, ignore_errors=True)
print("UI MATRIX OK")
