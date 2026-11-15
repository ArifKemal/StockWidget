import os
import sys
import json
import time
import queue
import ctypes
import ctypes.wintypes
import datetime
import logging
import shutil
import threading
import traceback
import tkinter as tk
import tkinter.font as tkfont
from logging.handlers import RotatingFileHandler

import requests

try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageTk, ImageChops
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

APP_NAME = "StockWidget"
APP_VERSION = "1.0.0"
FROZEN = bool(getattr(sys, "frozen", False))

# PyInstaller: kod _MEIPASS'e açılır, kalıcı veri oraya yazılamaz.
ASSET_DIR = (getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
             if FROZEN else os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = ASSET_DIR
ICON_FILE = os.path.join(ASSET_DIR, "stock.ico")


def _data_dir():
    """Kalıcı ayar/log dizini: %APPDATA%\\StockWidget (yazılamazsa yanına düş)."""
    override = os.environ.get("SW_DATA_DIR")
    base = override or os.path.join(
        os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        base = ASSET_DIR
    return base


DATA_DIR = _data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LOG_FILE = os.path.join(DATA_DIR, "sw.log")
# Eski sürümler config'i script/exe yanına yazıyordu; ilk açılışta taşınır.
LEGACY_CONFIG = os.path.join(
    os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else BASE_DIR,
    "config.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "StockWidget"

# İkinci kopya --toggle/--quit ile bu isimli olayları işaretler; ana pencere dinler.
TOGGLE_EVENT = "Local\\StockWidgetToggleEvent"
QUIT_EVENT = "Local\\StockWidgetQuitEvent"
EVENT_MODIFY_STATE = 0x0002

log = logging.getLogger("stockwidget")


def setup_logging():
    """pythonw.exe'de görünmeyen hataları sw.log'a yazar."""
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(LOG_FILE, maxBytes=200_000,
                                      backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
    except OSError:
        pass

def migrate_legacy_config():
    """Eski sürümün yanındaki config.json'ı kalıcı dizine taşır (bir kez)."""
    if os.path.exists(CONFIG_FILE) or not os.path.exists(LEGACY_CONFIG):
        return
    try:
        shutil.copy2(LEGACY_CONFIG, CONFIG_FILE)
    except OSError:
        pass


API_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           "{s}?interval=5m&range=1d")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

HOTKEY_ID = 1
HOTKEY_MODS = 0x0001 | 0x0002   # ALT | CONTROL
HOTKEY_NOREPEAT = 0x4000
HOTKEY_VK = 0x53                # S
WM_HOTKEY = 0x0312

INTERVAL_OPEN = 15 * 60
INTERVAL_CLOSED = 60 * 60
INTERVAL_RETRY = 90
THROTTLE_429 = 300

KEY = "#010203"          # transparentcolor key (rounded corners)

PALETTES = {
    "gece": {
        "card": "#14161b", "fg": "#f2f3f5", "muted": "#8b909b",
        "dim": "#5f6570", "divider": "#22262e", "hover": "#1a1d24",
        "green": "#3ddc84", "green_dim": "#12301f",
        "red": "#ff5a5f", "red_dim": "#33181c",
        "amber": "#e8b13f", "accent": "#4c8dff",
        "raised": "#1e222a", "track": "#252a34", "menu_bg": "#1b1e25",
        "menu_active": "#2b3038", "btn": "#242833",
        "btn_hover": "#2e333f", "accent_hover": "#3b7bff",
        "entry_border": "#2c313a",
    },
    "slate": {
        "card": "#11151c", "fg": "#e6edf3", "muted": "#8b98a9",
        "dim": "#5b6676", "divider": "#1e2733", "hover": "#17202b",
        "green": "#34d399", "green_dim": "#0d2b22",
        "red": "#f87171", "red_dim": "#331a1a",
        "amber": "#fbbf24", "accent": "#60a5fa",
        "raised": "#18202a", "track": "#22303f", "menu_bg": "#151c25",
        "menu_active": "#22303f", "btn": "#1d2a36",
        "btn_hover": "#263646", "accent_hover": "#4b93f0",
        "entry_border": "#263646",
    },
    "grafit": {
        "card": "#1a1a1c", "fg": "#ececec", "muted": "#9a9a9e",
        "dim": "#6a6a6e", "divider": "#2a2a2e", "hover": "#222226",
        "green": "#4ade80", "green_dim": "#14301f",
        "red": "#ef4444", "red_dim": "#331616",
        "amber": "#eab308", "accent": "#818cf8",
        "raised": "#242428", "track": "#2e2e33", "menu_bg": "#1f1f22",
        "menu_active": "#2e2e33", "btn": "#28282c",
        "btn_hover": "#323238", "accent_hover": "#6f7ae8",
        "entry_border": "#333338",
    },
    "acik": {
        "card": "#f4f5f8", "fg": "#171a20", "muted": "#5b6472",
        "dim": "#98a0ad", "divider": "#e2e5ea", "hover": "#e9ecf1",
        "green": "#0f9d58", "green_dim": "#d7f2e3",
        "red": "#d93025", "red_dim": "#fbe3e1",
        "amber": "#a86400", "accent": "#1a73e8",
        "raised": "#eef1f5", "track": "#dfe3ea", "menu_bg": "#ffffff",
        "menu_active": "#e8eefc", "btn": "#e9ecf1",
        "btn_hover": "#dde3ec", "accent_hover": "#1565d8",
        "entry_border": "#c9ced8",
    },
}
THEME_LABEL = {"gece": "Gece", "slate": "Slate",
               "grafit": "Grafit", "acik": "Açık"}
THEME_ORDER = ("gece", "slate", "grafit", "acik")

CARD = FG = MUTED = DIM = DIVIDER = HOVER = ""
GREEN = GREEN_DIM = RED = RED_DIM = AMBER = ACCENT = ""
RAISED = TRACK = MENU_BG = MENU_ACTIVE = BTN = BTN_HOVER = ""
ACCENT_HOVER = ENTRY_BORDER = ""


def apply_palette(name):
    p = PALETTES.get(name) or PALETTES["gece"]
    g = globals()
    g["CARD"] = p["card"]
    g["FG"] = p["fg"]
    g["MUTED"] = p["muted"]
    g["DIM"] = p["dim"]
    g["DIVIDER"] = p["divider"]
    g["HOVER"] = p["hover"]
    g["GREEN"] = p["green"]
    g["GREEN_DIM"] = p["green_dim"]
    g["RED"] = p["red"]
    g["RED_DIM"] = p["red_dim"]
    g["AMBER"] = p["amber"]
    g["ACCENT"] = p["accent"]
    g["RAISED"] = p["raised"]
    g["TRACK"] = p["track"]
    g["MENU_BG"] = p["menu_bg"]
    g["MENU_ACTIVE"] = p["menu_active"]
    g["BTN"] = p["btn"]
    g["BTN_HOVER"] = p["btn_hover"]
    g["ACCENT_HOVER"] = p["accent_hover"]
    g["ENTRY_BORDER"] = p["entry_border"]


apply_palette("gece")


def _init_dpi():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def et_now():
    utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    year = utc.year
    mar1 = datetime.datetime(year, 3, 1)
    first_sun_mar = 1 + (6 - mar1.weekday()) % 7
    dst_start = datetime.datetime(year, 3, first_sun_mar + 7, 7, 0)
    nov1 = datetime.datetime(year, 11, 1)
    first_sun_nov = 1 + (6 - nov1.weekday()) % 7
    dst_end = datetime.datetime(year, 11, first_sun_nov, 6, 0)
    offset = -4 if dst_start <= utc < dst_end else -5
    return utc + datetime.timedelta(hours=offset)


def _nth_weekday(year, month, weekday, n):
    """year/month ayındaki n. `weekday` (Pzt=0) gününü döndürür."""
    first = datetime.date(year, month, 1)
    return first + datetime.timedelta(
        days=(weekday - first.weekday()) % 7 + (n - 1) * 7)


def _last_weekday(year, month, weekday):
    """year/month ayındaki son `weekday` gününü döndürür."""
    if month == 12:
        last = datetime.date(year, 12, 31)
    else:
        last = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    return last - datetime.timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year):
    """Gregoryen takvimde Paskalya pazarını döndürür (Good Friday için)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def _observed(year, month, day):
    """Hafta sonuna denk gelen sabit tarihli tatili Cuma/Pazartesi'ye kaydırır."""
    d = datetime.date(year, month, day)
    if d.weekday() == 5:          # Cumartesi -> önceki Cuma
        return d - datetime.timedelta(days=1)
    if d.weekday() == 6:          # Pazar -> sonraki Pazartesi
        return d + datetime.timedelta(days=1)
    return d


def market_holidays(year):
    """NYSE (ABD borsası) resmi tatillerini döndürür."""
    days = [
        _observed(year, 1, 1),                       # Yılbaşı
        _nth_weekday(year, 1, 0, 3),                 # Martin Luther King (Ocak 3. Pzt)
        _nth_weekday(year, 2, 0, 3),                 # Presidents Day (Şubat 3. Pzt)
        _easter(year) - datetime.timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),                   # Memorial Day (Mayıs son Pzt)
        _nth_weekday(year, 9, 0, 1),                 # Labor Day (Eylül 1. Pzt)
        _nth_weekday(year, 11, 3, 4),                # Thanksgiving (Kasım 4. Per)
        _observed(year, 12, 25),                     # Noel
    ]
    if year >= 2022:                                 # Juneteenth 2022'den beri resmi
        days.append(_observed(year, 6, 19))
    return days


def market_open():
    et = et_now()
    if et.weekday() >= 5:
        return False
    if datetime.date(et.year, et.month, et.day) in market_holidays(et.year):
        return False
    t = et.hour * 60 + et.minute
    return 9 * 60 + 30 <= t < 16 * 60


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
    if not isinstance(cfg.get("symbols"), list) or not cfg["symbols"]:
        cfg["symbols"] = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
    if cfg.get("theme") not in PALETTES:
        cfg["theme"] = "gece"
    try:
        cfg["opacity"] = min(1.0, max(0.6, float(cfg.get("opacity", 0.97))))
    except (TypeError, ValueError):
        cfg["opacity"] = 0.97
    if cfg.get("density") not in ("normal", "compact"):
        cfg["density"] = "normal"
    if not isinstance(cfg.get("positions"), dict):
        cfg["positions"] = {}
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


def fetch_quote(symbol):
    url = API_URL.format(s=symbol)
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    result = data["chart"]["result"]
    if not result:
        raise ValueError("no data")
    meta = result[0]["meta"]
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None or not prev:
        raise ValueError("missing fields")
    # Aynı yanıttan detay alanları — ekstra istek yok
    try:
        quote = result[0]["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        quote = {}
    stamps = result[0].get("timestamp") or []
    arr = {
        "close": quote.get("close") or [],
        "open": quote.get("open") or [],
        "high": quote.get("high") or [],
        "low": quote.get("low") or [],
        "volume": quote.get("volume") or [],
    }
    n_raw = len(arr["close"])
    stamps = (stamps[:n_raw] if stamps else [None] * n_raw)

    def _at(key, i):
        a = arr[key]
        return a[i] if i < len(a) else None

    rows = []
    for i in range(n_raw):
        c = arr["close"][i]
        if c is None:
            continue
        o = _at("open", i)
        h = _at("high", i)
        lo_ = _at("low", i)
        o = c if o is None else o
        h = max(o, c, h if h is not None else o)
        lo_ = min(o, c, lo_ if lo_ is not None else o)
        rows.append((stamps[i], c, o, h, lo_, _at("volume", i)))
    if len(rows) > 60:
        step = (len(rows) - 1) / 59.0
        idx = list(dict.fromkeys(int(round(i * step)) for i in range(60)))
        rows = [rows[i] for i in idx]
    closes = [r[1] for r in rows]
    spark_times = ([r[0] for r in rows] if stamps and stamps[0] is not None
                   else [])
    spark_volumes = [r[5] or 0 for r in rows]
    spark_ohlc = [(r[2], r[3], r[4], r[1]) for r in rows]
    highs = [h for h in quote.get("high") or [] if h is not None]
    lows = [lo for lo in quote.get("low") or [] if lo is not None]
    opens = [o for o in quote.get("open") or [] if o is not None]
    volumes = [v for v in quote.get("volume") or [] if v]
    day_high = meta.get("regularMarketDayHigh") or (max(highs) if highs else None)
    day_low = meta.get("regularMarketDayLow") or (min(lows) if lows else None)
    volume = meta.get("regularMarketVolume") or (sum(volumes) if volumes else None)
    return {
        "symbol": symbol,
        "name": meta.get("shortName") or meta.get("longName") or symbol,
        "currency": meta.get("currency") or "USD",
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "",
        "price": float(price),
        "prev_close": float(prev),
        "change_pct": (float(price) / float(prev) - 1.0) * 100.0,
        "change_abs": float(price) - float(prev),
        "open": float(opens[0]) if opens else None,
        "day_high": float(day_high) if day_high else None,
        "day_low": float(day_low) if day_low else None,
        "high_52w": meta.get("fiftyTwoWeekHigh"),
        "low_52w": meta.get("fiftyTwoWeekLow"),
        "volume": volume,
        "spark": closes,
        "spark_times": spark_times,
        "spark_volumes": spark_volumes,
        "spark_ohlc": spark_ohlc,
    }


def startup_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except (OSError, ImportError):
        return False


def app_launch_command():
    """Otomatik başlatma için komut: exe ise exe, kaynak ise pythonw + script."""
    if FROZEN:
        return '"%s"' % sys.executable
    pyw = sys.executable
    if pyw.lower().endswith("python.exe"):
        pyw = pyw[:-10] + "pythonw.exe"
    return '"%s" "%s"' % (pyw, os.path.join(BASE_DIR, "stock_widget.py"))


def set_startup(enabled):
    try:
        import winreg
        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ,
                                  app_launch_command())
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, RUN_NAME)
        return True
    except (OSError, ImportError):
        return False


