import os
import sys
import json
import time
import queue
import ctypes
import ctypes.wintypes
import datetime
import calendar
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
APP_VERSION = "1.1.0"
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
           "{s}?interval=5m")


def quote_url(symbol, include_prepost=True, et=None):
    """Yahoo grafik URL'i: son/aktif işlem gününün 04:00–20:00 ET penceresi.

    `range=1d` piyasa öncesi saatlerde önceki seansa düşebiliyor; bu yüzden
    pencere açıkça `period1`/`period2` ile verilir. Ek istek yapılmaz.
    """
    url = API_URL.format(s=symbol)
    start, end = session_epoch_range(et)
    url += "&period1=%d&period2=%d" % (start, end)
    if include_prepost:
        url += "&includePrePost=true"
    return url
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

# Ayarlar penceresi: yenileme aralığı seçenekleri (dakika)
REFRESH_OPEN_OPTIONS = (5, 15, 30)
REFRESH_CLOSED_OPTIONS = (15, 60, 120)
PAUSE_POLL = 60          # duraklatılmışken yalnızca saat kontrolü aralığı (s)

SETTINGS_DEFAULTS = {
    "theme": "gece",
    "opacity": 0.97,
    "density": "normal",
    "always_on_top": True,
    "refresh_open": 15,
    "refresh_closed": 60,
    "pause_when_closed": False,
    "extended_hours": True,
    "close_to_tray": True,
}

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


def market_phase(et=None):
    """ABD borsası seansı: 'pre', 'regular', 'post' ya da None (kapalı)."""
    et = et or et_now()
    if et.weekday() >= 5:
        return None
    if datetime.date(et.year, et.month, et.day) in market_holidays(et.year):
        return None
    t = et.hour * 60 + et.minute
    if 4 * 60 <= t < 9 * 60 + 30:          # 04:00–09:30 ET öncesi seans
        return "pre"
    if 9 * 60 + 30 <= t < 16 * 60:         # 09:30–16:00 ET normal seans
        return "regular"
    if 16 * 60 <= t < 20 * 60:             # 16:00–20:00 ET sonrası seans
        return "post"
    return None


def market_open():
    """Normal seans açık mı?"""
    return market_phase() == "regular"


def market_active():
    """Herhangi bir seans (öncesi/normal/sonrası) açık mı?"""
    return market_phase() is not None


# Seans dışı etiketleri: piyasa öncesi / piyasa sonrası
SESSION_LABEL = {"pre": "PÖ", "post": "PS"}


def bar_session(ts):
    """Bir 5 dk barının ET saatine göre seansı: 'pre', 'post' ya da None.

    Tatil/hafta sonu ayrımı yapılmaz: amaç barın hangi seansa ait olduğunu
    bilmek. Hafta sonu son bar Cuma 19:55 ise veri hâlâ seans sonrasıdır.
    """
    if ts is None:
        return None
    utc = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    utc = utc.replace(tzinfo=None)
    et = utc + datetime.timedelta(hours=_et_offset_hours(utc.date()))
    t = et.hour * 60 + et.minute
    if 4 * 60 <= t < 9 * 60 + 30:
        return "pre"
    if 16 * 60 <= t < 20 * 60 + 5:
        return "post"
    return None


def _et_offset_hours(day):
    """Verilen gün için ET'nin UTC'ye göre farkı (-4 yaz, -5 kış)."""
    year = day.year
    mar1 = datetime.datetime(year, 3, 1)
    first_sun_mar = 1 + (6 - mar1.weekday()) % 7
    dst_start = datetime.datetime(year, 3, first_sun_mar + 7, 7, 0)
    nov1 = datetime.datetime(year, 11, 1)
    first_sun_nov = 1 + (6 - nov1.weekday()) % 7
    dst_end = datetime.datetime(year, 11, first_sun_nov, 6, 0)
    probe = datetime.datetime(day.year, day.month, day.day, 12, 0)
    return -4 if dst_start <= probe < dst_end else -5


def trading_day(et=None):
    """1G grafiğin ait olduğu işlem günü (04:00 ET öncesi önceki güne düşer)."""
    et = et or et_now()
    day = et.date()
    if et.hour * 60 + et.minute < 4 * 60:
        day -= datetime.timedelta(days=1)
    for _ in range(14):
        if day.weekday() < 5 and day not in market_holidays(day.year):
            break
        day -= datetime.timedelta(days=1)
    return day


def session_epoch_range(et=None):
    """Aktif/son işlem gününün 04:00–20:00 ET aralığını epoch'a çevirir."""
    et = et or et_now()
    day = trading_day(et)
    offset = _et_offset_hours(day)

    def epoch(hour, minute=0):
        wall = datetime.datetime(day.year, day.month, day.day, hour, minute)
        return calendar.timegm(wall.timetuple()) - offset * 3600

    return epoch(4), epoch(20, 5)


def _cfg_bool(cfg, key, default):
    """config.json'daki gevşek yazılmış doğru/yanlış değerlerini normalize eder."""
    value = cfg.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "on", "evet", "acik", "açık"):
            return True
        if text in ("0", "false", "no", "off", "hayir", "hayır", "kapali",
                    "kapalı"):
            return False
    return default


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
    cfg["always_on_top"] = _cfg_bool(cfg, "always_on_top", True)
    cfg["close_to_tray"] = _cfg_bool(cfg, "close_to_tray", True)
    cfg["pause_when_closed"] = _cfg_bool(cfg, "pause_when_closed", False)
    cfg["extended_hours"] = _cfg_bool(cfg, "extended_hours", True)
    for key, default in (("refresh_open", 15), ("refresh_closed", 60)):
        try:
            minutes = int(cfg.get(key, default))
        except (TypeError, ValueError):
            minutes = default
        cfg[key] = min(1440, max(1, minutes))
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


def fetch_quote(symbol, include_prepost=True):
    url = quote_url(symbol, include_prepost)
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

    # Seans dışı (piyasa öncesi/sonrası) fiyat: grafiği besleyen son bar.
    # Böylece kart ve detaydaki fiyat, grafiğin bittiği noktayla birebir aynı
    # olur; piyasa kapandıktan sonra da "kapanışta takılı" görünmez.
    ext_session = None
    ext_price = ext_pct = ext_abs = None
    if include_prepost and rows:
        ext_session = bar_session(rows[-1][0])
        if ext_session:
            ext_price = float(rows[-1][1])
            ext_pct = (ext_price / float(prev) - 1.0) * 100.0
            ext_abs = ext_price - float(prev)
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
        "ext_session": ext_session,
        "ext_price": ext_price,
        "ext_change_pct": ext_pct,
        "ext_change_abs": ext_abs,
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


# ---- kısa geçiş animasyonları ----
ANIM_MS = 130            # panel açılışı / sekme kayması
ANIM_CLOSE_MS = 90       # panel kapanışı
ANIM_HOVER_MS = 90       # satır vurgusu
ANIM_FRAME_MS = 16       # ~60 fps
ANIM_SLIDE = 10          # açılışta yukarı kayma (ölçeklenmemiş piksel)


def anim_enabled():
    """Windows'ta 'animasyonları göster' kapalıysa False döner."""
    try:
        value = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            0x1042, 0, ctypes.byref(value), 0)   # SPI_GETCLIENTAREAANIMATION
        return bool(ok and value.value)
    except Exception:
        return True