def acquire_single_instance():
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool,
                                          ctypes.c_wchar_p]
        handle = kernel32.CreateMutexW(
            None, False, "Local\\StockWidgetDesktopInstance")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return None
        return handle
    except Exception:
        return 1


def create_signal_event(name):
    """Çalışan kopyanın dinleyeceği isimli olayı oluşturur."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateEventW.restype = ctypes.c_void_p
        kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool,
                                          ctypes.c_bool, ctypes.c_wchar_p]
        return kernel32.CreateEventW(None, False, False, name)
    except Exception:
        return None


def request_signal(name, retries=20):
    """Çalışan kopyaya sinyal gönderir; olay yoksa False döner."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenEventW.restype = ctypes.c_void_p
        kernel32.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_bool,
                                        ctypes.c_wchar_p]
        kernel32.SetEvent.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        for _ in range(retries):
            handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, name)
            if handle:
                try:
                    kernel32.SetEvent(ctypes.c_void_p(handle))
                    return True
                finally:
                    kernel32.CloseHandle(ctypes.c_void_p(handle))
            time.sleep(0.1)
    except Exception:
        pass
    return False


def request_toggle(retries=20):
    """Çalışan kopyaya göster/gizle sinyali gönder (yoksa False)."""
    return request_signal(TOGGLE_EVENT, retries)


def request_quit(retries=20):
    """Çalışan kopyaya temiz çıkış sinyali gönder (yoksa False)."""
    return request_signal(QUIT_EVENT, retries)


def signal_watch_loop(targets, events, stop_flag):
    """Ana kopyada çalışır; olayları ('toggle'/'quit') kuyruğa aktarır.

    targets: [(handle, "toggle"), (handle, "quit")] — None handle'lar atlanır.
    """
    pairs = [(h, n) for h, n in targets if h]
    if not pairs:
        return
    kernel32 = ctypes.windll.kernel32
    handles = (ctypes.c_void_p * len(pairs))(
        *[ctypes.c_void_p(h) for h, _ in pairs])
    kernel32.WaitForMultipleObjects.argtypes = [
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.c_bool,
        ctypes.c_uint32]
    kernel32.WaitForMultipleObjects.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    try:
        while not stop_flag.is_set():
            res = kernel32.WaitForMultipleObjects(len(pairs), handles, False,
                                                  500)
            if res == 258:  # WAIT_TIMEOUT
                continue
            if res == 0xFFFFFFFF:  # WAIT_FAILED
                return
            index = res  # WAIT_OBJECT_0 + i
            if index >= len(pairs):
                continue  # WAIT_ABANDONED: döngü devam etsin
            name = pairs[index][1]
            events.put(name)
            if name == "quit":
                return
    finally:
        for h, _ in pairs:
            kernel32.CloseHandle(ctypes.c_void_p(h))


def hotkey_loop(events, stop_flag):
    """Ctrl+Alt+S'yi sistem genelinde dinler, basılınca kuyruğa 'toggle' yazar."""
    try:
        user32 = ctypes.windll.user32
        msg = ctypes.wintypes.MSG()
        registered = user32.RegisterHotKey(
            None, HOTKEY_ID, HOTKEY_MODS | HOTKEY_NOREPEAT, HOTKEY_VK)
        if not registered:
            registered = user32.RegisterHotKey(
                None, HOTKEY_ID, HOTKEY_MODS, HOTKEY_VK)
        if not registered:
            events.put("unavailable")
            return
        events.put("registered")
        try:
            while not stop_flag.is_set():
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == WM_HOTKEY:
                        events.put("toggle")
                time.sleep(0.05)
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
    except Exception:
        events.put("unavailable")


def dark_title_bar(win):
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value),
                    ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def round_rect(c, x1, y1, x2, y2, r, fill=None, outline=None, tags=None):
    tags = tags or ()
    if fill:
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="",
                           tags=tags)
        c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="",
                           tags=tags)
        for ax, ay, start in ((x1, y1, 90), (x2 - 2 * r, y1, 0),
                              (x2 - 2 * r, y2 - 2 * r, 270),
                              (x1, y2 - 2 * r, 180)):
            c.create_arc(ax, ay, ax + 2 * r, ay + 2 * r, start=start,
                         extent=90, style="pieslice", fill=fill, outline=fill,
                         tags=tags)
    if outline:
        c.create_line(x1 + r, y1, x2 - r, y1, fill=outline, tags=tags)
        c.create_line(x1 + r, y2, x2 - r, y2, fill=outline, tags=tags)
        c.create_line(x1, y1 + r, x1, y2 - r, fill=outline, tags=tags)
        c.create_line(x2, y1 + r, x2, y2 - r, fill=outline, tags=tags)
        for ax, ay, start in ((x1, y1, 90), (x2 - 2 * r, y1, 0),
                              (x2 - 2 * r, y2 - 2 * r, 270),
                              (x1, y2 - 2 * r, 180)):
            c.create_arc(ax, ay, ax + 2 * r, ay + 2 * r, start=start,
                         extent=90, style="arc", outline=outline, tags=tags)


def fmt_money(value, currency):
    if value is None:
        return "—"
    prefix = {"USD": "$", "EUR": "€", "GBP": "£"}.get((currency or "").upper())
    body = "{:,.2f}".format(value)
    if prefix:
        return prefix + body
    return body + (" " + currency if currency else "")


def fmt_volume(value):
    if not value:
        return "—"
    value = float(value)
    if value >= 1e9:
        return "{:.2f}B".format(value / 1e9)
    if value >= 1e6:
        return "{:.1f}M".format(value / 1e6)
    if value >= 1e3:
        return "{:.0f}K".format(value / 1e3)
    return str(int(value))