def ease_out(t):
    """0→1 arası hızlı başlayıp yavaşlayan yumuşatma."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return 1.0 - (1.0 - t) ** 3


def blend_color(src, dst, t):
    """İki renk arasında `t` (0→1) oranında geçiş yapar."""
    a, b = _hex_rgb(src), _hex_rgb(dst)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return "#%02x%02x%02x" % tuple(
        int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def run_anim(widget, ms, apply_fn, done=None, alive=None):
    """`apply_fn(p)` çağrısını 0→1 arası karelerle yapar (p yumuşatılmış).

    Widget yok edilirse ya da `alive()` False dönerse sessizce durur.
    Animasyon kapalıysa tek karede son duruma atlar.
    """
    if ms <= 0 or not anim_enabled():
        try:
            apply_fn(1.0)
            if done:
                done()
        except tk.TclError:
            pass
        return

    frames = max(4, int(round(ms / float(ANIM_FRAME_MS))))
    state = {"n": 0}

    def tick():
        if alive is not None and not alive():
            return
        state["n"] += 1
        p = ease_out(min(1.0, state["n"] / float(frames)))
        try:
            apply_fn(p)
            if state["n"] < frames:
                widget.after(ANIM_FRAME_MS, tick)
            elif done:
                done()
        except tk.TclError:
            return

    tick()


def fade(win, start, end, ms, done=None, alive=None):
    """Pencere opaklığını `start`tan `end`e kaydırır."""
    run_anim(win, ms,
             lambda p: win.attributes("-alpha", start + (end - start) * p),
             done=done, alive=alive)


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
        # Esc ile paneli kapat: hem panelde hem ana kartta çalışsın
        self.win.bind("<Escape>", self._on_escape)
        self._esc_id = app.root.bind("<Escape>", self._on_escape, add="+")
        self._dx = 0
        self._dy = 0
        self._plot = None
        self._hover_idx = None
        self._tab_geo = []
        self._tab_y = (0, 0)
        self._target_alpha = getattr(app, "alpha", 0.97)
        self._base_xy = None
        self._closing = False

        self.reposition()
        self.render()
        app.root.after(150, self._poll_results)
        self._animate_open()

    # ---------- animations ----------

    def _animate_open(self):
        """Panel kısa bir kayma + solma ile açılır."""
        if not anim_enabled() or self._base_xy is None:
            return
        bx, by = self._base_xy
        slide = self.s(ANIM_SLIDE)
        try:
            self.win.attributes("-alpha", 0.0)
        except tk.TclError:
            return

        def apply(p):
            self.win.attributes("-alpha", self._target_alpha * p)
            self.win.geometry("+%d+%d" % (bx, int(round(by + slide * (1 - p)))))

        def finish():
            try:
                self.win.geometry("+%d+%d" % (bx, by))
                self.win.attributes("-alpha", self._target_alpha)
            except tk.TclError:
                pass

        run_anim(self.win, ANIM_MS, apply, done=finish,
                 alive=lambda: not self._closed)

    # ---------- timeframe ----------

    def set_tf(self, tf):
        if self._closed:
            return
        old = self.tf
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
        self._animate_pill(old)

    def _animate_pill(self, old_tf):
        """Etkin sekme vurgusu eski sekmeden yenisine kayar."""
        if old_tf == self.tf or not anim_enabled() or not self._tab_geo:
            return
        try:
            old_i = TF_TABS.index(old_tf)
            new_i = TF_TABS.index(self.tf)
        except ValueError:
            return
        pill = self.canvas.find_withtag("tabpill")
        if not pill:
            return
        ox1, ox2 = self._tab_geo[old_i]
        nx1, nx2 = self._tab_geo[new_i]
        y1, y2 = self._tab_y

        def apply(p):
            self.canvas.coords(pill[0], ox1 + (nx1 - ox1) * p, y1,
                               ox2 + (nx2 - ox2) * p, y2)

        run_anim(self.win, ANIM_MS, apply, alive=lambda: not self._closed)

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
        self._base_xy = (x, y)
        self.win.geometry("%dx%d+%d+%d" % (W, H, x, y))

    def _on_escape(self, event=None):
        self.close()
        return "break"

    def _destroy(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def close(self, animate=True):
        if self._closed:
            return
        self._closed = True
        if self.app._detail is self:
            self.app._detail = None
        try:
            self.app.root.unbind("<Escape>", self._esc_id)
        except (tk.TclError, AttributeError):
            pass
        if animate and anim_enabled() and self._base_xy is not None:
            bx, by = self._base_xy
            slide = self.s(ANIM_SLIDE) // 2
            start = self._target_alpha

            def apply(p):
                self.win.attributes("-alpha", start * (1.0 - p))
                self.win.geometry("+%d+%d"
                                 % (bx, int(round(by - slide * p))))

            # `_closed` True olduğu için alive kontrolü ayrı: pencere yaşıyor mu?
            run_anim(self.win, ANIM_CLOSE_MS, apply, done=self._destroy,
                     alive=lambda: bool(self.win.winfo_exists()))
        else:
            self._destroy()

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
        geo = []
        for i, tf in enumerate(TF_TABS):
            x1 = pad + i * (w + gap)
            x2 = x1 + w
            geo.append((x1, x2))
            c.create_rectangle(x1, y1, x2, y2, fill=CARD, outline="",
                               tags=("tfb_" + tf,))
        self._tab_geo = geo
        self._tab_y = (y1, y2)
        # Etkin sekme vurgusu ayrı bir katman: sekme değişince kaydırılabilir
        try:
            idx = TF_TABS.index(self.tf)
        except ValueError:
            idx = 0
        if geo:
            ax1, ax2 = geo[idx]
            c.create_rectangle(ax1, y1, ax2, y2, fill=TRACK, outline="",
                               tags=("tabpill",))
        for i, tf in enumerate(TF_TABS):
            x1, x2 = geo[i]
            active = tf == self.tf
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
        ext = (info.get("ext_session")
               if self.app.cfg.get("extended_hours", True) else None)
        ext_price, ext_pct = info.get("ext_price"), info.get("ext_change_pct")
        use_ext = (ext in ("pre", "post") and ext_price is not None
                   and ext_pct is not None)
        # Seans dışında büyük fiyat/rozet canlı seans dışı değeri gösterir
        disp_price = ext_price if use_ext else price
        disp_pct = ext_pct if use_ext else pct
        up = (disp_pct or 0) >= 0
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

        c.create_text(pad, s(70), text=fmt_money(disp_price, cur), anchor="w",
                      fill=FG, font=(self.app.mono, 19, "bold"))
        if disp_pct is not None:
            pct_txt = ("▲ " if up else "▼ ") + "%+.2f%%" % disp_pct
            if use_ext:
                pct_txt = "%s %s" % (SESSION_LABEL.get(ext, ""), pct_txt)
            pw = self.app.font_pct.measure(pct_txt) + s(16)
            ph = s(19)
            py1 = s(61)
            round_rect(c, x2 - pw, py1, x2, py1 + ph, ph // 2, fill=bg)
            c.create_text(x2 - pw / 2.0, py1 + ph / 2.0, text=pct_txt,
                          fill=col, font=("Segoe UI", 8, "bold"))
        change = info.get("change_abs")
        if use_ext and pct is not None:
            # Seans dışı: son normal seans kapanışı ve değişimi
            line = "son kapanış %s (%+.2f%%)" % (fmt_money(price, cur), pct)
        elif change is not None:
            line = "bugün %+.2f" % change
        else:
            line = None
        if line:
            c.create_text(pad, s(95), text=line,
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
            if stamps:
                last = stamps[-1]
                right_lbl = datetime.datetime.fromtimestamp(last).strftime(
                    "%H:%M")
                if time.time() - last < 600:
                    right_lbl = "şimdi"
            else:
                right_lbl = "—"
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
        self.root.attributes("-topmost", bool(self.cfg["always_on_top"]))
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
        self._force_refresh = False
        self._tray_ok = bool(TRAY_AVAILABLE and PIL_AVAILABLE)
        self._settings_dlg = None
        self._settings_last_lbl = None
        self._settings_hotkey_lbl = None
        self._settings_status_lbl = None
        self._settings_pending = None
        self._settings_scroll = (0.0, 1.0)

        self.hotkey_ok = None
        self.hotkey_queue = queue.Queue()
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
                             lambda e: self.root.after(10, self.close_window))
        self.canvas.tag_bind("refresh_btn", "<Enter>",
                             lambda e: self._set_refresh_color(ACCENT))
        self.canvas.tag_bind("refresh_btn", "<Leave>",
                             lambda e: self._set_refresh_color(DIM))
        self.canvas.tag_bind("refresh_btn", "<Button-1>",
                             lambda e: self.root.after(
                                 10, self._header_refresh))
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)

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
        m.add_command(label="Ayarlar…", command=self.open_settings_editor)
        m.add_separator()
        m.add_command(label="Sembol ekle / çıkar…",
                      command=self.open_symbol_editor)
        m.add_command(label="Portföy…", command=self.open_portfolio_editor)
        self.remove_menu = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=FG,
                                   activebackground=MENU_ACTIVE)
        m.add_cascade(label="Hızlı çıkar", menu=self.remove_menu)
        m.add_separator()
        m.add_command(label="Yenile", command=self.refresh_now)
        m.add_separator()
        m.add_command(label="Gizle", command=self.hide_window)
        m.add_command(label="Çıkış", command=self.exit_app)

    def _style_menus(self):
        for mm in (getattr(self, "menu", None), self.remove_menu):
            if mm is None:
                continue
            try:
                mm.configure(bg=MENU_BG, fg=FG,
                             activebackground=MENU_ACTIVE,
                             activeforeground=FG)
            except tk.TclError:
                pass

    def set_theme(self, key):
        if key not in PALETTES or key == self.cfg.get("theme"):
            return
        apply_palette(key)
        self.cfg["theme"] = key
        save_config(self.cfg)
        self._style_menus()
        self.build_ui()
        self._restore_position()
        if self._detail is not None:
            self._detail.render()
        self._refresh_settings()

    def _apply_opacity(self, val):
        self.alpha = min(1.0, max(0.6, float(val)))
        try:
            self.root.attributes("-alpha", self.alpha)
        except tk.TclError:
            pass
        if self._detail is not None:
            try:
                self._detail.win.attributes("-alpha", self.alpha)
            except tk.TclError:
                pass

    def set_opacity(self, val):
        self._apply_opacity(val)
        self.cfg["opacity"] = self.alpha
        save_config(self.cfg)

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
        self._refresh_settings()

    def set_always_on_top(self, value):
        self.cfg["always_on_top"] = bool(value)
        save_config(self.cfg)
        try:
            self.root.attributes("-topmost", bool(value))
        except tk.TclError:
            pass

    def set_pause_when_closed(self, value):
        self.cfg["pause_when_closed"] = bool(value)
        save_config(self.cfg)
        self.wake.set()

    def set_close_to_tray(self, value):
        self.cfg["close_to_tray"] = bool(value)
        save_config(self.cfg)

    def set_extended_hours(self, value):
        self.cfg["extended_hours"] = bool(value)
        save_config(self.cfg)
        self.wake.set()
        # Veri kaynağı değişti: satırları hemen tazele
        self.refresh_now()

    def _status_tick(self):
        try:
            self._update_status()
            self._sync_settings_time()
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

    def _set_refresh_color(self, color):
        try:
            self.canvas.itemconfig("refresh_btn", fill=color)
        except tk.TclError:
            pass

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
        self.close_id = c.create_text(W - self.PAD - self.s(3), self.s(16),
                                      text="✕", anchor="center", fill=DIM,
                                      font=("Segoe UI", 9),
                                      tags=("close_btn",))
        self.refresh_id = c.create_text(W - self.PAD - self.s(21), self.s(16),
                                        text="⟳", anchor="center", fill=MUTED,
                                        font=("Segoe UI Symbol", 11),
                                        tags=("refresh_btn",))
        time_x = W - self.PAD - self.s(34)
        dot_x = time_x - self.s(30)
        self.dot_id = c.create_oval(dot_x, self.s(14),
                                    dot_x + self.s(5), self.s(19),
                                    fill=MUTED, outline="")
        self.phase_id = c.create_text(dot_x - self.s(5), self.s(17), text="",
                                      anchor="e", fill=AMBER,
                                      font=("Segoe UI", 6, "bold"))
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
        spark_col = col
        price_val = info["price"]
        # Seans dışı (piyasa öncesi/sonrası) veri varsa onu göster
        ext = (info.get("ext_session")
               if self.cfg.get("extended_hours", True) else None)
        ext_pct = info.get("ext_change_pct")
        if ext and info.get("ext_price") is not None and ext_pct is not None:
            price_val = info["ext_price"]
            pct = ext_pct
            up = pct >= 0
            col = GREEN if up else RED
            bg = GREEN_DIM if up else RED_DIM
            label = SESSION_LABEL.get(ext, "")
            txt = "%s %s %+.2f%%" % (label, "▲" if up else "▼", pct)
        else:
            txt = ("▲ " if up else "▼ ") + "%+.2f%%" % pct
        price_txt = fmt_money(price_val, info.get("currency"))
        c.itemconfig(it["price"], text=price_txt,
                     fill=MUTED if self.offline else FG)
        # değişim rozeti (trend oklu)
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
                img = render_spark(spark, sw, sh, spark_col, fill=spark_col)
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
                c.create_line(*pts, fill=spark_col,
                              width=max(1, int(round(1.4 * self.S))),
                              tags=(it["tag"],))
                c.create_oval(pts[-2] - self.s(2), pts[-1] - self.s(2),
                              pts[-2] + self.s(2), pts[-1] + self.s(2),
                              fill=spark_col, outline="", tags=(it["tag"],))
        else:
            # veri gelene kadar iskelet çizgi
            c.create_line(self.PAD, y + self.ro(32), self.PAD + sw,
                          y + self.ro(32), fill=DIVIDER, width=1,
                          tags=(it["tag"],))

    def _update_status(self):
        c = self.canvas
        phase = market_phase()
        if phase is None:
            # Seans kapalıyken de son veri seans dışından geliyorsa PÖ/PS yaz
            for sym in self.cfg.get("symbols") or []:
                info = self.last.get(sym) or {}
                if info.get("ext_session") in SESSION_LABEL:
                    phase = info["ext_session"]
                    break
        if self.offline:
            dot = AMBER
        elif phase == "regular":
            dot = GREEN
        elif phase in ("pre", "post"):
            dot = AMBER
        else:
            dot = DIM
        try:
            c.itemconfig(self.dot_id, fill=dot)
            c.itemconfig(self.phase_id, text=(
                SESSION_LABEL.get(phase, "")
                if self.cfg.get("extended_hours", True) else ""))
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
        self._hover_gen = getattr(self, "_hover_gen", 0) + 1
        gen = self._hover_gen
        hover_ids = self.canvas.find_withtag("hover")
        for i, hid in enumerate(hover_ids):
            if i == idx:
                self._fade_item(hid, HOVER, gen)
            else:
                self.canvas.itemconfig(hid, fill="")

    def _fade_item(self, item_id, target, gen):
        """Satır vurgusunu kısa bir renk geçişiyle açar."""
        if not anim_enabled():
            self.canvas.itemconfig(item_id, fill=target)
            return

        def apply(p):
            self.canvas.itemconfig(item_id,
                                   fill=blend_color(CARD, target, p))

        run_anim(self.canvas, ANIM_HOVER_MS, apply,
                 alive=lambda: gen == self._hover_gen)

    def _on_leave(self, event):
        self._hover_row = None
        self._hover_gen = getattr(self, "_hover_gen", 0) + 1
        self.canvas.config(cursor="")
        for hid in self.canvas.find_withtag("hover"):
            self.canvas.itemconfig(hid, fill="")

    def _on_double_click(self, event):
        current = self.canvas.find_withtag("current")
        tags = self.canvas.gettags(current[0]) if current else ()
        if "refresh_btn" in tags or "close_btn" in tags:
            return
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
        self._force_refresh = True
        self.wake.set()

    def _header_refresh(self):
        """Kart başlığındaki yenile simgesi: yeniler ve kısa süre vurgular."""
        self.refresh_now()
        self._set_refresh_color(ACCENT)
        try:
            self.root.after(900, self._refresh_icon_idle)
        except tk.TclError:
            pass

    def _refresh_icon_idle(self):
        self._set_refresh_color(DIM)

    # ---------- detail panel ----------

    def open_detail(self, sym):
        if sym not in self.cfg["symbols"]:
            return
        if self._detail is not None and self._detail.symbol == sym:
            self.close_detail()
            return
        if self._detail is not None:
            # Yerine yeni panel açılıyor: eskiyi animasyonsuz kapat
            self._detail.close(animate=False)
        self._detail = DetailPanel(self, sym)

    def close_detail(self, animate=True):
        if self._detail is not None:
            self._detail.close(animate=animate)

    def apply_startup(self, value):
        set_startup(bool(value))
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

        positions = self.cfg.get("positions") or {}
        symbols = list(self.cfg["symbols"])
        cur = next((v.get("currency") for v in self.last.values()
                    if v.get("currency")), None) or "USD"
        rows = {}

        def shade(widget, color):
            """Satır vurgusu: hücre ve içindeki parçaların zeminini boyar."""
            try:
                widget.configure(bg=color)
            except tk.TclError:
                pass
            for child in widget.winfo_children():
                shade(child, color)

        def highlight(rowinfo):
            if not dlg.winfo_exists():
                return
            for w in rowinfo["cells"]:
                shade(w, HOVER)

        def clear_unfocused(rowinfo):
            if not dlg.winfo_exists():
                return
            try:
                focus = dlg.focus_get()
            except tk.TclError:
                return
            if focus in rowinfo["cells"]:
                return
            for w in rowinfo["cells"]:
                shade(w, RAISED)

        # ---- başlık ----
        head = tk.Frame(dlg, bg=CARD)
        head.pack(fill="x", padx=s(18), pady=(s(14), 0))
        tk.Label(head, text="Portföy", bg=CARD, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(head, text=cur, bg=RAISED, fg=MUTED,
                 font=("Segoe UI", 6, "bold")).pack(
            side="left", padx=(s(8), 0), ipadx=s(4), ipady=s(1))
        tk.Label(dlg, text="Adet ve ortalama maliyet gir; boş satır siler.",
                 bg=CARD, fg=DIM, font=self.f_foot).pack(
            anchor="w", padx=s(18), pady=(s(2), s(10)))

        # ---- özet şeridi ----
        summary = tk.Frame(dlg, bg=RAISED, highlightthickness=1,
                           highlightbackground=DIVIDER)
        summary.pack(fill="x", padx=s(18))
        tk.Frame(summary, bg=ACCENT, width=max(2, s(3))).pack(
            side="left", fill="y")
        statsf = tk.Frame(summary, bg=RAISED)
        statsf.pack(side="left", fill="both", expand=True)
        stats = {}
        for idx, (key, label) in enumerate((("value", "TOPLAM DEĞER"),
                                            ("cost", "MALİYET"),
                                            ("pnl", "K/Z"))):
            statsf.grid_columnconfigure(idx, weight=1)
            cell = tk.Frame(statsf, bg=RAISED)
            cell.grid(row=0, column=idx, sticky="nsew",
                      padx=(s(12), s(6)), pady=(s(8), s(9)))
            tk.Label(cell, text=label, bg=RAISED, fg=DIM,
                     font=("Segoe UI", 6, "bold")).pack(anchor="w")
            big = tk.Label(cell, text="—", bg=RAISED, fg=FG,
                           font=(self.mono, 11, "bold"))
            big.pack(anchor="w")
            sub = tk.Label(cell, text="", bg=RAISED, fg=DIM,
                           font=("Segoe UI", 6))
            sub.pack(anchor="w")
            stats[key] = (big, sub)

        # ---- tablo ----
        body = tk.Frame(dlg, bg=CARD)
        body.pack(fill="x", padx=s(18), pady=(s(12), 0))
        left = tk.Frame(body, bg=CARD)
        left.pack(side="left", fill="both", expand=True)

        MINS = {0: s(58), 1: s(60), 2: s(74), 3: s(84), 4: s(62), 5: s(20)}
        PADS = {0: (s(10), 0), 1: (s(2), 0), 2: (s(2), 0),
                3: (s(6), s(6)), 4: (0, s(6)), 5: (0, 0)}

        header = tk.Frame(left, bg=CARD)
        header.pack(fill="x", pady=(0, s(4)))
        for col in range(6):
            header.grid_columnconfigure(
                col, minsize=MINS[col], weight=1 if col == 3 else 0)
        for col, text, anchor in ((0, "SEMBOL", "w"), (1, "ADET", "e"),
                                  (2, "ORTALAMA", "e"), (3, "DEĞER", "e"),
                                  (4, "K/Z", "e")):
            tk.Label(header, text=text, bg=CARD, fg=DIM,
                     font=("Segoe UI", 6, "bold"), anchor=anchor).grid(
                row=0, column=col, sticky="ew", padx=PADS[col])

        canvas = tk.Canvas(left, bg=CARD, highlightthickness=0, bd=0)
        canvas.pack(fill="x")
        vs = tk.Scrollbar(body, orient="vertical", command=canvas.yview,
                          width=s(9), bg=CARD, troughcolor=CARD, bd=0,
                          relief="flat", activebackground=BTN,
                          highlightthickness=0)
        canvas.configure(yscrollcommand=vs.set)

        table = tk.Frame(canvas, bg=RAISED, highlightthickness=1,
                         highlightbackground=DIVIDER)
        win_id = canvas.create_window((0, 0), window=table, anchor="nw")
        for col in range(6):
            table.grid_columnconfigure(
                col, minsize=MINS[col], weight=1 if col == 3 else 0)
        table.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
            win_id, width=e.width))

        def mk_entry(parent, rowinfo):
            e = tk.Entry(parent, bg=RAISED, fg=FG, insertbackground=FG,
                         relief="flat", width=4, font=(self.mono, 9),
                         justify="right", highlightthickness=1,
                         highlightbackground=ENTRY_BORDER,
                         highlightcolor=ACCENT)
            e.bind("<KeyRelease>", lambda ev: recalc())
            e.bind("<FocusIn>", lambda ev: (e.select_range(0, "end"),
                                            highlight(rowinfo)))
            e.bind("<FocusOut>", lambda ev: dlg.after_idle(
                lambda: clear_unfocused(rowinfo)))
            return e

        for idx, sym in enumerate(symbols):
            p = positions.get(sym) or {}
            rowinfo = {"cells": []}
            r = idx * 2

            c0 = tk.Frame(table, bg=RAISED)
            c0.grid(row=r, column=0, sticky="nsew",
                    padx=(s(10), 0), pady=s(6))
            sym_lbl = tk.Label(c0, text=sym, bg=RAISED, fg=FG,
                               font=self.f_sym, anchor="w")
            sym_lbl.pack(fill="x")

            c1 = tk.Frame(table, bg=RAISED)
            c1.grid(row=r, column=1, sticky="nsew",
                    padx=(s(2), 0), pady=s(4))
            qty = mk_entry(c1, rowinfo)
            qty.insert(0, str(p.get("qty") or ""))
            qty.pack(fill="x", ipady=s(3))

            c2 = tk.Frame(table, bg=RAISED)
            c2.grid(row=r, column=2, sticky="nsew",
                    padx=(s(2), 0), pady=s(4))
            avg = mk_entry(c2, rowinfo)
            avg.insert(0, str(p.get("avg") or ""))
            avg.pack(fill="x", ipady=s(3))

            c3 = tk.Frame(table, bg=RAISED)
            c3.grid(row=r, column=3, sticky="nsew",
                    padx=(s(6), s(6)), pady=s(6))
            val_lbl = tk.Label(c3, text="—", bg=RAISED, fg=FG,
                               font=(self.mono, 8, "bold"), anchor="e")
            val_lbl.pack(fill="x")

            c4 = tk.Frame(table, bg=RAISED)
            c4.grid(row=r, column=4, sticky="nsew",
                    padx=(0, s(6)), pady=s(6))
            pnl_lbl = tk.Label(c4, text="", bg=RAISED, fg=DIM,
                               font=("Segoe UI", 7, "bold"), anchor="e")
            pnl_lbl.pack(fill="x")

            c5 = tk.Frame(table, bg=RAISED)
            c5.grid(row=r, column=5, sticky="nsew", pady=s(4))
            clear = tk.Button(c5, text="✕", bg=RAISED, fg=DIM, bd=0,
                              activebackground=RED_DIM,
                              activeforeground=RED,
                              font=("Segoe UI", 8), cursor="hand2",
                              command=lambda q=qty, a=avg: (
                                  q.delete(0, "end"),
                                  a.delete(0, "end"), recalc()))
            clear.pack()

            rowinfo["cells"] = [c0, sym_lbl, c1, qty, c2, avg, c3, val_lbl,
                                c4, pnl_lbl, c5, clear]
            rows[sym] = {"qty": qty, "avg": avg, "value": val_lbl,
                         "pnl": pnl_lbl}
            for w in rowinfo["cells"]:
                w.bind("<Enter>", lambda ev, rr=rowinfo: highlight(rr),
                       add="+")
                w.bind("<Leave>", lambda ev, rr=rowinfo: dlg.after(
                    30, lambda rr=rr: clear_unfocused(rr)), add="+")

            if idx < len(symbols) - 1:
                tk.Frame(table, bg=DIVIDER, height=1).grid(
                    row=r + 1, column=0, columnspan=6, sticky="ew")

        if not symbols:
            tk.Label(table, text="Takip listesi boş.\n"
                                 "Sağ tık → Sembol ekle ile başla.",
                     bg=RAISED, fg=DIM, font=self.f_foot,
                     justify="center").grid(
                row=0, column=0, columnspan=6, pady=s(24))

        # ---- hesaplama ve kaydetme ----
        def parse_num(widget):
            txt = (widget.get() or "").strip().replace(",", ".")
            if not txt:
                return 0.0
            try:
                return float(txt)
            except ValueError:
                return None

        def recalc(event=None):
            tv = tc = pnl_sum = tc_priced = 0.0
            have_price = False
            bad = None
            for sym, r in rows.items():
                q = parse_num(r["qty"])
                a = parse_num(r["avg"])
                r["qty"].config(highlightbackground=(
                    ENTRY_BORDER if q is not None else RED))
                r["avg"].config(highlightbackground=(
                    ENTRY_BORDER if a is not None else RED))
                if q is None or a is None:
                    bad = sym
                    r["value"].config(text="—", fg=DIM)
                    r["pnl"].config(text="geçersiz", fg=RED)
                    continue
                if q <= 0:
                    r["value"].config(text="—", fg=DIM)
                    r["pnl"].config(text="", fg=DIM)
                    continue
                info = self.last.get(sym) or {}
                price = info.get("price")
                cost = q * a
                tc += cost
                if price:
                    value = q * float(price)
                    have_price = True
                    tc_priced += cost
                    pnl_sum += value - cost
                    r["value"].config(text=fmt_money(value, cur), fg=FG)
                    if a > 0:
                        r["pnl"].config(
                            text="%+.2f%%" % ((value - cost) / cost * 100.0),
                            fg=GREEN if value >= cost else RED)
                    else:
                        r["pnl"].config(text="maliyet yok", fg=AMBER)
                else:
                    value = cost
                    r["value"].config(text=fmt_money(value, cur), fg=DIM)
                    r["pnl"].config(text="veri yok", fg=DIM)
                tv += value
            stats["value"][0].config(
                text=fmt_money(tv, cur) if tv else "—",
                fg=FG if have_price else MUTED)
            stats["cost"][0].config(text=fmt_money(tc, cur) if tc else "—")
            if tc_priced:
                pct = pnl_sum / tc_priced * 100.0
                stats["pnl"][0].config(text="%+.2f%%" % pct,
                                       fg=GREEN if pnl_sum >= 0 else RED)
                pnl_sign = "+" if pnl_sum >= 0 else ""
                stats["pnl"][1].config(
                    text=pnl_sign + fmt_money(pnl_sum, cur), fg=DIM)
            else:
                stats["pnl"][0].config(text="—", fg=DIM)
                stats["pnl"][1].config(text="")
            if bad:
                status.config(text="%s: geçersiz sayı." % bad, fg=RED)
            else:
                status.config(text="Değişiklikler Kaydet ile uygulanır.",
                              fg=DIM)

        def save():
            out = {}
            for sym, r in rows.items():
                q = parse_num(r["qty"])
                a = parse_num(r["avg"])
                if q is None or a is None:
                    recalc()
                    (r["qty"] if q is None else r["avg"]).focus_set()
                    status.config(text="%s: geçersiz sayı." % sym, fg=RED)
                    return
                if q > 0:
                    out[sym] = {"qty": q, "avg": a}
            self.cfg["positions"] = out
            save_config(self.cfg)
            self.build_ui()
            self._restore_position()
            recalc()
            if out:
                status.config(text="Kaydedildi · %d pozisyon" % len(out),
                              fg=GREEN)
            else:
                status.config(text="Portföy boş.", fg=DIM)

        # ---- alt bar ----
        tk.Frame(dlg, bg=DIVIDER, height=1).pack(fill="x", padx=s(18),
                                                 pady=(s(12), 0))
        status = tk.Label(dlg, text="", bg=CARD, fg=DIM, font=self.f_foot,
                          anchor="w")
        status.pack(fill="x", padx=s(18), pady=(s(6), 0))
        footer = tk.Frame(dlg, bg=CARD)
        footer.pack(fill="x", padx=s(18), pady=(s(6), s(14)))
        tk.Button(footer, text="Kaydet", bg=ACCENT, fg="#ffffff", bd=0,
                  activebackground=ACCENT_HOVER, activeforeground="#ffffff",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  command=save).pack(side="right", ipadx=s(26), ipady=s(5))
        tk.Button(footer, text="Kapat", bg=BTN, fg=FG, bd=0,
                  activebackground=BTN_HOVER, activeforeground=FG,
                  font=("Segoe UI", 9), cursor="hand2",
                  command=dlg.destroy).pack(side="right", padx=(0, s(6)),
                                            ipadx=s(16), ipady=s(5))

        # ---- yerleşim ----
        dlg.update_idletasks()
        rows_h = table.winfo_reqheight()
        cap = s(280)
        canvas.configure(height=min(rows_h, cap))
        if rows_h > cap:
            vs.pack(side="right", fill="y", padx=(s(4), 0))

        dlg.bind("<MouseWheel>", lambda ev: canvas.yview_scroll(
            -1 if ev.delta > 0 else 1, "units") if rows_h > cap else None)
        dlg.bind("<Escape>", lambda ev: dlg.destroy())
        dlg.bind("<Return>", lambda ev: save())
        dlg.bind("<Control-s>", lambda ev: (save(), "break")[1])
        dlg.bind("<Destroy>", lambda ev: (
            setattr(self, "_portfolio_dlg", None)
            if ev.widget is dlg else None))

        recalc()
        sm = ctypes.windll.user32.GetSystemMetrics
        sw_, sh_ = sm(0), sm(1)
        dlg.update_idletasks()
        w, h = s(452), dlg.winfo_reqheight()
        dlg.geometry("%dx%d+%d+%d" % (w, h, sw_ // 2 - w // 2,
                                      sh_ // 2 - h // 2))
        return dlg

    # ---------- settings ----------

    def open_settings_editor(self):
        dlg = self._settings_dlg
        if dlg is not None and dlg.winfo_exists():
            dlg.deiconify()
            dlg.lift()
            dlg.focus_set()
            return dlg
        dlg = tk.Toplevel(self.root)
        self._settings_dlg = dlg
        self._settings_pending = None
        dlg.configure(bg=CARD)
        dlg.attributes("-topmost", True)
        dlg.title("Ayarlar")
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        try:
            dlg.iconbitmap(ICON_FILE)
        except tk.TclError:
            pass
        dark_title_bar(dlg)
        dlg.bind("<Escape>", lambda ev: dlg.destroy())
        dlg.bind("<Destroy>",
                 lambda ev: self._settings_destroyed(ev, dlg))
        self._build_settings(dlg, center=True)
        return dlg

    def _settings_destroyed(self, event, dlg):
        if event.widget is not dlg:
            return
        self._settings_dlg = None
        self._settings_last_lbl = None
        self._settings_hotkey_lbl = None
        self._settings_status_lbl = None
        self._settings_pending = None

    def _refresh_settings(self):
        """Tema gibi renkleri değiştiren işlemlerden sonra pencereyi kur."""
        dlg = self._settings_dlg
        if dlg is None:
            return
        try:
            if dlg.winfo_exists():
                dlg.after_idle(lambda: self._rebuild_settings(dlg))
        except tk.TclError:
            pass

    def _rebuild_settings(self, dlg):
        try:
            if dlg.winfo_exists():
                self._build_settings(dlg, center=False)
        except tk.TclError:
            pass

    def _settings_note(self, text, color=None):
        self._settings_pending = (text, color or DIM)
        lbl = self._settings_status_lbl
        if lbl is None:
            return
        try:
            if lbl.winfo_exists():
                lbl.config(text=text, fg=color or DIM)
        except tk.TclError:
            pass

    def _sync_settings_time(self):
        lbl = self._settings_last_lbl
        if lbl is None:
            return
        try:
            if lbl.winfo_exists():
                lbl.config(text=self._rel_time())
        except tk.TclError:
            pass

    def _pick_theme(self, key):
        if key == self.cfg.get("theme"):
            return
        self.set_theme(key)
        self._settings_note("Tema: %s." % THEME_LABEL.get(key, key))

    def _pick_density(self, key):
        if key == self.cfg.get("density"):
            return
        self.set_density(key)
        self._settings_note("Yoğunluk: %s."
                            % ("Normal" if key == "normal" else "Kompakt"))

    def _pick_always_on_top(self, value):
        self.set_always_on_top(value)
        self._settings_note("Her zaman üstte %s."
                            % ("açık" if value else "kapalı"))

    def _pick_pause_when_closed(self, value):
        self.set_pause_when_closed(value)
        self._settings_note("Piyasa kapalıyken yenileme %s."
                            % ("duruyor" if value else "sürüyor"))

    def _pick_extended_hours(self, value):
        self.set_extended_hours(value)
        self._settings_note("Piyasa öncesi/sonrası veri %s."
                            % ("gösteriliyor" if value else "kapalı"))

    def _pick_close_to_tray(self, value):
        self.set_close_to_tray(value)
        self._settings_note("✕ %s."
                            % ("tepsiye gizler" if value else "uygulamayı "
                               "kapatır"))

    def _pick_startup(self, value):
        self.apply_startup(value)
        actual = startup_enabled()
        if actual != bool(value):
            self._settings_note("Otomatik başlatma değiştirilemedi.", RED)
        else:
            self._settings_note("Otomatik başlatma %s."
                                % ("açık" if actual else "kapalı"))

    def _pick_reset_position(self):
        self.reset_position()
        self._settings_note("Konum sıfırlandı.", GREEN)

    def _settings_refresh_now(self):
        self.refresh_now()
        lbl = self._settings_last_lbl
        if lbl is not None:
            try:
                lbl.config(text="yenileniyor…")
            except tk.TclError:
                pass

    def set_refresh(self, key, minutes):
        if key not in ("refresh_open", "refresh_closed"):
            return
        self.cfg[key] = int(minutes)
        save_config(self.cfg)
        self.wake.set()
        self._refresh_settings()
        label = ("Piyasa açıkken" if key == "refresh_open"
                 else "Piyasa kapalıyken")
        self._settings_note("%s yenileme: %d dk." % (label, int(minutes)))

    def reset_position(self):
        sm = ctypes.windll.user32.GetSystemMetrics
        sw_, sh_ = sm(0), sm(1)
        W, H = self.W, self._row_height()
        self.cfg["x"] = sw_ - W - self.s(24)
        self.cfg["y"] = sh_ - H - self.s(60)
        save_config(self.cfg)
        self._restore_position()

    def reset_settings(self):
        for key, value in SETTINGS_DEFAULTS.items():
            self.cfg[key] = value
        save_config(self.cfg)
        apply_palette(self.cfg["theme"])
        self.density = self.cfg["density"]
        self._set_density()
        self._apply_opacity(self.cfg["opacity"])
        self.cfg["opacity"] = self.alpha
        try:
            self.root.attributes("-topmost", self.cfg["always_on_top"])
        except tk.TclError:
            pass
        self._style_menus()
        self.build_ui()
        self._restore_position()
        if self._detail is not None:
            self._detail.render()
        self.wake.set()
        self._settings_note("Ayarlar varsayılana döndü.", GREEN)
        self._refresh_settings()

    def _open_data_dir(self):
        try:
            os.startfile(DATA_DIR)
        except OSError:
            log.exception("ayar klasörü açılamadı")
            self._settings_note("Klasör açılamadı.", RED)

    def _build_settings(self, dlg, center):
        s = self.s
        if center:
            self._settings_scroll = (0.0, 1.0)
        dlg.configure(bg=CARD)
        for child in dlg.winfo_children():
            child.destroy()
        self._settings_last_lbl = None
        self._settings_hotkey_lbl = None
        self._settings_status_lbl = None

        # ---- başlık ----
        head = tk.Frame(dlg, bg=CARD)
        head.pack(fill="x", padx=s(18), pady=(s(14), 0))
        tk.Label(head, text="Ayarlar", bg=CARD, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(head, text=APP_VERSION, bg=RAISED, fg=MUTED,
                 font=("Segoe UI", 6, "bold")).pack(
            side="left", padx=(s(8), 0), ipadx=s(4), ipady=s(1))
        tk.Label(dlg, text="Değişiklikler anında uygulanır.",
                 bg=CARD, fg=DIM, font=self.f_foot).pack(
            anchor="w", padx=s(18), pady=(s(2), s(6)))

        # ---- kaydırılabilir gövde ----
        holder = tk.Frame(dlg, bg=CARD)
        holder.pack(fill="both", expand=True, padx=s(18))
        canvas = tk.Canvas(holder, bg=CARD, highlightthickness=0, bd=0)
        canvas.pack(side="left", fill="both", expand=True)
        vs = tk.Scrollbar(holder, orient="vertical", command=canvas.yview,
                          width=s(9), bg=CARD, troughcolor=CARD, bd=0,
                          relief="flat", activebackground=BTN,
                          highlightthickness=0)
        body = tk.Frame(canvas, bg=CARD)
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
            win_id, width=e.width))

        body.grid_columnconfigure(0, weight=1, uniform="col")
        body.grid_columnconfigure(1, weight=1, uniform="col")
        left_col = tk.Frame(body, bg=CARD)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, s(5)))
        right_col = tk.Frame(body, bg=CARD)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(s(5), 0))

        # ---- ortak parçalar ----
        def section(parent, title):
            tk.Label(parent, text=title, bg=CARD, fg=DIM,
                     font=("Segoe UI", 6, "bold"), anchor="w").pack(
                fill="x", padx=s(2), pady=(s(10), s(3)))
            card = tk.Frame(parent, bg=RAISED, highlightthickness=1,
                            highlightbackground=DIVIDER)
            card.pack(fill="x")
            return card

        def add_row(card, title, hint=None, last=False):
            row = tk.Frame(card, bg=RAISED)
            row.pack(fill="x")
            left = tk.Frame(row, bg=RAISED)
            left.pack(side="left", padx=(s(11), s(4)), pady=s(6))
            tk.Label(left, text=title, bg=RAISED, fg=FG,
                     font=("Segoe UI", 9), anchor="w").pack(anchor="w")
            hint_lbl = None
            if hint:
                hint_lbl = tk.Label(left, text=hint, bg=RAISED, fg=DIM,
                                    font=("Segoe UI", 7), anchor="w",
                                    justify="left")
                hint_lbl.pack(anchor="w", pady=(s(1), 0))
            if not last:
                tk.Frame(card, bg=DIVIDER, height=1).pack(fill="x",
                                                          padx=s(11))
            return row, hint_lbl

        def segmented(parent, options, getter, on_pick):
            box = tk.Frame(parent, bg=RAISED)
            cells = {}
            for label, value in options:
                cell = tk.Frame(box, bg=RAISED)
                cell.pack(side="left", padx=(s(1), 0))
                btn = tk.Button(cell, text=label, bd=0, relief="flat",
                                bg=RAISED, fg=MUTED,
                                activebackground=RAISED, activeforeground=FG,
                                font=("Segoe UI", 8), cursor="hand2",
                                padx=s(5), pady=s(2),
                                command=lambda v=value: on_pick(v))
                btn.pack()
                line = tk.Frame(cell, bg=RAISED, height=s(2))
                line.pack(fill="x", padx=s(3))
                cells[value] = (btn, line)
            cur = getter()
            for value, (btn, line) in cells.items():
                sel = value == cur
                btn.configure(fg=FG if sel else MUTED,
                              font=("Segoe UI", 8,
                                    "bold" if sel else "normal"))
                line.configure(bg=ACCENT if sel else RAISED)
            return box

        def switch(parent, getter, on_change):
            w, h = s(30), s(16)
            cv = tk.Canvas(parent, width=w, height=h, bg=RAISED,
                           highlightthickness=0, bd=0, cursor="hand2")

            def draw():
                on = bool(getter())
                col = ACCENT if on else TRACK
                cv.delete("all")
                r = h / 2.0
                cv.create_oval(0, 0, h, h, fill=col, outline="")
                cv.create_oval(w - h, 0, w, h, fill=col, outline="")
                cv.create_rectangle(r, 0, w - r, h, fill=col, outline="")
                knob = h - s(4)
                x = (w - h + s(2)) if on else s(2)
                cv.create_oval(x, s(2), x + knob, s(2) + knob,
                               fill="#ffffff" if on else FG, outline="")

            def clicked(event=None):
                on_change(not getter())
                draw()

            cv.bind("<Button-1>", clicked)
            draw()
            return cv

        def small_button(parent, text, command):
            return tk.Button(parent, text=text, bg=BTN, fg=FG, bd=0,
                             activebackground=BTN_HOVER, activeforeground=FG,
                             font=("Segoe UI", 8), cursor="hand2",
                             padx=s(9), pady=s(3), command=command)

        # ---- sol: görünüm ----
        card = section(left_col, "GÖRÜNÜM")
        row, _ = add_row(card, "Tema")
        segmented(row, [(THEME_LABEL[k], k) for k in THEME_ORDER],
                  lambda: self.cfg["theme"], self._pick_theme).pack(
            side="right", padx=(0, s(9)))

        row, _ = add_row(card, "Opaklık")
        op_val = tk.Label(row, text="%d%%" % int(round(self.alpha * 100)),
                          bg=RAISED, fg=FG, font=(self.mono, 9, "bold"),
                          width=4, anchor="e")
        op_val.pack(side="right", padx=(0, s(11)))

        def on_opacity(val, commit):
            pct = int(round(val))
            op_val.config(text="%d%%" % pct)
            if commit:
                self.set_opacity(pct / 100.0)
                self._settings_note("Opaklık: %d%%." % pct)
            else:
                self._apply_opacity(pct / 100.0)

        def slider(parent, value, on_change):
            w, h = s(112), s(18)
            cv = tk.Canvas(parent, width=w, height=h, bg=RAISED,
                           highlightthickness=0, bd=0, cursor="hand2")
            pad = s(7)
            cy = h / 2.0
            thick = max(2, s(3))
            state = {"val": float(value)}

            def draw(val):
                cv.delete("all")
                x1, x2 = pad, w - pad
                x = x1 + (x2 - x1) * (val - 60.0) / 40.0
                cv.create_line(x1, cy, x2, cy, fill=TRACK, width=thick,
                               capstyle="round")
                if x > x1:
                    cv.create_line(x1, cy, x, cy, fill=ACCENT,
                                   width=thick, capstyle="round")
                r = s(6)
                cv.create_oval(x - r, cy - r, x + r, cy + r, fill=ACCENT,
                               outline=RAISED, width=max(1, s(1)))

            def value_at(px):
                frac = (px - pad) / float(w - 2 * pad)
                return 60.0 + min(1.0, max(0.0, frac)) * 40.0

            def move(ev):
                state["val"] = value_at(ev.x)
                draw(state["val"])
                on_change(state["val"], False)

            def release(ev):
                move(ev)
                on_change(state["val"], True)

            cv.bind("<Button-1>", move)
            cv.bind("<B1-Motion>", move)
            cv.bind("<ButtonRelease-1>", release)
            draw(state["val"])
            return cv

        slider(row, int(round(self.alpha * 100)), on_opacity).pack(
            side="right", padx=(0, s(6)))

        row, _ = add_row(card, "Yoğunluk")
        segmented(row, [("Normal", "normal"), ("Kompakt", "compact")],
                  lambda: self.cfg["density"], self._pick_density).pack(
            side="right", padx=(0, s(9)))

        row, _ = add_row(card, "Her zaman üstte",
                         "Diğer pencerelerin üstünde kalır")
        switch(row, lambda: self.cfg.get("always_on_top", True),
               self._pick_always_on_top).pack(side="right",
                                              padx=(0, s(11)))

        row, _ = add_row(card, "Konum", "Kartı sağ alta taşır", last=True)
        small_button(row, "Konumu sıfırla",
                     self._pick_reset_position).pack(side="right",
                                                     padx=(0, s(9)))

        # ---- sol: gelişmiş ----
        card = section(left_col, "GELİŞMİŞ")
        row, _ = add_row(card, "Ayar dosyası", "config.json", last=True)
        small_button(row, "Klasörü aç",
                     self._open_data_dir).pack(side="right",
                                               padx=(0, s(9)))

        # ---- sağ: veri ----
        card = section(right_col, "VERİ")
        row, _ = add_row(card, "Piyasa açıkken", "Yenileme aralığı")
        segmented(row,
                  [("%d dk" % m, m) for m in REFRESH_OPEN_OPTIONS],
                  lambda: self.cfg.get("refresh_open", 15),
                  lambda v: self.set_refresh("refresh_open", v)).pack(
            side="right", padx=(0, s(9)))

        row, _ = add_row(card, "Piyasa kapalıyken", "Yenileme aralığı")
        segmented(row,
                  [("%d dk" % m, m) for m in REFRESH_CLOSED_OPTIONS],
                  lambda: self.cfg.get("refresh_closed", 60),
                  lambda v: self.set_refresh("refresh_closed", v)).pack(
            side="right", padx=(0, s(9)))

        row, _ = add_row(card, "Piyasa öncesi/sonrası",
                         "PÖ / PS fiyat ve değişimi göster")
        switch(row, lambda: self.cfg.get("extended_hours", True),
               self._pick_extended_hours).pack(side="right",
                                               padx=(0, s(11)))

        row, _ = add_row(card, "Piyasa kapalıyken durdur",
                         "İstek göndermez, açılışı bekler")
        switch(row, lambda: self.cfg.get("pause_when_closed", False),
               self._pick_pause_when_closed).pack(side="right",
                                                  padx=(0, s(11)))

        row, last_lbl = add_row(card, "Son güncelleme",
                                self._rel_time(), last=True)
        self._settings_last_lbl = last_lbl
        small_button(row, "Yenile",
                     self._settings_refresh_now).pack(side="right",
                                                      padx=(0, s(9)))
        tk.Label(right_col, text="Kaynak: Yahoo Finance · resmî olmayan, "
                                 "gecikmeli veri.",
                 bg=CARD, fg=DIM, font=("Segoe UI", 7), anchor="w",
                 justify="left", wraplength=s(280)).pack(
            fill="x", padx=s(2), pady=(s(4), 0))

        # ---- sağ: davranış ----
        card = section(right_col, "DAVRANIŞ")
        row, _ = add_row(card, "Windows'ta otomatik başlat",
                         "Oturum açılınca başlar")
        switch(row, startup_enabled, self._pick_startup).pack(
            side="right", padx=(0, s(11)))

        row, _ = add_row(card, "Kapatınca tepsiye gizle",
                         "Kapalıysa ✕ uygulamayı kapatır")
        switch(row, lambda: self.cfg.get("close_to_tray", True),
               self._pick_close_to_tray).pack(side="right",
                                              padx=(0, s(11)))

        row, _ = add_row(card, "Göster / gizle kısayolu",
                         "Değiştirme henüz yok", last=True)
        hk_ok = self.hotkey_ok is not False
        hk = tk.Label(row, text="Ctrl + Alt + S" if hk_ok
                      else "kaydedilemedi",
                      bg=TRACK, fg=FG if hk_ok else RED,
                      font=(self.mono, 8, "bold"), padx=s(6), pady=s(2))
        hk.pack(side="right", padx=(0, s(11)))
        self._settings_hotkey_lbl = hk

        # ---- alt bar ----
        tk.Frame(dlg, bg=DIVIDER, height=1).pack(fill="x", padx=s(18),
                                                 pady=(s(10), 0))
        status = tk.Label(dlg, text="", bg=CARD, fg=DIM, font=self.f_foot,
                          anchor="w")
        status.pack(fill="x", padx=s(18), pady=(s(6), 0))
        self._settings_status_lbl = status
        if self._settings_pending:
            text, color = self._settings_pending
            status.config(text=text, fg=color)

        footer = tk.Frame(dlg, bg=CARD)
        footer.pack(fill="x", padx=s(18), pady=(s(4), s(14)))
        tk.Button(footer, text="Sıfırla", bg=BTN, fg=MUTED, bd=0,
                  activebackground=BTN_HOVER, activeforeground=RED,
                  font=("Segoe UI", 9), cursor="hand2",
                  command=self.reset_settings).pack(side="left",
                                                    ipadx=s(12), ipady=s(4))
        small_button(footer, "Semboller…",
                     self.open_symbol_editor).pack(side="left",
                                                   padx=(s(6), 0))
        small_button(footer, "Portföy…",
                     self.open_portfolio_editor).pack(side="left",
                                                      padx=(s(6), 0))
        tk.Button(footer, text="Kapat", bg=ACCENT, fg="#ffffff", bd=0,
                  activebackground=ACCENT_HOVER, activeforeground="#ffffff",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  command=dlg.destroy).pack(side="right", ipadx=s(26),
                                            ipady=s(5))

        # ---- yerleşim ----
        dlg.update_idletasks()
        body_h = body.winfo_reqheight()
        sm = ctypes.windll.user32.GetSystemMetrics
        sw_, sh_ = sm(0), sm(1)
        cap = max(s(280), int(sh_ * 0.66))
        canvas.configure(height=min(max(body_h, s(160)), cap))
        if body_h > cap:
            def on_yscroll(first, last):
                vs.set(first, last)
                self._settings_scroll = (float(first), float(last))

            canvas.configure(yscrollcommand=on_yscroll)
            vs.pack(side="right", fill="y", padx=(s(4), 0))
            dlg.bind("<MouseWheel>", lambda ev: canvas.yview_scroll(
                -1 if ev.delta > 0 else 1, "units"))

        dlg.update_idletasks()
        if center:
            w = min(max(s(620), dlg.winfo_reqwidth()), sw_ - s(40))
            h = dlg.winfo_reqheight()
            dlg.geometry("%dx%d+%d+%d" % (
                w, h, max(0, sw_ // 2 - w // 2),
                max(0, sh_ // 2 - h // 2)))
        canvas.yview_moveto(self._settings_scroll[0])

    # ---------- data loop ----------

    def _set_hotkey_hint(self, ok):
        self.hotkey_ok = ok
        lbl = getattr(self, "_settings_hotkey_lbl", None)
        if lbl is None:
            return
        try:
            lbl.config(text=("Ctrl + Alt + S" if ok else "kaydedilemedi"),
                       fg=FG if ok else RED)
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

    def _refresh_minutes(self, is_open):
        key = "refresh_open" if is_open else "refresh_closed"
        default = (INTERVAL_OPEN if is_open else INTERVAL_CLOSED) // 60
        try:
            return max(1, int(self.cfg.get(key, default)))
        except (TypeError, ValueError):
            return default

    def fetch_loop(self):
        while not self.stop_flag.is_set():
            extended = self.cfg.get("extended_hours", True)
            is_open = market_active() if extended else market_open()
            if (not is_open and self.cfg.get("pause_when_closed")
                    and not self._force_refresh):
                # Piyasa kapalı ve yenileme duraklatıldı: ağ isteği yok,
                # yalnızca açılışı yakalamak için saat kontrol edilir.
                self.wake.wait(PAUSE_POLL)
                self.wake.clear()
                continue
            self._force_refresh = False
            symbols = list(self.cfg["symbols"])
            if not symbols:
                # Boş liste: sadece bekle, çevrimdışı sayma
                self.queue.put(({}, False))
                self.wake.wait(self._refresh_minutes(False) * 60)
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
                    results[sym] = fetch_quote(sym, extended)
                except requests.exceptions.HTTPError as exc:
                    if exc.response is not None and exc.response.status_code == 429:
                        time.sleep(THROTTLE_429)
                    failures += 1
                except Exception:
                    failures += 1
            if failures:
                log.warning("fetch: %d/%d sembol başarısız",
                            failures, len(symbols))
            extended = self.cfg.get("extended_hours", True)
            is_open = market_active() if extended else market_open()
            interval = self._refresh_minutes(is_open) * 60
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

    @staticmethod
    def _patch_tray_message_filter():
        """Frozen exe'de pystray'in mesaj filtresi çağrısı WinError 5 veriyor.

        ChangeWindowMessageFilterEx yalnızca explorer yeniden başladığında
        simgenin geri gelmesini sağlar; başarısız olursa tepsi simgesi yine
        çalışır (Shell_NotifyIcon etkilenmez). Bu yüzden hatayı yutuyoruz.
        """
        try:
            from pystray._util import win32 as pystray_win32
        except ImportError:
            return
        original = pystray_win32.ChangeWindowMessageFilterEx
        state = {"warned": False}

        def tolerant(*args, **kwargs):
            try:
                return original(*args, **kwargs)
            except OSError:
                if not state["warned"]:
                    state["warned"] = True
                    log.info("tepsi mesaj filtresi uygulanamadı (önemsiz)")
                return 0

        pystray_win32.ChangeWindowMessageFilterEx = tolerant

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
                "Ayarlar…",
                lambda *a: self.root.after(0, self.open_settings_editor)),
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
        if self.tray_icon:
            try:
                self.tray_icon.update_menu()
            except Exception:
                pass
        self._refresh_settings()

    def _setup_tray(self):
        if not (TRAY_AVAILABLE and PIL_AVAILABLE):
            return
        self._patch_tray_message_filter()
        self.tray_icon = self._create_tray_icon()
        threading.Thread(target=self._tray_run, daemon=True).start()
        self.root.after(1500, self._log_tray_state)

    def _log_tray_state(self):
        """Tanı: tepsi simgesi bildirim alanına eklendi mi?"""
        if not self.tray_icon:
            return
        try:
            visible = bool(self.tray_icon.visible)
        except Exception:
            visible = False
        log.info("tepsi simgesi: %s", "hazır" if visible else "görünür değil")

    def _tray_run(self):
        # Tepsi simgesi bazı oturumlarda (uzak masaüstü/servis) engellenebilir;
        # bu durumda widget penceresi çalışmaya devam etmeli.
        try:
            self.tray_icon.run()
        except Exception:
            self._tray_ok = False
            log.exception("tepsi simgesi başlatılamadı")

    def toggle_visibility(self, icon=None, item=None):
        if self.root.winfo_viewable():
            self.hide_window()
        else:
            self.show_window()

    def show_window(self):
        """Kartı kısa bir solmayla göster."""
        self._fade_gen = getattr(self, "_fade_gen", 0) + 1
        gen = self._fade_gen
        self.root.deiconify()
        self.root.lift()
        root = self.root
        if not anim_enabled():
            root.attributes("-alpha", self.alpha)
            return
        root.attributes("-alpha", 0.0)
        fade(root, 0.0, self.alpha, ANIM_MS,
             done=lambda: self._end_fade(gen),
             alive=lambda: gen == self._fade_gen)

    def _end_fade(self, gen):
        if gen != getattr(self, "_fade_gen", 0):
            return
        try:
            self.root.attributes("-alpha", self.alpha)
        except tk.TclError:
            pass

    def hide_window(self):
        self.close_detail(animate=False)
        dlg = self._settings_dlg
        if dlg is not None:
            try:
                dlg.destroy()
            except tk.TclError:
                pass
        if not anim_enabled() or not self.root.winfo_viewable():
            self.root.withdraw()
            return
        self._fade_gen = getattr(self, "_fade_gen", 0) + 1
        gen = self._fade_gen
        fade(self.root, self.alpha, 0.0, ANIM_CLOSE_MS,
             done=lambda: self._finish_hide(gen),
             alive=lambda: gen == self._fade_gen)

    def _finish_hide(self, gen):
        if gen != getattr(self, "_fade_gen", 0):
            return
        try:
            self.root.attributes("-alpha", self.alpha)
            self.root.withdraw()
        except tk.TclError:
            pass

    def close_window(self):
        """✕ / Alt+F4: tercihe göre tepsiye gizle ya da tamamen çık."""
        can_restore = bool(self._tray_ok or self.hotkey_ok is True)
        if self.cfg.get("close_to_tray", True) and can_restore:
            self.hide_window()
        else:
            self.exit_app()

    # ---------- lifecycle ----------

    def exit_app(self):
        log.info("çıkış")
        self.cfg["x"] = self.root.winfo_x()
        self.cfg["y"] = self.root.winfo_y()
        save_config(self.cfg)
        self.close_detail(animate=False)
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