def _hex_rgb(color):
    h = (color or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return (128, 128, 128)


def pick_mono(root):
    """Fiyatlar için sabit genişlikli (tabular) bir yazı tipi seçer."""
    try:
        fams = set(tkfont.families(root))
    except tk.TclError:
        return "Segoe UI"
    for f in ("Cascadia Mono", "Cascadia Code", "Consolas", "Courier New"):
        if f in fams:
            return f
    return "Segoe UI"


def render_spark(values, w, h, color, fill=None, ref=None, grid=None,
                 grid_lines=0, volumes=None, ss=4, dot=True):
    """PIL ile anti-aliased sparkline (w x h piksel) üretir."""
    w, h = max(1, int(w)), max(1, int(h))
    if not values or len(values) < 2:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    W, H = w * ss, h * ss
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bounds = list(vals) + ([ref] if ref is not None else [])
    lo, hi = min(bounds), max(bounds)
    rng = (hi - lo) or 1.0
    n = len(vals)
    rgb = _hex_rgb(color)

    def yy(v):
        return (H - 1) - (v - lo) / rng * (H - 1)

    pts = [(i / float(n - 1) * (W - 1), yy(v)) for i, v in enumerate(vals)]

    if fill:
        poly = pts + [(W - 1, H - 1), (0, H - 1)]
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).polygon(poly, fill=255)
        grad = Image.new("L", (W, H))
        gd = ImageDraw.Draw(grad)
        for y in range(H):
            gd.line([(0, y), (W, y)], fill=int(115 * (1.0 - y / float(H))))
        alpha = ImageChops.multiply(mask, grad)
        layer = Image.new("RGBA", (W, H), _hex_rgb(fill) + (0,))
        layer.putalpha(alpha)
        img = Image.alpha_composite(img, layer)
        d = ImageDraw.Draw(img)

    if grid and grid_lines:
        grgb = _hex_rgb(grid)
        for k in range(1, grid_lines + 1):
            gy = (H - 1) * k / float(grid_lines + 1)
            d.line([(0, gy), (W - 1, gy)], fill=grgb + (60,),
                   width=max(1, ss // 2))

    if volumes:
        vol = list(volumes[:len(vals)])
        vmax = max([v for v in vol if v] or [1.0])
        vb = H * 0.22
        bw = max(1, int(round((W - 1) / float(max(1, n)) * 0.55)))
        vrgb = _hex_rgb(fill or color)
        for i, v in enumerate(vol):
            if not v:
                continue
            x = i / float(n - 1) * (W - 1)
            bh = (v / float(vmax)) * vb
            d.rectangle([x - bw, H - 1 - bh, x + bw, H - 1],
                        fill=vrgb + (55,))

    if ref is not None:
        ry = yy(ref)
        dash, x, drgb = max(2, ss * 2), 0, _hex_rgb(DIM)
        while x < W:
            d.line([(x, ry), (min(W - 1, x + dash), ry)],
                   fill=drgb + (150,), width=max(1, ss // 2))
            x += dash * 2

    d.line(pts, fill=rgb + (255,), width=max(1, int(round(1.6 * ss))),
           joint="curve")
    if dot:
        r = max(2, int(round(2 * ss)))
        ex, ey = pts[-1]
        d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=rgb + (255,))
    return img.resize((w, h), Image.LANCZOS)


def downsample_ohlc(ohlc, max_n=70):
    """Mum grafiği için OHLC listesini max_n kovaya indirger."""
    n = len(ohlc)
    if n <= max_n:
        return list(ohlc)
    out = []
    for k in range(max_n):
        a = int(k * n / float(max_n))
        b = int((k + 1) * n / float(max_n))
        chunk = ohlc[a:b]
        if not chunk:
            continue
        out.append((chunk[0][0], max(x[1] for x in chunk),
                    min(x[2] for x in chunk), chunk[-1][3]))
    return out


def render_candles(ohlc, w, h, up_color, down_color, grid=None, grid_lines=0,
                   ss=4):
    """PIL ile anti-aliased mum (candlestick) grafiği."""
    w, h = max(1, int(w)), max(1, int(h))
    if not ohlc or len(ohlc) < 2:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    W, H = w * ss, h * ss
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lo = min(c[2] for c in ohlc)
    hi = max(c[1] for c in ohlc)
    rng = (hi - lo) or 1.0

    def yy(v):
        return (H - 1) - (v - lo) / rng * (H - 1)

    if grid and grid_lines:
        grgb = _hex_rgb(grid)
        for k in range(1, grid_lines + 1):
            gy = (H - 1) * k / float(grid_lines + 1)
            d.line([(0, gy), (W - 1, gy)], fill=grgb + (60,),
                   width=max(1, ss // 2))

    n = len(ohlc)
    slot = (W - 1) / float(n)
    bw = max(ss, int(round(slot * 0.6)))
    up = _hex_rgb(up_color)
    down = _hex_rgb(down_color)
    wick = max(1, ss // 2)
    for i, (o, hh, ll, c) in enumerate(ohlc):
        x = (i + 0.5) * slot
        col = up if c >= o else down
        d.line([(x, yy(hh)), (x, yy(ll))], fill=col + (210,), width=wick)
        top = min(yy(o), yy(c))
        bot = max(yy(o), yy(c))
        if bot - top < ss:
            bot = top + ss
        d.rectangle([x - bw / 2.0, top, x + bw / 2.0, bot],
                    fill=col + (230,))
    return img.resize((w, h), Image.LANCZOS)


SERIES_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/"
              "{s}?range={r}&interval={i}")

TF_RANGE = {"1H": ("5d", "15m"), "1A": ("1mo", "1d"), "1Y": ("1y", "1d")}
TF_TTL = {"1H": 15 * 60, "1A": 60 * 60, "1Y": 60 * 60}
TF_LABEL = {"1D": "1G", "1H": "1H", "1A": "1A", "1Y": "1Y"}
TF_TABS = ("1D", "1H", "1A", "1Y")

_SERIES_CACHE = {}


def fetch_series(symbol, tf):
    """Seçilen zaman aralığı için kapanış serisi (tembel + önbellekli)."""
    key = (symbol, tf)
    now = time.time()
    hit = _SERIES_CACHE.get(key)
    if hit and now - hit[0] < TF_TTL[tf]:
        return hit[1]
    rng, interval = TF_RANGE[tf]
    resp = requests.get(SERIES_URL.format(s=symbol, r=rng, i=interval),
                        headers=HEADERS, timeout=10)
    resp.raise_for_status()
    res = resp.json()["chart"]["result"][0]
    stamps = res.get("timestamp") or []
    quote = (res.get("indicators") or {}).get("quote") or [{}]
    q = quote[0]
    raw = {
        "close": q.get("close") or [],
        "open": q.get("open") or [],
        "high": q.get("high") or [],
        "low": q.get("low") or [],
        "volume": q.get("volume") or [],
    }
    n_raw = len(raw["close"])
    stamps = (stamps[:n_raw] if stamps else [None] * n_raw)

    def _at(key, i):
        a = raw[key]
        return a[i] if i < len(a) else None

    pts = []
    for i in range(n_raw):
        c = raw["close"][i]
        if c is None:
            continue
        o = _at("open", i)
        h = _at("high", i)
        lo_ = _at("low", i)
        o = c if o is None else o
        h = max(o, c, h if h is not None else o)
        lo_ = min(o, c, lo_ if lo_ is not None else o)
        pts.append((stamps[i], c, o, h, lo_, _at("volume", i)))
    if len(pts) < 2:
        raise ValueError("empty series")
    if len(pts) > 150:
        step = (len(pts) - 1) / 149.0
        idx = [int(round(i * step)) for i in range(150)]
        pts = [pts[i] for i in dict.fromkeys(idx)]
    data = {
        "closes": [p[1] for p in pts],
        "times": [p[0] for p in pts],
        "volumes": [p[5] or 0 for p in pts],
        "ohlc": [(p[2], p[3], p[4], p[1]) for p in pts],
    }
    _SERIES_CACHE[key] = (now, data)
    return data


class DetailPanel:
    WIDTH = 300
    HEIGHT = 398

    def __init__(self, app, symbol):
        self.app = app
        self.symbol = symbol
        self.s = app.s
        self._closed = False
        self.tf = "1D"
        self.series = {}
        self.errors = set()
        self.loading = None
        self.mode = "line"
        self._res = queue.Queue()
        self._chart_photo = None

        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", getattr(app, "alpha", 0.97))
        self.win.configure(bg=KEY)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(self.win, bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.tag_bind("dclose", "<Enter>",
                             lambda e: self.canvas.itemconfig("dclose",
                                                             fill=RED))
        self.canvas.tag_bind("dclose", "<Leave>",
                             lambda e: self.canvas.itemconfig("dclose",
                                                              fill=DIM))
        self.canvas.tag_bind("dclose", "<Button-1>",
                             lambda e: self.win.after(10, self.close))
        for tf in TF_TABS:
            txt_tag, hit_tag = "tf_" + tf, "tfb_" + tf
            for tag in (txt_tag, hit_tag):
                self.canvas.tag_bind(
                    tag, "<Button-1>",
                    lambda e, t=tf: self.win.after(0, self.set_tf, t))
            self.canvas.tag_bind(
                txt_tag, "<Enter>",
                lambda e, t=tf: self._tab_hover(t, True))
            self.canvas.tag_bind(
                txt_tag, "<Leave>",
                lambda e, t=tf: self._tab_hover(t, False))
        self.canvas.tag_bind(
            "modebtn", "<Button-1>",
            lambda e: self.win.after(0, self.toggle_mode))
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self._dx = 0
        self._dy = 0
        self._plot = None
        self._hover_idx = None

        self.reposition()
        self.render()
        app.root.after(150, self._poll_results)

    # ---------- timeframe ----------

    def set_tf(self, tf):
        if self._closed:
            return
        if tf == self.tf:
            # Aynı sekme: yüklü ya da yükleniyorsa yapacak bir şey yok;
            # hata aldıysa aşağıda yeniden dener.
            if tf == "1D" or tf in self.series or self.loading == tf:
                return
        self.tf = tf
        self.errors.discard(tf)
        if tf != "1D" and tf not in self.series:
            self.loading = tf
            threading.Thread(target=self._fetch_series, args=(tf,),
                             daemon=True).start()
        self.render()

    def _fetch_series(self, tf):
        try:
            data = fetch_series(self.symbol, tf)
        except Exception:
            data = None
        try:
            self._res.put((tf, data))
        except Exception:
            pass

    def _poll_results(self):
        if self._closed:
            return
        try:
            while True:
                tf, data = self._res.get_nowait()
                if self.loading == tf:
                    self.loading = None
                if data is None:
                    self.errors.add(tf)
                else:
                    self.series[tf] = data
                    self.errors.discard(tf)
                if self.tf == tf:
                    self.render()
        except queue.Empty:
            pass
        self.app.root.after(200, self._poll_results)

    def _tab_hover(self, tf, on):
        if self._closed or tf == self.tf:
            return
        try:
            self.canvas.itemconfig("tf_" + tf, fill=FG if on else MUTED)
        except tk.TclError:
            pass

    def _chart_data(self):
        if self.tf == "1D":
            info = self.app.last.get(self.symbol) or {}
            return {
                "closes": list(info.get("spark") or []),
                "times": list(info.get("spark_times") or []),
                "volumes": list(info.get("spark_volumes") or []),
                "ohlc": list(info.get("spark_ohlc") or []),
            }
        data = self.series.get(self.tf) or {}
        return {
            "closes": list(data.get("closes") or []),
            "times": list(data.get("times") or []),
            "volumes": list(data.get("volumes") or []),
            "ohlc": list(data.get("ohlc") or []),
        }

    # ---------- chart hover ----------

    def _on_motion(self, event):
        if self._closed or not self._plot:
            return
        p = self._plot
        y1, y2 = self.s(140), self.s(202)
        if not (p["x1"] - 2 <= event.x <= p["x2"] + 2
                and y1 - 4 <= event.y <= y2 + 4):
            if self._hover_idx is not None:
                self.canvas.config(cursor="")
                self._clear_hover()
            return
        n = p["n"]
        frac = (event.x - p["x1"]) / float(p["x2"] - p["x1"])
        idx = max(0, min(n - 1, int(round(frac * (n - 1)))))
        self.canvas.config(cursor="crosshair")
        self._hover_idx = idx
        self._draw_hover(idx)

    def _on_leave(self, event):
        self.canvas.config(cursor="")
        self._clear_hover()

    def _clear_hover(self):
        self._hover_idx = None
        try:
            self.canvas.delete("chov")
            self.canvas.itemconfig("axislbl", state="normal")
        except tk.TclError:
            pass

    def _hover_label(self, idx):
        p = self._plot
        stamps = p.get("stamps") or []
        if idx >= len(stamps):
            return "gün içi" if self.tf == "1D" else ""
        try:
            if self.tf == "1D":
                return datetime.datetime.fromtimestamp(
                    stamps[idx]).strftime("%H:%M")
            fmt = {"1H": "%d.%m %H:%M", "1A": "%d.%m",
                   "1Y": "%d.%m.%y"}[self.tf]
            return datetime.datetime.fromtimestamp(stamps[idx]).strftime(fmt)
        except (OverflowError, OSError, ValueError):
            return ""

    def _draw_hover(self, idx):
        if self._closed or not self._plot:
            return
        p = self._plot
        c, s = self.canvas, self.s
        n, spark = p["n"], p["spark"]
        c.delete("chov")
        c.itemconfig("axislbl", state="hidden")
        x1, x2, y1, y2 = p["x1"], p["x2"], p["y1"], p["y2"]
        px = x1 + (x2 - x1) * idx / float(n - 1)
        py = y2 - (spark[idx] - p["lo"]) / p["rng"] * (y2 - y1)

        # seviye çizgisi + dikey imleç + belirgin nokta
        c.create_line(x1, py, x2, py, fill=DIM, dash=(2, 4), tags=("chov",))
        c.create_line(px, y1, px, y2, fill=ACCENT, dash=(2, 2), tags=("chov",))
        c.create_oval(px - s(4), py - s(4), px + s(4), py + s(4),
                      fill=p["col"], outline=FG, width=max(1, s(1)),
                      tags=("chov",))

        price = spark[idx]
        base = p.get("prev") if self.tf == "1D" else spark[0]
        pct = (price / base - 1.0) * 100.0 if base else None
        tcol = (GREEN if pct is not None and pct >= 0
                else RED if pct is not None else FG)

        # grafiğin altında belirgin okuma çubuğu
        by1, by2 = s(205), s(225)
        mid = (by1 + by2) / 2.0
        round_rect(c, x1, by1, x2, by2, s(8),
                   fill=RAISED, outline=DIVIDER, tags=("chov",))
        lbl = self._hover_label(idx)
        c.create_text(x1 + s(10), mid, text=lbl, anchor="w", fill=MUTED,
                      font=("Segoe UI", 7), tags=("chov",))
        price_txt = fmt_money(price, p.get("cur"))
        if pct is not None:
            pct_txt = "%+.2f%%" % pct
            pw = self.app.font_pct.measure(pct_txt) + s(14)
            ph = s(16)
            px2 = x2 - s(8)
            px1 = px2 - pw
            py1 = mid - ph / 2.0
            round_rect(c, px1, py1, px2, py1 + ph, ph // 2,
                       fill=GREEN_DIM if pct >= 0 else RED_DIM,
                       tags=("chov",))
            c.create_text((px1 + px2) / 2.0, mid, text=pct_txt, fill=tcol,
                          font=("Segoe UI", 8, "bold"), tags=("chov",))
            cx = (x1 + px1) / 2.0
        else:
            cx = (x1 + x2) / 2.0
        c.create_text(cx, mid, text=price_txt, fill=FG,
                      font=(self.app.mono, 10, "bold"), tags=("chov",))

    # ---------- geometry ----------

    def _press(self, event):
        self._dx = self.win.winfo_pointerx() - self.win.winfo_rootx()
        self._dy = self.win.winfo_pointery() - self.win.winfo_rooty()

    def _drag(self, event):
        x = self.win.winfo_pointerx() - self._dx
        y = self.win.winfo_pointery() - self._dy
        self.win.geometry("+%d+%d" % (x, y))

    def reposition(self):
        if self._closed:
            return
        s = self.s
        W, H = s(self.WIDTH), s(self.HEIGHT)
        try:
            sm = ctypes.windll.user32.GetSystemMetrics
            sw, sh = sm(0), sm(1)
        except Exception:
            sw = self.app.root.winfo_screenwidth()
            sh = self.app.root.winfo_screenheight()
        gx, gy = self.app.root.winfo_x(), self.app.root.winfo_y()
        x = gx + self.app.W + s(8)
        if x + W > sw - s(4):
            x = gx - W - s(8)
        x = max(s(4), x)
        y = max(s(4), min(gy, sh - H - s(8)))
        self.win.geometry("%dx%d+%d+%d" % (W, H, x, y))

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.app._detail is self:
            self.app._detail = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # ---------- drawing ----------

    def _range_bar(self, x1, x2, y, lo, hi, value, col):
        s = self.s
        h = s(5)
        round_rect(self.canvas, x1, y, x2, y + h, h // 2, fill=TRACK)
        if lo is None or hi is None or hi <= lo:
            return
        v = hi if value is None else min(max(value, lo), hi)
        fx = x1 + (x2 - x1) * (v - lo) / (hi - lo)
        if fx - x1 > s(2):
            round_rect(self.canvas, x1, y, fx, y + h, h // 2, fill=col)
        self.canvas.create_oval(fx - s(3), y - s(2), fx + s(3), y + h + s(2),
                                fill=FG, outline="")

    def _draw_tabs(self, pad, y1, y2):
        c, s = self.canvas, self.s
        w, gap = s(34), s(5)
        for i, tf in enumerate(TF_TABS):
            x1 = pad + i * (w + gap)
            x2 = x1 + w
            active = tf == self.tf
            c.create_rectangle(x1, y1, x2, y2, fill=TRACK if active else CARD,
                               outline="",
                               tags=(("tfb_" + tf,) if active else ("tfb_" + tf,)))
            c.create_text((x1 + x2) / 2.0, (y1 + y2) / 2.0 + s(1),
                          text=TF_LABEL[tf], fill=ACCENT if active else MUTED,
                          font=("Segoe UI", 8, "bold" if active else "normal"),
                          tags=("tf_" + tf,))

    def _draw_chart(self, pad, x2, y1, y2, info, col):
        c, s = self.canvas, self.s
        data = self._chart_data()
        spark, stamps = data["closes"], data["times"]
        vols, ohlc = data["volumes"], data["ohlc"]
        self._plot = None
        if self.loading == self.tf:
            c.create_text((pad + x2) / 2.0, (y1 + y2) / 2.0,
                          text="yükleniyor…", fill=DIM, font=("Segoe UI", 8))
            return
        if not spark or len(spark) < 2:
            msg = "grafik yüklenemedi" if self.tf in self.errors else "veri yok"
            c.create_text((pad + x2) / 2.0, (y1 + y2) / 2.0,
                          text=msg, fill=DIM, font=("Segoe UI", 8))
            return
        prev = info.get("prev_close")
        candle = (self.mode == "candle" and len(ohlc) > 1)
        if candle:
            candles = downsample_ohlc(ohlc, 70)
            plot_spark = [x[3] for x in candles]
            plot_stamps = []
            lo = min(x[2] for x in candles)
            hi = max(x[1] for x in candles)
        else:
            candles = None
            plot_spark, plot_stamps = spark, stamps
            values = list(spark) + ([prev] if self.tf == "1D" and prev else [])
            lo, hi = min(values), max(values)
        rng = (hi - lo) or 1.0
        n = len(plot_spark)
        if PIL_AVAILABLE:
            if candle:
                img = render_candles(candles, x2 - pad, y2 - y1, GREEN, RED,
                                     grid=DIVIDER, grid_lines=2)
            else:
                img = render_spark(spark, x2 - pad, y2 - y1, col, fill=col,
                                   ref=prev if self.tf == "1D" else None,
                                   grid=DIVIDER, grid_lines=2, volumes=vols)
            photo = ImageTk.PhotoImage(img, master=self.win)
            self._chart_photo = photo
            c.create_image(pad, y1, image=photo, anchor="nw")
        else:
            pts = []
            for i, v in enumerate(plot_spark):
                pts.extend((pad + (x2 - pad) * i / float(n - 1),
                            y2 - (v - lo) / rng * (y2 - y1)))
            if self.tf == "1D" and prev and not candle:
                pl = y2 - (prev - lo) / rng * (y2 - y1)
                c.create_line(pad, pl, x2, pl, fill=DIM, dash=(2, 3))
            c.create_line(*pts, fill=col,
                          width=max(1, int(round(1.6 * self.app.S))))
            c.create_oval(pts[-2] - s(2), pts[-1] - s(2),
                          pts[-2] + s(2), pts[-1] + s(2), fill=col,
                          outline="")
        self._plot = {
            "x1": pad, "x2": x2, "y1": y1, "y2": y2,
            "spark": plot_spark, "stamps": plot_stamps or [],
            "lo": lo, "hi": hi, "rng": rng, "n": n,
            "prev": prev, "col": col, "candle": candle,
            "cur": info.get("currency") or "USD",
        }

    def _draw_mode_btn(self, x2, y1, y2):
        label = "mum" if self.mode == "line" else "çizgi"
        self.canvas.create_text(
            x2, (y1 + y2) / 2.0, text=label, anchor="e",
            fill=ACCENT if self.mode == "candle" else MUTED,
            font=("Segoe UI", 7, "bold"), tags=("modebtn",))

    def toggle_mode(self):
        if self._closed:
            return
        self.mode = "candle" if self.mode == "line" else "line"
        self.render()

    def _draw_axis(self, chart_x2, x2, y1, y2):
        if not self._plot:
            return
        lo, hi = self._plot["lo"], self._plot["hi"]
        for frac, val in ((0.0, hi), (0.5, (hi + lo) / 2.0), (1.0, lo)):
            y = y1 + (y2 - y1) * frac
            self.canvas.create_text(
                x2, y, text="%.2f" % val, anchor="e", fill=DIM,
                font=("Segoe UI", 6))

    def render(self):
        if self._closed:
            return
        c, s = self.canvas, self.s
        W, H = s(self.WIDTH), s(self.HEIGHT)
        pad = s(16)
        c.delete("all")
        round_rect(c, 0, 0, W - 1, H - 1, s(14), fill=CARD, outline=DIVIDER)

        info = self.app.last.get(self.symbol) or {}
        cur = info.get("currency") or "USD"
        price = info.get("price")
        pct = info.get("change_pct")
        up = (pct or 0) >= 0
        col = GREEN if up else RED
        bg = GREEN_DIM if up else RED_DIM
        x2 = W - pad

        c.create_text(pad, s(20), text=self.symbol, anchor="w", fill=FG,
                      font=("Segoe UI", 11, "bold"))
        c.create_text(x2, s(9), text="✕", anchor="ne", fill=DIM,
                      font=("Segoe UI", 9), tags=("dclose",))
        name = info.get("name") or "—"
        if len(name) > 42:
            name = name[:41] + "…"
        c.create_text(pad, s(39), text=name, anchor="w", fill=MUTED,
                      font=("Segoe UI", 7))

        c.create_text(pad, s(70), text=fmt_money(price, cur), anchor="w",
                      fill=FG, font=(self.app.mono, 19, "bold"))
        if pct is not None:
            pct_txt = ("▲ " if up else "▼ ") + "%+.2f%%" % pct
            pw = self.app.font_pct.measure(pct_txt) + s(16)
            ph = s(19)
            py1 = s(61)
            round_rect(c, x2 - pw, py1, x2, py1 + ph, ph // 2, fill=bg)
            c.create_text(x2 - pw / 2.0, py1 + ph / 2.0, text=pct_txt,
                          fill=col, font=("Segoe UI", 8, "bold"))
        change = info.get("change_abs")
        if change is not None:
            c.create_text(pad, s(95), text="bugün %+.2f" % change,
                          anchor="w", fill=MUTED, font=("Segoe UI", 7))

        self._draw_tabs(pad, s(108), s(128))
        self._draw_mode_btn(x2, s(108), s(128))

        # grafik (seçilen zaman aralığı)
        sy1, sy2 = s(140), s(202)
        chart_x2 = x2 - s(28)
        data = self._chart_data()
        chart_col = col
        if self.tf != "1D" and len(data["closes"]) > 1:
            chart_col = (GREEN if data["closes"][-1] >= data["closes"][0]
                         else RED)
        self._draw_chart(pad, chart_x2, sy1, sy2, info, chart_col)
        self._draw_axis(chart_x2, x2, sy1, sy2)

        # eksen etiketleri
        stamps = data["times"]
        if self.tf == "1D":
            left_lbl = "gün içi"
            right_lbl = datetime.datetime.now().strftime("%H:%M")
        else:
            left_lbl = right_lbl = "—"
            if stamps:
                fmt = "%d.%m.%y" if self.tf == "1Y" else "%d.%m"
                left_lbl = datetime.datetime.fromtimestamp(stamps[0]).strftime(fmt)
                right_lbl = datetime.datetime.fromtimestamp(stamps[-1]).strftime(fmt)
        c.create_text(pad, s(212), text=left_lbl, anchor="w", fill=DIM,
                      font=("Segoe UI", 6), tags=("axislbl",))
        c.create_text(chart_x2, s(212), text=right_lbl, anchor="e", fill=DIM,
                      font=("Segoe UI", 6), tags=("axislbl",))

        c.create_line(pad, s(226), x2, s(226), fill=DIVIDER)

        def pair(y, label, value, vcol=FG):
            c.create_text(pad, y, text=label, anchor="w", fill=MUTED,
                          font=("Segoe UI", 8))
            c.create_text(x2, y, text=value, anchor="e", fill=vcol,
                          font=("Segoe UI", 8, "bold"))

        day_lo, day_hi = info.get("day_low"), info.get("day_high")
        pair(s(243), "Gün aralığı",
             ("{:.2f} – {:.2f}".format(day_lo, day_hi)
              if day_lo is not None and day_hi is not None else "—"))
        self._range_bar(pad, x2, s(252), day_lo, day_hi, price, col)
        pair(s(274), "Açılış", fmt_money(info.get("open"), cur))
        pair(s(296), "Önceki kapanış", fmt_money(info.get("prev_close"), cur))
        pair(s(318), "Hacim", fmt_volume(info.get("volume")))
        lo52, hi52 = info.get("low_52w"), info.get("high_52w")
        pair(s(340), "52 hafta",
             ("{:.2f} – {:.2f}".format(lo52, hi52)
              if lo52 is not None and hi52 is not None else "—"))
        self._range_bar(pad, x2, s(349), lo52, hi52, price, ACCENT)

        c.create_line(pad, s(366), x2, s(366), fill=DIVIDER)
        meta_txt = " · ".join(x for x in (info.get("exchange"), cur) if x)
        c.create_text(pad, s(381), text=meta_txt or "—", anchor="w",
                      fill=DIM, font=("Segoe UI", 7))
        c.create_text(x2, s(381), text=datetime.datetime.now().strftime("%H:%M"),
                      anchor="e", fill=DIM, font=("Segoe UI", 7))

class StockWidget:
    def __init__(self):
        self.S = _init_dpi()
        self.cfg = load_config()
        apply_palette(self.cfg["theme"])
        self.alpha = float(self.cfg["opacity"])
        self.density = self.cfg["density"]
        self.last = {}
        self.offline = False
        self._hover_row = None

        self.root = tk.Tk()
        self.root.title("StockWidget")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.alpha)
        self.root.configure(bg=KEY)
        try:
            self.root.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.root.tk.call("tk", "scaling", 96 * self.S / 72.0)

        self.W = self.s(300)
        self.HEADER_H = self.s(34)
        self.PAD = self.s(16)
        self._set_density()

        self.mono = pick_mono(self.root)
        self.f_title = ("Segoe UI", 7, "bold")
        self.f_sym = ("Segoe UI", 10, "bold")
        self.f_price = (self.mono, 11, "bold")
        self.f_pct = ("Segoe UI", 8, "bold")
        self.f_foot = ("Segoe UI", 7)
        self.f_name = ("Segoe UI", 6)
        self.font_pct = tkfont.Font(root=self.root, family="Segoe UI",
                                    size=8, weight="bold")
        self.font_name = tkfont.Font(root=self.root, family="Segoe UI",
                                     size=6)

        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.queue = queue.Queue()
        self.wake = threading.Event()
        self.stop_flag = threading.Event()
        self.last_ok = None
        self.tray_icon = None
        self._editor = None
        self._detail = None
        self._moved = False
        self._px = 0
        self._py = 0
        self._row_photos = {}
        self._chart_photo = None
        self._data_ts = None

        self.theme_var = tk.StringVar(value=self.cfg["theme"])
        self.opacity_var = tk.DoubleVar(value=self.alpha)
        self.density_var = tk.StringVar(value=self.density)
        self._build_menu()

        self._dx = 0
        self._dy = 0
        self.build_ui()
        self._restore_position()

        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._popup_menu)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.tag_bind("close_btn", "<Enter>",
                             lambda e: self.canvas.itemconfig("close_btn",
                                                              fill=RED))
        self.canvas.tag_bind("close_btn", "<Leave>",
                             lambda e: self.canvas.itemconfig("close_btn",
                                                              fill=DIM))
        self.canvas.tag_bind("close_btn", "<Button-1>",
                             lambda e: self.root.after(10, self.hide_window))
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self._setup_tray()
        threading.Thread(target=hotkey_loop,
                         args=(self.hotkey_queue, self.stop_flag),
                         daemon=True).start()

        self.thread = threading.Thread(target=self.fetch_loop, daemon=True)
        self.thread.start()
        self.root.after(150, self.poll_queue)
        self.root.after(20000, self._status_tick)
        if os.environ.get("SW_SMOKE"):
            self.root.after(12000, self.exit_app)

    # ---------- personalization ----------

    def _set_density(self):
        self.ROW_H = self.s(46 if self.density == "normal" else 40)
        self._row_f = self.ROW_H / float(self.s(46))

    def ro(self, v):
        return int(round(v * self.S * self._row_f))

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0, bg=MENU_BG, fg=FG,
                    activebackground=MENU_ACTIVE, activeforeground=FG, bd=0)
        self.menu = m
        m.add_command(label="Sembol ekle / çıkar…",
                      command=self.open_symbol_editor)
        m.add_command(label="Portföy…", command=self.open_portfolio_editor)
        self.remove_menu = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=FG,
                                   activebackground=MENU_ACTIVE)
        m.add_cascade(label="Hızlı çıkar", menu=self.remove_menu)
        m.add_separator()
        m.add_command(label="Yenile", command=self.refresh_now)

        self.theme_menu = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=FG,
                                  activebackground=MENU_ACTIVE)
        for key in THEME_ORDER:
            self.theme_menu.add_radiobutton(
                label=THEME_LABEL[key], value=key, variable=self.theme_var,
                command=lambda k=key: self.set_theme(k))
        m.add_cascade(label="Tema", menu=self.theme_menu)

        self.opacity_menu = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=FG,
                                    activebackground=MENU_ACTIVE)
        for v in (0.8, 0.85, 0.9, 0.95, 1.0):
            self.opacity_menu.add_radiobutton(
                label="%d%%" % int(round(v * 100)), value=v,
                variable=self.opacity_var,
                command=lambda val=v: self.set_opacity(val))
        m.add_cascade(label="Opaklık", menu=self.opacity_menu)

        self.density_menu = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=FG,
                                    activebackground=MENU_ACTIVE)
        self.density_menu.add_radiobutton(
            label="Normal", value="normal", variable=self.density_var,
            command=lambda: self.set_density("normal"))
        self.density_menu.add_radiobutton(
            label="Kompakt", value="compact", variable=self.density_var,
            command=lambda: self.set_density("compact"))
        m.add_cascade(label="Yoğunluk", menu=self.density_menu)

        self.startup_var = tk.BooleanVar(value=startup_enabled())
        self.hotkey_ok = None
        self.hotkey_queue = queue.Queue()
        m.add_checkbutton(label="Windows'ta otomatik başlat",
                          variable=self.startup_var,
                          command=self.toggle_startup)
        self.hotkey_idx = m.index("end") + 1
        m.add_command(label="Kısayol: Ctrl+Alt+S – göster/gizle",
                      state="disabled")
        m.add_separator()
        m.add_command(label="Gizle", command=self.hide_window)
        m.add_command(label="Çıkış", command=self.exit_app)

    def _style_menus(self):
        for mm in (getattr(self, "menu", None), self.remove_menu,
                   self.theme_menu, self.opacity_menu, self.density_menu):
            if mm is None:
                continue
            try:
                mm.configure(bg=MENU_BG, fg=FG,
                             activebackground=MENU_ACTIVE,
                             activeforeground=FG)
            except tk.TclError:
                pass

    def set_theme(self, key):
        apply_palette(key)
        self.cfg["theme"] = key
        save_config(self.cfg)
        self._style_menus()
        self.build_ui()
        self._restore_position()
        if self._detail is not None:
            self._detail.render()

    def set_opacity(self, val):
        self.alpha = float(val)
        self.cfg["opacity"] = self.alpha
        save_config(self.cfg)
        try:
            self.root.attributes("-alpha", self.alpha)
        except tk.TclError:
            pass
        if self._detail is not None:
            try:
                self._detail.win.attributes("-alpha", self.alpha)
            except tk.TclError:
                pass

    def set_density(self, key):
        if key not in ("normal", "compact"):
            return
        self.density = key
        self.cfg["density"] = key
        save_config(self.cfg)
        self._set_density()
        self.build_ui()
        self._restore_position()
        if self._detail is not None:
            self._detail.reposition()

    def _status_tick(self):
        try:
            self._update_status()
            self.root.after(20000, self._status_tick)
        except tk.TclError:
            pass

    def _rel_time(self):
        if not self._data_ts:
            return "güncelleniyor…"
        d = int(time.time() - self._data_ts)
        if d < 60:
            return "az önce"
        if d < 3600:
            return "%d dk önce" % (d // 60)
        if d < 86400:
            return "%d sa önce" % (d // 3600)
        return "%d gün önce" % (d // 86400)

    def _ellipsize(self, text, font, max_w):
        try:
            if font.measure(text) <= max_w:
                return text
            t = text
            while t and font.measure(t + "…") > max_w:
                t = t[:-1]
            return (t + "…") if t else ""
        except tk.TclError:
            return text

    # ---------- portfolio ----------

    def _has_portfolio(self):
        pos = self.cfg.get("positions") or {}
        return any(isinstance(p, dict) and (p.get("qty") or 0) > 0
                   for p in pos.values())

    def _portfolio_stats(self):
        pos = self.cfg.get("positions") or {}
        val = cost = day = 0.0
        ok = False
        cur = None
        for sym, p in pos.items():
            if not isinstance(p, dict):
                continue
            try:
                qty = float(p.get("qty") or 0)
                avg = float(p.get("avg") or 0)
            except (TypeError, ValueError):
                continue
            info = self.last.get(sym)
            if qty <= 0 or not info:
                continue
            ok = True
            if cur is None:
                cur = info.get("currency")
            val += qty * info["price"]
            cost += qty * avg
            day += qty * (info["price"] - info["prev_close"])
        return ok, val, cost, day, cur

    def _draw_portfolio(self, y):
        c = self.canvas
        w = self.W
        mid = y + self.s(9)
        self._round_rect(self.PAD - self.s(4), y,
                         w - self.PAD + self.s(4), y + self.s(18),
                         self.s(9), fill=RAISED, tags=("pf",))
        c.create_text(self.PAD, mid, text="Portföy", anchor="w", fill=MUTED,
                      font=("Segoe UI", 7), tags=("pf",))
        ok, val, cost, day, cur = self._portfolio_stats()
        if not ok:
            c.create_text(w - self.PAD, mid, text="adet gir", anchor="e",
                          fill=DIM, font=("Segoe UI", 7), tags=("pf",))
            return
        base = val - day
        pct = (day / base * 100.0) if base else 0.0
        pct_txt = "%+.2f%%" % pct
        pw = self.font_pct.measure(pct_txt) + self.s(12)
        ph = self.s(14)
        px2 = w - self.PAD
        px1 = px2 - pw
        py1 = mid - ph / 2.0
        col = GREEN if day >= 0 else RED
        bg = GREEN_DIM if day >= 0 else RED_DIM
        self._round_rect(px1, py1, px2, py1 + ph, ph // 2, fill=bg,
                         tags=("pf",))
        c.create_text((px1 + px2) / 2.0, mid, text=pct_txt, fill=col,
                      font=("Segoe UI", 7, "bold"), tags=("pf",))
        c.create_text(px1 - self.s(8), mid, text=fmt_money(val, cur),
                      anchor="e", fill=FG, font=(self.mono, 8, "bold"),
                      tags=("pf",))

    def _update_portfolio(self):
        if getattr(self, "_pf_y", None) is None:
            return
        try:
            self.canvas.delete("pf")
            self._draw_portfolio(self._pf_y)
        except tk.TclError:
            pass

    # ---------- geometry helpers ----------

    def s(self, v):
        return int(round(v * self.S))

    def _round_rect(self, x1, y1, x2, y2, r, fill=None, outline=None,
                    tags=None):
        round_rect(self.canvas, x1, y1, x2, y2, r, fill, outline, tags)

    def _row_y(self, index):
        return self.HEADER_H + index * self.ROW_H

    def _row_height(self):
        n = len(self.cfg["symbols"])
        extra = self.s(26) if self._has_portfolio() else 0
        return (self.HEADER_H + n * self.ROW_H + self.s(30) + extra)

    # ---------- UI ----------

    def build_ui(self):
        c = self.canvas
        c.delete("all")
        self.items = {}
        self.row_bounds = []
        W, H = self.W, self._row_height()
        self._round_rect(0, 0, W - 1, H - 1, self.s(14), fill=CARD,
                         outline=DIVIDER)
        c.create_text(self.PAD, self.s(17), text="TAKİP LİSTESİ",
                      anchor="w", fill=MUTED, font=self.f_title)
        self.close_id = c.create_text(W - self.PAD, self.s(9), text="✕",
                                      anchor="ne", fill=DIM,
                                      font=("Segoe UI", 9),
                                      tags=("close_btn",))
        time_x = W - self.PAD - self.s(17)
        dot_x = time_x - self.s(30)
        self.dot_id = c.create_oval(dot_x, self.s(14),
                                    dot_x + self.s(5), self.s(19),
                                    fill=MUTED, outline="")
        self.time_id = c.create_text(time_x, self.s(17), text="--:--",
                                     anchor="e", fill=MUTED,
                                     font=self.f_foot)
        for i, sym in enumerate(self.cfg["symbols"]):
            y = self._row_y(i)
            if i:
                c.create_line(self.PAD, y, W - self.PAD, y, fill=DIVIDER)
            c.create_rectangle(self.s(6), y + self.ro(2),
                               W - self.s(6), y + self.ROW_H - self.ro(2),
                               fill="", outline="", tags=("hover",))
            c.create_text(self.PAD, y + self.ro(9), text=sym, anchor="nw",
                          fill=FG, font=self.f_sym)
            price_id = c.create_text(W - self.PAD, y + self.ro(9), text="—",
                                     anchor="ne", fill=DIM,
                                     font=self.f_price)
            self.items[sym] = {"price": price_id, "y": y,
                               "tag": "dyn_%d" % i}
            self.row_bounds.append((y, y + self.ROW_H))
        fy = self._row_y(len(self.cfg["symbols"]))
        c.create_line(self.PAD, fy, W - self.PAD, fy, fill=DIVIDER)
        self._pf_y = None
        if self._has_portfolio():
            self._pf_y = fy + self.s(4)
            self._draw_portfolio(self._pf_y)
            fy2 = self._pf_y + self.s(22)
            c.create_line(self.PAD, fy2, W - self.PAD, fy2, fill=DIVIDER)
            foot_y = fy2 + self.s(15)
        else:
            foot_y = fy + self.s(15)
        c.create_text(self.PAD, foot_y, text="Yahoo Finance",
                      anchor="w", fill=DIM, font=self.f_foot)
        self.upd_id = c.create_text(W - self.PAD, foot_y,
                                    text="yükleniyor…", anchor="e",
                                    fill=DIM, font=self.f_foot)
        for sym, info in self.last.items():
            if sym in self.items:
                self._render_row(sym, info)
        self._update_status()
        if self._detail is not None and self._detail.symbol not in self.cfg["symbols"]:
            self.close_detail()

    def _restore_position(self):
        sm = ctypes.windll.user32.GetSystemMetrics
        sw, sh = sm(0), sm(1)
        W, H = self.W, self._row_height()
        x = self.cfg.get("x", sw - W - self.s(24))
        y = self.cfg.get("y", sh - H - self.s(60))
        x = max(-40, min(x, sw - self.s(80)))
        y = max(0, min(y, sh - self.s(40)))
        self.root.geometry("%dx%d+%d+%d" % (W, H, x, y))

    def _render_row(self, sym, info):
        c = self.canvas
        it = self.items.get(sym)
        if not it:
            return
        c.delete(it["tag"])
        y = it["y"]
        pct = info["change_pct"]
        up = pct >= 0
        col = GREEN if up else RED
        bg = GREEN_DIM if up else RED_DIM
        price_txt = fmt_money(info["price"], info.get("currency"))
        c.itemconfig(it["price"], text=price_txt,
                     fill=MUTED if self.offline else FG)
        # değişim rozeti (trend oklu)
        txt = ("▲ " if up else "▼ ") + "%+.2f%%" % pct
        tw = self.font_pct.measure(txt)
        ph = self.ro(17)
        pw = tw + self.s(14)
        x2 = self.W - self.PAD
        x1 = x2 - pw
        y1 = y + self.ro(26)
        self._round_rect(x1, y1, x2, y1 + ph, ph // 2, fill=bg)
        c.create_text((x1 + x2) / 2.0, y1 + ph / 2.0, text=txt, fill=col,
                      font=self.f_pct, tags=(it["tag"],))
        # şirket adı (sparkline ile rozet arasında)
        name = info.get("name") or ""
        nx = self.PAD + self.s(78)
        avail = x1 - nx - self.s(6)
        if name and avail > self.s(14):
            txtname = self._ellipsize(name, self.font_name, avail)
            if txtname:
                c.create_text(nx, y1 + ph / 2.0, text=txtname, anchor="w",
                              fill=DIM, font=self.f_name,
                              tags=(it["tag"],))
        # sparkline (PIL ile anti-aliased)
        spark = info.get("spark") or []
        sw, sh = self.s(72), self.ro(16)
        if len(spark) > 1:
            sx1, sy1 = self.PAD, y + self.ro(25)
            if PIL_AVAILABLE:
                img = render_spark(spark, sw, sh, col, fill=col)
                photo = ImageTk.PhotoImage(img, master=self.root)
                self._row_photos[sym] = photo
                c.create_image(sx1, sy1, image=photo, anchor="nw",
                               tags=(it["tag"],))
            else:
                lo, hi = min(spark), max(spark)
                rng = (hi - lo) or 1.0
                pts = []
                n = len(spark)
                for i, v in enumerate(spark):
                    pts.extend((sx1 + sw * i / float(n - 1),
                                sy1 + sh - (v - lo) / rng * sh))
                c.create_line(*pts, fill=col,
                              width=max(1, int(round(1.4 * self.S))),
                              tags=(it["tag"],))
                c.create_oval(pts[-2] - self.s(2), pts[-1] - self.s(2),
                              pts[-2] + self.s(2), pts[-1] + self.s(2),
                              fill=col, outline="", tags=(it["tag"],))
        else:
            # veri gelene kadar iskelet çizgi
            c.create_line(self.PAD, y + self.ro(32), self.PAD + sw,
                          y + self.ro(32), fill=DIVIDER, width=1,
                          tags=(it["tag"],))

    def _update_status(self):
        c = self.canvas
        if self.offline:
            dot = AMBER
        elif market_open():
            dot = GREEN
        else:
            dot = DIM
        try:
            c.itemconfig(self.dot_id, fill=dot)
            c.itemconfig(self.time_id, text=datetime.datetime.now().strftime("%H:%M"))
            c.itemconfig(self.upd_id, text=(
                "çevrimdışı · deneniyor…" if self.offline
                else "son güncelleme %s" % self._rel_time()))
        except (tk.TclError, AttributeError):
            pass

    def apply_data(self, results, offline):
        self.offline = offline
        if results:
            self._data_ts = time.time()
        for sym, info in results.items():
            self.last[sym] = info
            self._render_row(sym, info)
        if offline:
            # Çevrimdışıyken başarısız satırların fiyatını da soluklaştır
            for sym, info in self.last.items():
                if sym not in results:
                    self._render_row(sym, info)
        self._update_status()
        self._update_portfolio()
        if self._detail is not None:
            self._detail.render()

    # ---------- interaction ----------

    def _press(self, event):
        self._px = event.x_root
        self._py = event.y_root
        self._moved = False
        self._dx = self.root.winfo_pointerx() - self.root.winfo_rootx()
        self._dy = self.root.winfo_pointery() - self.root.winfo_rooty()

    def _drag(self, event):
        if abs(event.x_root - self._px) > 3 or abs(event.y_root - self._py) > 3:
            self._moved = True
        x = self.root.winfo_pointerx() - self._dx
        y = self.root.winfo_pointery() - self._dy
        try:
            sm = ctypes.windll.user32.GetSystemMetrics
            sw, sh = sm(0), sm(1)
            x = max(-40, min(x, sw - self.s(80)))
            y = max(0, min(y, sh - self.s(40)))
        except Exception:
            pass
        self.root.geometry("+%d+%d" % (x, y))
        if self._detail is not None:
            self._detail.reposition()

    def _release(self, event):
        self.cfg["x"] = self.root.winfo_x()
        self.cfg["y"] = self.root.winfo_y()
        save_config(self.cfg)
        if not self._moved:
            idx = self._row_index_at(event.y)
            if idx is not None:
                self.open_detail(self.cfg["symbols"][idx])

    def _row_index_at(self, y):
        for i, (y1, y2) in enumerate(self.row_bounds):
            if y1 <= y < y2:
                return i
        return None

    def _on_motion(self, event):
        idx = self._row_index_at(event.y)
        self.canvas.config(cursor="hand2" if idx is not None else "")
        if idx == self._hover_row:
            return
        self._hover_row = idx
        hover_ids = self.canvas.find_withtag("hover")
        for i, hid in enumerate(hover_ids):
            self.canvas.itemconfig(hid, fill=HOVER if i == idx else "")

    def _on_leave(self, event):
        self._hover_row = None
        self.canvas.config(cursor="")
        for hid in self.canvas.find_withtag("hover"):
            self.canvas.itemconfig(hid, fill="")

    def _on_double_click(self, event):
        if event.y < self.HEADER_H or event.y > self._row_height() - self.s(24):
            self.open_symbol_editor()

    def _popup_menu(self, event):
        try:
            self._refresh_remove_menu()
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.menu.grab_release()
            except tk.TclError:
                pass

    def _refresh_remove_menu(self):
        self.remove_menu.delete(0, "end")
        if not self.cfg["symbols"]:
            self.remove_menu.add_command(label="(boş)", state="disabled")
        for sym in list(self.cfg["symbols"]):
            self.remove_menu.add_command(
                label=sym, command=lambda s=sym: self.remove_symbol(s))

    def refresh_now(self):
        self.wake.set()

    # ---------- detail panel ----------

    def open_detail(self, sym):
        if sym not in self.cfg["symbols"]:
            return
        if self._detail is not None and self._detail.symbol == sym:
            self.close_detail()
            return
        if self._detail is not None:
            self._detail.close()
        self._detail = DetailPanel(self, sym)

    def close_detail(self):
        if self._detail is not None:
            self._detail.close()

    def toggle_startup(self):
        set_startup(self.startup_var.get())
        if self.tray_icon:
            try:
                self.tray_icon.update_menu()
            except Exception:
                pass

    # ---------- symbol editor ----------

    def open_symbol_editor(self):
        if self._editor is not None and self._editor.winfo_exists():
            self._editor.deiconify()
            self._editor.lift()
            self._editor.focus_set()
            return self._editor
        s = self.s
        dlg = tk.Toplevel(self.root)
        self._editor = dlg
        dlg.configure(bg=CARD)
        dlg.attributes("-topmost", True)
        dlg.title("Semboller")
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        try:
            dlg.iconbitmap(ICON_FILE)
        except tk.TclError:
            pass
        dark_title_bar(dlg)

        tk.Label(dlg, text="TAKİP LİSTESİ", bg=CARD, fg=MUTED,
                 font=self.f_title).pack(fill="x", padx=s(14), pady=(s(12), s(4)))
        listf = tk.Frame(dlg, bg=CARD)
        listf.pack(fill="both", expand=True, padx=s(14))

        status = tk.Label(dlg, text="Ticker yazıp Enter'a bas.",
                          bg=CARD, fg=DIM, font=self.f_foot,
                          wraplength=s(250), justify="left", anchor="w")
        status.pack(fill="x", padx=s(14), pady=(s(6), s(2)))

        entry_row = tk.Frame(dlg, bg=CARD)
        entry_row.pack(fill="x", padx=s(14), pady=(s(2), s(2)))
        entry = tk.Entry(entry_row, bg=RAISED, fg=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 10),
                         highlightthickness=1, highlightbackground=ENTRY_BORDER,
                         highlightcolor=ACCENT, width=10)
        entry.pack(side="left", fill="x", expand=True, ipady=s(4), ipadx=s(6))

        def fit():
            dlg.update_idletasks()
            dlg.geometry("%dx%d" % (s(300), dlg.winfo_reqheight()))

        def rebuild_list():
            for w in listf.winfo_children():
                w.destroy()
            if not self.cfg["symbols"]:
                tk.Label(listf, text="(liste boş)", bg=CARD, fg=MUTED,
                         font=self.f_foot).pack(anchor="w")
            for sym in list(self.cfg["symbols"]):
                r = tk.Frame(listf, bg=CARD)
                r.pack(fill="x", pady=1)
                tk.Label(r, text=sym, bg=CARD, fg=FG, font=self.f_sym,
                         width=10, anchor="w").pack(side="left")
                tk.Button(r, text="✕", bg=CARD, fg=DIM, bd=0,
                          activebackground=RED_DIM, activeforeground=RED,
                          font=("Segoe UI", 9), cursor="hand2",
                          command=lambda sn=sym: do_remove(sn)
                          ).pack(side="right", padx=s(2))

        def do_remove(sym):
            if sym in self.cfg["symbols"]:
                self.cfg["symbols"].remove(sym)
                save_config(self.cfg)
                self.last.pop(sym, None)
                self.build_ui()
                self._restore_position()
                rebuild_list()
                status.config(text="%s kaldırıldı." % sym, fg=MUTED)
                fit()
                self.refresh_now()

        def do_add(event=None):
            sym = entry.get().strip().upper()
            if not sym:
                return
            if sym in self.cfg["symbols"]:
                status.config(text="%s zaten listede." % sym, fg=AMBER)
                return
            # Doğrulama ağ isteği ana thread'i dondurmasın: ayrı thread'de çalışır,
            # sonuç root.after ile ana thread'e döner.
            add_btn.config(state="disabled")
            entry.config(state="disabled")
            status.config(text="%s doğrulanıyor…" % sym, fg=MUTED)

            def on_done(ok, message):
                if not ok:
                    if dlg.winfo_exists():
                        add_btn.config(state="normal")
                        entry.config(state="normal")
                        status.config(text=message, fg=RED)
                    return
                self.cfg["symbols"].append(sym)
                save_config(self.cfg)
                self.build_ui()
                self._restore_position()
                self.refresh_now()
                if dlg.winfo_exists():
                    add_btn.config(state="normal")
                    entry.config(state="normal")
                    rebuild_list()
                    entry.delete(0, "end")
                    status.config(text=message, fg=GREEN)
                    fit()

            def worker():
                try:
                    fetch_quote(sym)
                    ok, message = True, "%s eklendi." % sym
                except Exception:
                    ok, message = False, "%s bulunamadı ya da bağlantı hatası." % sym
                try:
                    self.root.after(0, on_done, ok, message)
                except tk.TclError:
                    pass  # uygulama kapanmış olabilir

            threading.Thread(target=worker, daemon=True).start()

        entry.bind("<Return>", do_add)
        add_btn = tk.Button(entry_row, text="Ekle", bg=ACCENT, fg="#ffffff",
                            bd=0, activebackground=ACCENT_HOVER,
                            activeforeground="#ffffff",
                            font=("Segoe UI", 9, "bold"), cursor="hand2",
                            command=do_add)
        add_btn.pack(side="left", padx=(s(6), 0), ipadx=s(10), ipady=s(4))
        tk.Button(dlg, text="Kapat", bg=BTN, fg=FG, bd=0,
                  activebackground=BTN_HOVER, activeforeground=FG,
                  font=("Segoe UI", 9), cursor="hand2",
                  command=dlg.destroy).pack(fill="x", padx=s(14),
                                            pady=(s(6), s(14)), ipady=s(3))

        sm = ctypes.windll.user32.GetSystemMetrics
        sw, sh = sm(0), sm(1)
        rebuild_list()
        fit()
        h = dlg.winfo_reqheight()
        w = s(300)
        dlg.geometry("%dx%d+%d+%d" % (w, h, sw // 2 - w // 2, sh // 2 - h // 2))
        entry.focus_set()
        return dlg

    def remove_symbol(self, sym):
        if sym in self.cfg["symbols"]:
            self.cfg["symbols"].remove(sym)
            save_config(self.cfg)
            self.last.pop(sym, None)
            self.build_ui()
            self._restore_position()

    # ---------- portfolio editor ----------

    def open_portfolio_editor(self):
        dlg = getattr(self, "_portfolio_dlg", None)
        if dlg is not None and dlg.winfo_exists():
            dlg.deiconify()
            dlg.lift()
            dlg.focus_set()
            return dlg
        s = self.s
        dlg = tk.Toplevel(self.root)
        self._portfolio_dlg = dlg
        dlg.configure(bg=CARD)
        dlg.attributes("-topmost", True)
        dlg.title("Portföy")
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        try:
            dlg.iconbitmap(ICON_FILE)
        except tk.TclError:
            pass
        dark_title_bar(dlg)

        tk.Label(dlg, text="PORTFÖY", bg=CARD, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=s(18), pady=(s(14), 0))
        tk.Label(dlg, text="Adet ve ortalama maliyet gir; boş satır pozisyonu kaldırır.",
                 bg=CARD, fg=DIM, font=self.f_foot).pack(
            anchor="w", padx=s(18), pady=(s(2), s(10)))
        tk.Frame(dlg, bg=DIVIDER, height=1).pack(fill="x", padx=s(18))

        listf = tk.Frame(dlg, bg=CARD)
        listf.pack(fill="x", padx=s(14), pady=(s(10), 0))

        positions = self.cfg.get("positions") or {}
        cur = next((v.get("currency") for v in self.last.values()
                    if v.get("currency")), None) or "USD"
        rows = {}

        def mk_entry(parent):
            e = tk.Entry(parent, bg=CARD, fg=FG, insertbackground=FG,
                         relief="flat", width=7, font=(self.mono, 9),
                         justify="right", highlightthickness=1,
                         highlightbackground=ENTRY_BORDER,
                         highlightcolor=ACCENT)
            e.bind("<KeyRelease>", lambda ev: recalc())
            return e

        for sym in list(self.cfg["symbols"]):
            p = positions.get(sym) or {}
            card = tk.Frame(listf, bg=RAISED, highlightthickness=1,
                            highlightbackground=DIVIDER)
            card.pack(fill="x", pady=(0, s(8)))
            inner = tk.Frame(card, bg=RAISED)
            inner.pack(fill="x", padx=s(10), pady=s(9))

            top = tk.Frame(inner, bg=RAISED)
            top.pack(fill="x")
            tk.Label(top, text=sym, bg=RAISED, fg=FG,
                     font=self.f_sym).pack(side="left")
            clear = tk.Button(top, text="✕", bg=RAISED, fg=DIM, bd=0,
                              activebackground=RED_DIM, activeforeground=RED,
                              font=("Segoe UI", 8), cursor="hand2")
            clear.pack(side="right", padx=(s(6), 0))
            value_lbl = tk.Label(top, text="—", bg=RAISED, fg=FG,
                                 font=(self.mono, 8, "bold"))
            value_lbl.pack(side="right")

            mid = tk.Frame(inner, bg=RAISED)
            mid.pack(fill="x", pady=(s(6), 0))
            tk.Label(mid, text="Adet", bg=RAISED, fg=DIM,
                     font=self.f_foot).pack(side="left", padx=(0, s(2)))
            qty = mk_entry(mid)
            qty.insert(0, str(p.get("qty") or ""))
            qty.pack(side="left", padx=(s(4), s(14)), ipady=s(2))
            tk.Label(mid, text="Ortalama", bg=RAISED, fg=DIM,
                     font=self.f_foot).pack(side="left", padx=(0, s(2)))
            avg = mk_entry(mid)
            avg.insert(0, str(p.get("avg") or ""))
            avg.pack(side="left", padx=(s(4), 0), ipady=s(2))

            pnl_lbl = tk.Label(inner, text="", bg=RAISED, fg=DIM,
                               font=("Segoe UI", 6), anchor="w")
            pnl_lbl.pack(fill="x", pady=(s(4), 0))
            rows[sym] = {"qty": qty, "avg": avg, "value": value_lbl,
                         "pnl": pnl_lbl}
            clear.config(command=lambda q=qty, a=avg: (
                q.delete(0, "end"), a.delete(0, "end"), recalc()))

        tk.Frame(dlg, bg=DIVIDER, height=1).pack(fill="x", padx=s(18),
                                                 pady=(s(10), s(6)))
        tot = tk.Frame(dlg, bg=CARD)
        tot.pack(fill="x", padx=s(18))
        tk.Label(tot, text="Toplam değer", bg=CARD, fg=MUTED,
                 font=self.f_foot).pack(side="left")
        total_val = tk.Label(tot, text="—", bg=CARD, fg=FG,
                             font=(self.mono, 10, "bold"))
        total_val.pack(side="right")
        total_pnl = tk.Label(tot, text="", bg=CARD, fg=DIM,
                             font=("Segoe UI", 7, "bold"))
        total_pnl.pack(side="right", padx=(0, s(10)))

        status = tk.Label(dlg, text="", bg=CARD, fg=DIM, font=self.f_foot,
                          anchor="w")
        status.pack(fill="x", padx=s(18), pady=(s(4), 0))
        tk.Label(dlg, text="Değer ve K/Z son bilinen fiyatlara göre hesaplanır.",
                 bg=CARD, fg=DIM, font=("Segoe UI", 6)).pack(
            anchor="w", padx=s(18), pady=(0, s(4)))

        def recalc(event=None):
            tv = tc = tp = 0.0
            invalid = False
            for sym, r in rows.items():
                try:
                    q = float((r["qty"].get() or "0").replace(",", "."))
                    a = float((r["avg"].get() or "0").replace(",", "."))
                except ValueError:
                    r["value"].config(text="—", fg=RED)
                    r["pnl"].config(text="geçersiz sayı", fg=RED)
                    invalid = True
                    continue
                info = self.last.get(sym) or {}
                price = float(info.get("price") or a or 0)
                if q > 0:
                    value = q * price
                    cost = q * a
                    pnl = value - cost
                    r["value"].config(text=fmt_money(value, cur), fg=FG)
                    pct = (pnl / cost * 100.0) if cost else 0.0
                    r["pnl"].config(
                        text="Maliyet %s · K/Z %+.2f%%"
                             % (fmt_money(cost, cur), pct),
                        fg=GREEN if pnl >= 0 else RED)
                    tv += value
                    tc += cost
                    tp += pnl
                else:
                    r["value"].config(text="—", fg=DIM)
                    r["pnl"].config(text="", fg=DIM)
            total_val.config(text=fmt_money(tv, cur) if tv else "—")
            if tc:
                total_pnl.config(text="%+.2f%%" % (tp / tc * 100.0),
                                 fg=GREEN if tp >= 0 else RED)
            else:
                total_pnl.config(text="")
            status.config(text="Geçersiz sayı var." if invalid else "",
                          fg=RED if invalid else DIM)

        def save():
            out = {}
            for sym, r in rows.items():
                try:
                    q = float((r["qty"].get() or "0").replace(",", "."))
                    a = float((r["avg"].get() or "0").replace(",", "."))
                except ValueError:
                    status.config(text="%s: geçersiz sayı." % sym, fg=RED)
                    return
                if q > 0:
                    out[sym] = {"qty": q, "avg": a}
            self.cfg["positions"] = out
            save_config(self.cfg)
            self.build_ui()
            self._restore_position()
            recalc()
            status.config(text="Portföy kaydedildi.", fg=GREEN)

        btns = tk.Frame(dlg, bg=CARD)
        btns.pack(fill="x", padx=s(14), pady=(s(8), s(14)))
        tk.Button(btns, text="Kaydet", bg=ACCENT, fg="#ffffff", bd=0,
                  activebackground=ACCENT_HOVER, activeforeground="#ffffff",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  command=save).pack(side="left", fill="x", expand=True,
                                     ipady=s(4))
        tk.Button(btns, text="Kapat", bg=BTN, fg=FG, bd=0,
                  activebackground=BTN_HOVER, activeforeground=FG,
                  font=("Segoe UI", 9), cursor="hand2",
                  command=dlg.destroy).pack(side="left", fill="x", expand=True,
                                            padx=(s(6), 0), ipady=s(4))

        recalc()
        sm = ctypes.windll.user32.GetSystemMetrics
        sw_, sh_ = sm(0), sm(1)
        dlg.update_idletasks()
        w, h = s(340), dlg.winfo_reqheight()
        dlg.geometry("%dx%d+%d+%d" % (w, h, sw_ // 2 - w // 2,
                                      sh_ // 2 - h // 2))
        return dlg

    # ---------- data loop ----------

    def _set_hotkey_hint(self, ok):
        self.hotkey_ok = ok
        try:
            self.menu.entryconfig(
                self.hotkey_idx,
                label=("Kısayol: Ctrl+Alt+S – göster/gizle" if ok else
                       "Kısayol: Ctrl+Alt+S kaydedilemedi"))
        except tk.TclError:
            pass

    def poll_queue(self):
        try:
            try:
                while True:
                    event = self.hotkey_queue.get_nowait()
                    if event == "toggle":
                        self.toggle_visibility()
                    elif event == "quit":
                        # --quit: tepsi/başlat menüsünden gelen temiz kapanış
                        self.exit_app()
                        return
                    elif event == "registered":
                        self._set_hotkey_hint(True)
                    elif event == "unavailable":
                        self._set_hotkey_hint(False)
            except queue.Empty:
                pass
            try:
                results, offline = self.queue.get_nowait()
            except queue.Empty:
                results, offline = None, None
            if results is not None:
                self.apply_data(results, offline)
        except Exception:
            # Bir istisna kuyruk döngüsünü kalıcı olarak durdurmasın
            log.exception("poll_queue hatası")
        finally:
            if not self.stop_flag.is_set():
                try:
                    self.root.after(200, self.poll_queue)
                except tk.TclError:
                    pass

    def fetch_loop(self):
        while not self.stop_flag.is_set():
            symbols = list(self.cfg["symbols"])
            if not symbols:
                # Boş liste: sadece bekle, çevrimdışı sayma
                self.queue.put(({}, False))
                self.wake.wait(INTERVAL_CLOSED)
                self.wake.clear()
                continue
            results = {}
            failures = 0
            for i, sym in enumerate(symbols):
                if self.stop_flag.is_set():
                    return
                if i:
                    time.sleep(0.4)
                try:
                    results[sym] = fetch_quote(sym)
                except requests.exceptions.HTTPError as exc:
                    if exc.response is not None and exc.response.status_code == 429:
                        time.sleep(THROTTLE_429)
                    failures += 1
                except Exception:
                    failures += 1
            if failures:
                log.warning("fetch: %d/%d sembol başarısız",
                            failures, len(symbols))
            interval = INTERVAL_CLOSED if not market_open() else INTERVAL_OPEN
            offline = failures == len(symbols) and not results
            if failures and not results:
                interval = INTERVAL_RETRY
                if self.last_ok is not None:
                    offline = True
            if results:
                self.last_ok = True
                offline = False
            self.queue.put((results, offline))
            self.wake.wait(interval)
            self.wake.clear()

    # ---------- tray ----------

    def _tray_image(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([2, 2, 62, 62], radius=14, fill=(20, 22, 27, 255))
        for x, top, bot, col in ((16, 26, 46, (61, 220, 132, 255)),
                                 (30, 18, 40, (61, 220, 132, 255)),
                                 (44, 22, 48, (255, 90, 95, 255))):
            d.line([x, top - 5, x, bot + 5], fill=col, width=2)
            d.rounded_rectangle([x - 4, top, x + 4, bot], radius=2, fill=col)
        return img

    def _create_tray_icon(self):
        # pystray menü callback'leri tray thread'inde çalışır; Tk'ye dokunmamaları
        # için hepsi root.after ile ana thread'e taşınır (bkz. AGENT.md "Tk tek thread").
        menu = pystray.Menu(
            pystray.MenuItem(
                "Göster / Gizle",
                lambda *a: self.root.after(0, self.toggle_visibility),
                default=True),
            pystray.MenuItem("Yenile", lambda *a: self.refresh_now()),
            pystray.MenuItem(
                "Semboller…",
                lambda *a: self.root.after(0, self.open_symbol_editor)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Windows'ta otomatik başlat",
                lambda *a: self.root.after(0, self._tray_toggle_startup),
                checked=lambda item: startup_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Çıkış",
                             lambda *a: self.root.after(0, self.exit_app)),
        )
        return pystray.Icon("StockWidget", self._tray_image(),
                            "%s %s" % (APP_NAME, APP_VERSION), menu)

    def _tray_toggle_startup(self):
        set_startup(not startup_enabled())
        self.startup_var.set(startup_enabled())
        if self.tray_icon:
            try:
                self.tray_icon.update_menu()
            except Exception:
                pass

    def _setup_tray(self):
        if not (TRAY_AVAILABLE and PIL_AVAILABLE):
            return
        self.tray_icon = self._create_tray_icon()
        threading.Thread(target=self._tray_run, daemon=True).start()

    def _tray_run(self):
        # Tepsi simgesi bazı oturumlarda (uzak masaüstü/servis) engellenebilir;
        # bu durumda widget penceresi çalışmaya devam etmeli.
        try:
            self.tray_icon.run()
        except Exception:
            log.exception("tepsi simgesi başlatılamadı")

    def toggle_visibility(self, icon=None, item=None):
        if self.root.winfo_viewable():
            self.hide_window()
        else:
            self.root.deiconify()
            self.root.lift()

    def hide_window(self):
        self.close_detail()
        self.root.withdraw()

    # ---------- lifecycle ----------

    def exit_app(self):
        log.info("çıkış")
        self.cfg["x"] = self.root.winfo_x()
        self.cfg["y"] = self.root.winfo_y()
        save_config(self.cfg)
        self.close_detail()
        self.stop_flag.set()
        self.wake.set()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def main():
    setup_logging()
    if "--version" in sys.argv:
        try:
            print("%s %s" % (APP_NAME, APP_VERSION))
        except Exception:
            pass
        return
    if "--paths" in sys.argv:
        # Destek/hata ayıklama: hangi ayar ve log dosyası kullanılıyor?
        try:
            print(CONFIG_FILE)
            print(LOG_FILE)
        except Exception:
            pass
        return
    if "--quit" in sys.argv:
        # Kurulum/kaldırma ve kısayol: çalışan kopyayı kapat. Kopya yoksa
        # uygulamayı başlatmadan sessizce çık.
        request_quit()
        return
    mutex = acquire_single_instance()
    if mutex is None:
        # Kurulu sürümde masaüstü kısayolu --toggle ile gelir.
        if "--toggle" in sys.argv:
            request_toggle()
        else:
            log.info("ikinci kopya, çıkılıyor")
        return
    migrate_legacy_config()
    log.info("başladı (pid %s)", os.getpid())
    toggle_event = create_signal_event(TOGGLE_EVENT)
    quit_event = create_signal_event(QUIT_EVENT)
    app = StockWidget()
    if toggle_event or quit_event:
        threading.Thread(
            target=signal_watch_loop,
            args=([(toggle_event, "toggle"), (quit_event, "quit")],
                  app.hotkey_queue, app.stop_flag),
            daemon=True).start()
    app.root.mainloop()


if __name__ == "__main__":
    main()
