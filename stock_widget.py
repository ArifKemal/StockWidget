import os
import re
import sys
import csv
import json
import math
import time
import queue
import ctypes
import ctypes.wintypes
import datetime
import calendar
import email.utils
import logging
import platform
import random
import shutil
import threading
import urllib.parse
import webbrowser
import zipfile
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox
from logging.handlers import RotatingFileHandler

import requests

import i18n
from i18n import tr as T

from market_calendar import (  # noqa: F401  (takvim fonksiyonları dışa aktarılır)
    PROFILE_LABEL, crypto_phase, exchange_profile, market_state_phase,
    phase_label, tr_half_days, tr_holidays, tr_phase)

try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageTk, ImageChops
    PIL_AVAILABLE = True
    try:
        RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
    except AttributeError:      # Pillow < 9.1
        RESAMPLE_LANCZOS = Image.LANCZOS
except ImportError:
    PIL_AVAILABLE = False
    RESAMPLE_LANCZOS = None

i18n.install_tk_translation()

APP_NAME = "StockWidget"
APP_VERSION = "1.1.0"
FROZEN = bool(getattr(sys, "frozen", False))

UPDATE_URL = ("https://api.github.com/repos/ArifKemal/StockWidget/"
              "releases/latest")
RELEASES_URL = "https://github.com/ArifKemal/StockWidget/releases/latest"
UPDATE_TTL = 24 * 3600          # güncelleme kontrolü: günde en fazla 1 istek
VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")

# PyInstaller: kod _MEIPASS'e açılır, kalıcı veri oraya yazılamaz.
ASSET_DIR = (getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
             if FROZEN else os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = ASSET_DIR
ICON_FILE = os.path.join(ASSET_DIR, "assets", "stock.ico")


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
SNAPSHOT_FILE = os.path.join(DATA_DIR, "snapshot.json")
UPDATE_FILE = os.path.join(DATA_DIR, "update.json")
HISTORY_FILE = os.path.join(DATA_DIR, "portfolio-history.json")
ALARM_HISTORY_FILE = os.path.join(DATA_DIR, "alarm-history.json")
SERIES_CACHE_FILE = os.path.join(DATA_DIR, "series-cache.json")
# Eski sürümler config'i script/exe yanına yazıyordu; ilk açılışta taşınır.
LEGACY_CONFIG = os.path.join(
    os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else BASE_DIR,
    "config.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "StockWidget"

# İkinci kopya --toggle/--quit ile bu isimli olayları işaretler; ana pencere dinler.
# Duman testleri kurulu kopyayla çakışmasın: ayrı mutex/olay ad alanı.
_INSTANCE_SUFFIX = re.sub(
    r"[^A-Za-z0-9_-]", "", os.environ.get("SW_INSTANCE_SUFFIX", ""))[:40]
_INSTANCE_TAG = ("_" + _INSTANCE_SUFFIX) if _INSTANCE_SUFFIX else ""
TOGGLE_EVENT = "Local\\StockWidgetToggleEvent" + _INSTANCE_TAG
QUIT_EVENT = "Local\\StockWidgetQuitEvent" + _INSTANCE_TAG
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
    url += "&events=div%2Csplits"
    if include_prepost:
        url += "&includePrePost=true"
    return url
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

# Tek oturum: aynı istek sayısıyla TLS/bağlantı kurma maliyetini azaltır.
# Session thread-safe kabul edilmediği için kısa bir kilit kullanılır.
_HTTP = requests.Session()
_HTTP.headers.update(HEADERS)
_HTTP_LOCK = threading.Lock()


def _http_get(url, **kwargs):
    with _HTTP_LOCK:
        return _HTTP.get(url, **kwargs)


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
    "night_pause": True,
    "extended_hours": True,
    "close_to_tray": True,
    "sort_mode": "manual",
    "portfolio_show_cost": False,
    "hide_portfolio_amount": False,
    "alarms": {},
    "quiet_enabled": False,
    "quiet_start": 23,
    "quiet_end": 8,
    "focus_mode": False,
    "focus_symbol": "",
    "symbol_groups": {},
    "group_filter": "",
    "language": "tr",
}

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
MAX_SYMBOLS = 20
# Yahoo sembolleri: AAPL, BRK-B, ^GSPC, ES=F, BTC-USD
SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.\-^=]{0,11}$")
# config.json bozuk çıkıp yedekten kurtarıldıysa yedeği ezmemek için
_CONFIG_FROM_BACKUP = False

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
    override = _to_float(os.environ.get("SW_SCALE"))
    if override is not None:      # yalnızca DPI matris testleri için
        return min(3.0, max(0.75, override))
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


def virtual_screen():
    """Sanal masaüstü sınırları: (x, y, genişlik, yükseklik).

    Çoklu monitörde ikincil ekrandaki pencere birincil ekran sınırlarına
    kırpılmasın diye tüm monitörleri kapsayan dikdörtgen döner.
    """
    try:
        sm = ctypes.windll.user32.GetSystemMetrics
        x, y = int(sm(76)), int(sm(77))     # SM_X/YVIRTUALSCREEN
        w, h = int(sm(78)), int(sm(79))     # SM_CX/CYVIRTUALSCREEN
        if w > 0 and h > 0:
            return x, y, w, h
    except Exception:
        pass
    try:
        sm = ctypes.windll.user32.GetSystemMetrics
        return 0, 0, int(sm(0)), int(sm(1))
    except Exception:
        return 0, 0, 1920, 1080


def clamp_to_screen(x, y, width, height, margin_x=80, margin_y=40):
    """Pencereyi sanal masaüstünün içinde tut (en az bir tutamak görünür)."""
    vx, vy, vw, vh = virtual_screen()
    x = max(vx - (width - margin_x), min(x, vx + vw - margin_x))
    y = max(vy, min(y, vy + vh - margin_y))
    return x, y


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
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
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
        _observed(year, 6, 19) if year >= 2022       # Juneteenth (2022'den beri)
        else None,
        _observed(year, 7, 4),                       # Bağımsızlık Günü
        _nth_weekday(year, 9, 0, 1),                 # Labor Day (Eylül 1. Pzt)
        _nth_weekday(year, 11, 3, 4),                # Thanksgiving (Kasım 4. Per)
        _observed(year, 12, 25),                     # Noel
    ]
    return [d for d in days if d is not None]


def is_market_holiday(day):
    """Gün NYSE tatili mi?

    Yılbaşı Cumartesi'ye denk gelince gözlenen tatil bir önceki yılın
    31 Aralık'ına düşer; bu yüzden komşu yıl da kontrol edilir.
    """
    return day in market_holidays(day.year) or day in market_holidays(day.year + 1)


def early_closes(year):
    """NYSE erken kapanış (13:00 ET) günleri."""
    holidays = set(market_holidays(year))
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    days = {thanksgiving + datetime.timedelta(days=1)}
    for month, day in ((7, 3), (12, 24)):
        d = datetime.date(year, month, day)
        if d.weekday() < 5 and d not in holidays:
            days.add(d)
    return days


def market_phase(et=None):
    """ABD borsası seansı: 'pre', 'regular', 'post' ya da None (kapalı)."""
    et = et or et_now()
    if et.weekday() >= 5:
        return None
    day = datetime.date(et.year, et.month, et.day)
    if is_market_holiday(day):
        return None
    t = et.hour * 60 + et.minute
    if 4 * 60 <= t < 9 * 60 + 30:          # 04:00–09:30 ET öncesi seans
        return "pre"
    close = 13 * 60 if day in early_closes(day.year) else 16 * 60
    if 9 * 60 + 30 <= t < close:           # normal seans (erken kapanışta 13:00)
        return "regular"
    if close <= t < 20 * 60:               # 16:00–20:00 ET sonrası seans
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

# Bu yaştan eski veri "son güncelleme" sayılmaz; yaşı açıkça yazılır.
DATA_FRESH_SECONDS = 20 * 60


def _rel_seconds(seconds):
    """Saniyeyi kısa Türkçe yaş metnine çevirir (saf, test edilebilir)."""
    d = max(0, int(seconds))
    if d < 60:
        return "az önce"
    if d < 3600:
        return "%d dk önce" % (d // 60)
    if d < 86400:
        return "%d sa önce" % (d // 3600)
    return "%d gün önce" % (d // 86400)


def data_age_text(age, phase=None):
    """Durum metni: istek zamanı değil verinin yaşı (saf fonksiyon).

    Seans içinde taze veri "son güncelleme", eski veri "son veri" olarak
    yazılır. PÖ/PS penceresi açıkken bar yoksa bunun işlem olmadığı söylenir;
    böylece Cuma kapanışı pazartesi sabahı "az önce" gibi görünmez.
    """
    if age is None:
        return "güncelleniyor…"
    rel = _rel_seconds(age)
    if age >= DATA_FRESH_SECONDS:
        if phase in SESSION_LABEL:
            return "işlem yok · son veri %s" % rel
        return "son veri %s" % rel
    return "son güncelleme %s" % rel


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


def newest_quote_ts(quotes, fallback=None):
    """Sembol sözlüğündeki en yeni bar/quote zamanı.

    Durum satırı yaş hesabı ve açılışta snapshot yaşı için tek kaynak.
    """
    stamps = []
    for info in (quotes or {}).values():
        if not isinstance(info, dict):
            continue
        stamp = _to_float(info.get("bar_ts"))
        if stamp is None:
            stamp = _to_float(info.get("quote_ts"))
        if stamp:
            stamps.append(stamp)
    return max(stamps) if stamps else fallback


def us_quiet_hours(et=None):
    """ABD'de yeni 5 dk barı beklenmeyen saatler.

    Hafta sonu/tatil ya da 20:05–04:00 ET: Yahoo chart'ta yeni veri olmaz.
    Gece isteği duraklatma bu pencereyi kullanır; BIST/kripto açıkken
    `_fetch_cycle` bu kapıya hiç girmez.
    """
    et = et or et_now()
    if et.weekday() >= 5 or is_market_holiday(et.date()):
        return True
    minutes = et.hour * 60 + et.minute
    return minutes >= 20 * 60 + 5 or minutes < 4 * 60


def initial_stale(has_cache, cfg, et=None):
    """Açılışta önbellek bayrağı.

    Gece duraklatması açıkken canlı yanıt saatlerce beklenmeyeceği için
    önbellek etiketi/dimli satırlar yanıltıcı olur; yaş metni yeterli.
    """
    if not has_cache:
        return False
    if cfg.get("night_pause", True) and us_quiet_hours(et):
        return False
    return True


def trading_day(et=None):
    """1G grafiğin ait olduğu işlem günü (04:00 ET öncesi önceki güne düşer)."""
    et = et or et_now()
    day = et.date()
    if et.hour * 60 + et.minute < 4 * 60:
        day -= datetime.timedelta(days=1)
    for _ in range(14):
        if day.weekday() < 5 and not is_market_holiday(day):
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


def _to_float(value):
    """Gevşek sayı -> float; geçersiz/sonsuz değerde None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _to_int(value, default=None):
    """Gevşek sayı -> int; geçersiz değerde `default`."""
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clean_symbol(value):
    """Tek sembolü doğrular: büyük harf, boşluksuz; geçersizse None."""
    if not isinstance(value, str):
        return None
    sym = value.strip().upper()
    if not sym or not SYMBOL_RE.match(sym):
        return None
    return sym


def clean_symbols(value):
    """Sembol listesini doğrular: string, büyük harf, tekrarsız, sınırlı."""
    out = []
    if isinstance(value, (list, tuple)):
        for item in value:
            sym = clean_symbol(item)
            if sym and sym not in out:
                out.append(sym)
    return out[:MAX_SYMBOLS] or list(DEFAULT_SYMBOLS)


def clean_positions(value):
    """Portföy kayıtlarını doğrular; geçersiz satırlar sessizce atılır."""
    out = {}
    if not isinstance(value, dict):
        return out
    for key, rec in value.items():
        sym = clean_symbol(key)
        if not sym or not isinstance(rec, dict):
            continue
        qty = _to_float(rec.get("qty"))
        avg = _to_float(rec.get("avg"))
        if qty is None or avg is None or qty <= 0 or avg < 0:
            continue
        clean = {"qty": qty, "avg": avg}
        target = _to_float(rec.get("target"))
        if target is not None and target > 0:
            clean["target"] = target
        note = rec.get("note")
        if isinstance(note, str) and note.strip():
            clean["note"] = note.strip()[:120]
        out[sym] = clean
    return out


def clean_symbol_groups(value):
    """{sembol: grup adı} eşlemesini doğrular; boş/geçersizleri atar."""
    out = {}
    if not isinstance(value, dict):
        return out
    for key, group in value.items():
        sym = clean_symbol(key)
        if not sym or not isinstance(group, str):
            continue
        name = group.strip()[:24]
        if name:
            out[sym] = name
    return out


def clean_alarms(value):
    """Sembol başına fiyat/yüzde alarmlarını doğrular.

    Model: {"AAPL": {"above": 200, "below": 150, "pct": 5,
                     "extended": False}}. Alanların hepsi isteğe bağlıdır;
    boş kayıtlar ve geçersiz değerler atılır.
    """
    out = {}
    if not isinstance(value, dict):
        return out
    for key, rec in value.items():
        sym = clean_symbol(key)
        if not sym or not isinstance(rec, dict):
            continue
        clean = {}
        for field in ("above", "below", "pct", "profit", "loss"):
            number = _to_float(rec.get(field))
            if number is not None and number > 0:
                clean[field] = number
        if not clean:
            continue
        clean["extended"] = rec.get("extended") is True
        out[sym] = clean
    return out


def alarm_quote(info, extended):
    """Alarm için kullanılacak fiyat ve değişimi seçer.

    `extended` hem uygulamanın PÖ/PS ayarı hem alarmın kendi ayarı açıkken
    True olmalı. Dönüş: (fiyat, günlük_değişim_yüzdesi).
    """
    price = _to_float((info or {}).get("price"))
    pct = _to_float((info or {}).get("change_pct"))
    if extended and (info or {}).get("ext_session") in SESSION_LABEL:
        ext_price = _to_float(info.get("ext_price"))
        if ext_price is not None:
            price = ext_price
            ext_pct = _to_float(info.get("ext_change_pct"))
            if ext_pct is not None:
                pct = ext_pct
    return price, pct


def display_price(info, extended=True):
    """Kartla aynı fiyat: seans dışı veri varsa `ext_price`, yoksa `price`."""
    info = info or {}
    price = _to_float(info.get("price"))
    if extended and info.get("ext_session") in SESSION_LABEL:
        ext_price = _to_float(info.get("ext_price"))
        if ext_price is not None:
            return ext_price
    return price


def reference_close(info, extended=True):
    """Günlük değişimin tabanı.

    Seans dışı gösterimde son normal kapanış (`price`), normal seansta
    önceki kapanış (`prev_close`). Yahoo PÖ penceresinde `chartPreviousClose`
    olarak bir önceki günü verebildiği için `prev_close` taban olamaz.
    """
    info = info or {}
    if (extended and info.get("ext_session") in SESSION_LABEL
            and _to_float(info.get("ext_price")) is not None):
        return _to_float(info.get("price"))
    return _to_float(info.get("prev_close"))


PORTFOLIO_CSV_HEADER = [
    "Sembol", "Adet", "Ortalama", "Hedef", "Not", "ParaBirimi",
    "Fiyat", "Deger", "Maliyet", "KarZarar", "GunlukDegisim",
]


def portfolio_csv_rows(positions, last):
    """Portföyü CSV satırlarına çevirir; para birimleri ayrı kalır."""
    rows = []
    for sym in sorted(positions or {}):
        rec = positions[sym]
        if not isinstance(rec, dict):
            continue
        qty = _to_float(rec.get("qty")) or 0.0
        avg = _to_float(rec.get("avg")) or 0.0
        info = (last or {}).get(sym) or {}
        price = display_price(info)
        prev = reference_close(info)
        value = qty * price if price is not None else None
        cost = qty * avg
        pnl = value - cost if value is not None else None
        day = (qty * (price - prev)
               if price is not None and prev is not None else None)
        rows.append([
            sym, qty, avg,
            _to_float(rec.get("target")) or "",
            rec.get("note") or "",
            info.get("currency") or "",
            price if price is not None else "",
            round(value, 4) if value is not None else "",
            round(cost, 4),
            round(pnl, 4) if pnl is not None else "",
            round(day, 4) if day is not None else "",
        ])
    return rows


def is_quiet_time(now, start, end):
    """Sessiz saat aralığında mı? Gece yarısını aşan aralıkları destekler."""
    try:
        hour = int(now.hour)
        start = int(start) % 24
        end = int(end) % 24
    except (AttributeError, TypeError, ValueError):
        return False
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def evaluate_alarm(sym, info, rule, state, extended=False, position=None):
    """Alarmı değerlendirip state'i günceller; yeni olay metinlerini döndürür.

    State {sym: {"above": bool, "below": bool, "pct": bool,
    "profit": bool, "loss": bool}} biçimindedir. Koşul devam ettiği sürece
    bildirim tekrarlanmaz; koşul bozulunca alarm yeniden kurulur.
    `position` verilirse maliyete göre kâr/zarar eşikleri de denetlenir.
    """
    events = []
    price, pct = alarm_quote(info, extended)
    if price is None:
        return events
    flags = state.setdefault(sym, {})
    cur = (info or {}).get("currency")
    checks = (
        ("above", price >= rule.get("above", math.inf),
         "%s %s üzerine çıktı (şimdi %s)"),
        ("below", price <= rule.get("below", -math.inf),
         "%s %s altına indi (şimdi %s)"),
    )
    for kind, active, template in checks:
        if kind not in rule:
            continue
        if active and not flags.get(kind):
            events.append(template % (sym, fmt_money(rule[kind], cur),
                                      fmt_money(price, cur)))
        flags[kind] = bool(active)
    if "pct" in rule and pct is not None:
        active = abs(pct) >= rule["pct"]
        if active and not flags.get("pct"):
            events.append("%s günlük değişim %+.2f%% (eşik ±%.2f%%)"
                          % (sym, pct, rule["pct"]))
        flags["pct"] = bool(active)
    avg = _to_float((position or {}).get("avg"))
    qty = _to_float((position or {}).get("qty"))
    if avg and avg > 0 and qty and qty > 0:
        pl_pct = (price / avg - 1.0) * 100.0
        for kind, active, label in (
                ("profit", pl_pct >= rule.get("profit", math.inf), "kâr"),
                ("loss", pl_pct <= -rule.get("loss", math.inf), "zarar")):
            if kind not in rule:
                continue
            if active and not flags.get(kind):
                events.append("%s maliyete göre %s %+.2f%% (eşik %.1f%%)"
                              % (sym, label, pl_pct, rule[kind]))
            flags[kind] = bool(active)
    return events


def _atomic_write_json(path, payload):
    """JSON dosyasını geçici dosya + yer değiştirme ile atomik yazar."""
    tmp = path + ".tmp"
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except (OSError, TypeError, ValueError) as exc:
        log.debug("JSON yazılamadı (%s): %s", path, exc)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


HISTORY_MAX_ENTRIES = 400


def clean_history(value):
    """Portföy geçmişi: günlük, para birimi başına toplamlar."""
    entries = value.get("entries") if isinstance(value, dict) else value
    if not isinstance(entries, list):
        return []
    out = []
    seen = set()
    for rec in entries:
        if not isinstance(rec, dict):
            continue
        try:
            day = datetime.date.fromisoformat(str(rec.get("date")))
        except (TypeError, ValueError):
            continue
        totals = rec.get("totals")
        if not isinstance(totals, dict):
            continue
        clean_totals = {}
        for cur, bucket in totals.items():
            if not isinstance(cur, str) or not isinstance(bucket, dict):
                continue
            value_num = _to_float(bucket.get("value"))
            if value_num is None or value_num < 0:
                continue
            clean_totals[cur[:8]] = {
                "value": value_num,
                "cost": _to_float(bucket.get("cost")) or 0.0,
                "day": _to_float(bucket.get("day")) or 0.0,
            }
        if not clean_totals or day.isoformat() in seen:
            continue
        seen.add(day.isoformat())
        out.append({"date": day.isoformat(),
                    "ts": _to_float(rec.get("ts")) or 0.0,
                    "totals": clean_totals})
    out.sort(key=lambda item: item["date"])
    return out[-HISTORY_MAX_ENTRIES:]


def record_history(entries, totals, day=None):
    """Bugünün toplamını ekler/üzerine yazar; geçmişi döndürür."""
    clean_totals = {}
    for cur, bucket in (totals or {}).items():
        if not isinstance(bucket, dict):
            continue
        value_num = _to_float(bucket.get("value"))
        if value_num is None or value_num < 0:
            continue
        clean_totals[str(cur)[:8]] = {
            "value": value_num,
            "cost": _to_float(bucket.get("cost")) or 0.0,
            "day": _to_float(bucket.get("day")) or 0.0,
        }
    if not clean_totals:
        return clean_history(entries)
    day = day or datetime.date.today()
    if isinstance(day, str):
        try:
            day = datetime.date.fromisoformat(day)
        except ValueError:
            day = datetime.date.today()
    iso = day.isoformat()
    clean = clean_history(entries)
    existing = next((item for item in clean if item.get("date") == iso), None)
    if existing and existing.get("totals") == clean_totals:
        return clean          # aynı gün aynı toplam: gereksiz yazma yok
    kept = [item for item in clean if item.get("date") != iso]
    kept.append({"date": iso, "ts": time.time(), "totals": clean_totals})
    return clean_history(kept)


def history_series(entries, currency, days=30):
    """Tek para birimi için son N kayıtlı günü (tarih, değer) olarak döndürür."""
    points = []
    for item in clean_history(entries):
        bucket = (item.get("totals") or {}).get(currency)
        if bucket:
            points.append((item["date"], bucket["value"]))
    return points[-max(1, int(days)):]


def history_change(series):
    """Serinin ilk ve son değeri arasındaki yüzde değişim; yetersizse None."""
    if not series or len(series) < 2:
        return None
    first = _to_float(series[0][1])
    last = _to_float(series[-1][1])
    if first is None or last is None or first <= 0:
        return None
    return (last / first - 1.0) * 100.0


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return clean_history(json.load(f))
    except (OSError, ValueError):
        return []


def save_history(entries):
    return _atomic_write_json(HISTORY_FILE, {"entries": clean_history(entries)})


ALARM_HISTORY_MAX = 100


def clean_alarm_history(value):
    entries = value.get("entries") if isinstance(value, dict) else value
    if not isinstance(entries, list):
        return []
    out = []
    for rec in entries:
        if not isinstance(rec, dict):
            continue
        message = rec.get("message")
        ts = _to_float(rec.get("ts"))
        if not isinstance(message, str) or not message.strip() or ts is None:
            continue
        out.append({"ts": ts, "message": message.strip()[:300]})
    out.sort(key=lambda item: item["ts"])
    return out[-ALARM_HISTORY_MAX:]


def append_alarm_history(entries, messages, ts=None):
    stamp = time.time() if ts is None else ts
    updated = clean_alarm_history(entries)
    for message in messages:
        updated.append({"ts": stamp, "message": str(message)[:300]})
    return updated[-ALARM_HISTORY_MAX:]


def load_alarm_history():
    try:
        with open(ALARM_HISTORY_FILE, "r", encoding="utf-8") as f:
            return clean_alarm_history(json.load(f))
    except (OSError, ValueError):
        return []


def save_alarm_history(entries):
    return _atomic_write_json(ALARM_HISTORY_FILE,
                              {"entries": clean_alarm_history(entries)})


def redact_config(cfg):
    """Destek paketi için hassas portföy/alarm ayrıntılarını çıkarır."""
    safe = {k: v for k, v in (cfg or {}).items()
            if k not in ("positions", "alarms", "symbol_groups", "x", "y",
                         "focus_symbol", "symbols", "group_filter")}
    safe["symbols_count"] = len(cfg.get("symbols") or [])
    safe["positions_count"] = len(cfg.get("positions") or {})
    safe["alarms_count"] = len(cfg.get("alarms") or {})
    safe["groups_count"] = len(set(
        (cfg.get("symbol_groups") or {}).values()))
    return safe


def diagnostics_info(cfg, last, history, version=APP_VERSION, now=None):
    """Destek/tanılama için okunabilir sistem özeti üretir."""
    now = time.time() if now is None else now
    data_ts = 0.0
    for info in (last or {}).values():
        ts = _to_float((info or {}).get("quote_ts"))
        if ts:
            data_ts = max(data_ts, ts)
    age = ("%.0f dk" % ((now - data_ts) / 60.0)) if data_ts else "bilinmiyor"
    lines = [
        "%s %s" % (APP_NAME, version),
        "zaman: %s" % datetime.datetime.fromtimestamp(now).strftime(
            "%Y-%m-%d %H:%M:%S"),
        "frozen: %s" % ("evet" if FROZEN else "hayır"),
        "platform: %s" % platform.platform(),
        "python: %s" % platform.python_version(),
        "veri dizini: %s" % DATA_DIR,
        "sembol: %d | portföy: %d | alarm: %d | geçmiş: %d gün" % (
            len(cfg.get("symbols") or []),
            len(cfg.get("positions") or {}),
            len(cfg.get("alarms") or {}),
            len(history or [])),
        "son fiyat yaşı: %s" % age,
        "tema/yoğunluk: %s / %s" % (cfg.get("theme"), cfg.get("density")),
        "sürüm notu: pozisyon adet/maliyet ve alarm eşikleri pakete girmez",
    ]
    return "\n".join(lines) + "\n"


def parse_dividends(events):
    """Yahoo chart `events.dividends` -> [(ts, amount)] (eskiden yeniye)."""
    block = (events or {}).get("dividends") or {}
    out = []
    if isinstance(block, dict):
        for key, item in block.items():
            if not isinstance(item, dict):
                continue
            ts = _to_float(item.get("date")) or _to_float(key)
            amount = _to_float(item.get("amount"))
            if ts is None or amount is None or amount <= 0:
                continue
            out.append((ts, amount))
    out.sort()
    return out[-50:]


def parse_splits(events):
    """Yahoo chart `events.splits` -> [(ts, numerator, denominator)]."""
    block = (events or {}).get("splits") or {}
    out = []
    if isinstance(block, dict):
        for key, item in block.items():
            if not isinstance(item, dict):
                continue
            ts = _to_float(item.get("date")) or _to_float(key)
            num = _to_float(item.get("numerator"))
            den = _to_float(item.get("denominator"))
            if ts is None or not num or not den or num <= 0 or den <= 0:
                continue
            out.append((ts, num, den))
    out.sort()
    return out[-20:]


def _dividend_list(value):
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:50]:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        ts, amount = _to_float(item[0]), _to_float(item[1])
        if ts is not None and amount is not None and amount > 0:
            out.append((ts, amount))
    return out


def _split_list(value):
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:20]:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        ts, num, den = (_to_float(item[0]), _to_float(item[1]),
                        _to_float(item[2]))
        if ts is not None and num and den and num > 0 and den > 0:
            out.append((ts, num, den))
    return out


def _read_config_file():
    """config.json'ı okur; bozuksa `.bak` yedeğine düşer."""
    global _CONFIG_FROM_BACKUP
    for path in (CONFIG_FILE, CONFIG_FILE + ".bak"):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            log.warning("config okunamadı (%s): %s", path, exc)
            continue
        if not isinstance(data, dict):
            log.warning("config kökü nesne değil (%s)", path)
            continue
        if path != CONFIG_FILE:
            _CONFIG_FROM_BACKUP = True
            log.warning("config bozuk; yedekten kurtarıldı")
        return data
    return {}


def load_config():
    cfg = dict(SETTINGS_DEFAULTS)
    raw = _read_config_file()
    if raw:
        cfg.update(raw)
    cfg["symbols"] = clean_symbols(cfg.get("symbols"))
    if not isinstance(cfg.get("theme"), str) or cfg["theme"] not in PALETTES:
        cfg["theme"] = SETTINGS_DEFAULTS["theme"]
    opacity = _to_float(cfg.get("opacity"))
    if opacity is None:
        opacity = SETTINGS_DEFAULTS["opacity"]
    cfg["opacity"] = min(1.0, max(0.6, opacity))
    if cfg.get("density") not in ("normal", "compact"):
        cfg["density"] = SETTINGS_DEFAULTS["density"]
    cfg["positions"] = clean_positions(cfg.get("positions"))
    cfg["alarms"] = clean_alarms(cfg.get("alarms"))
    groups = clean_symbol_groups(cfg.get("symbol_groups"))
    cfg["symbol_groups"] = {s: g for s, g in groups.items()
                            if s in cfg["symbols"]}
    cfg["quiet_enabled"] = _cfg_bool(cfg, "quiet_enabled", False)
    for key in ("quiet_start", "quiet_end"):
        cfg[key] = min(23, max(0, _to_int(
            cfg.get(key), SETTINGS_DEFAULTS[key])))
    cfg["focus_mode"] = _cfg_bool(cfg, "focus_mode", False)
    focus = clean_symbol(cfg.get("focus_symbol"))
    cfg["focus_symbol"] = focus if focus in cfg["symbols"] else ""
    group_filter = cfg.get("group_filter")
    if not isinstance(group_filter, str):
        group_filter = ""
    if group_filter and group_filter not in set(cfg["symbol_groups"].values()):
        group_filter = ""
    cfg["group_filter"] = group_filter
    if cfg.get("language") not in ("tr", "en"):
        cfg["language"] = SETTINGS_DEFAULTS["language"]
    if cfg.get("sort_mode") not in ("manual", "change", "symbol", "value"):
        cfg["sort_mode"] = SETTINGS_DEFAULTS["sort_mode"]
    cfg["portfolio_show_cost"] = _cfg_bool(cfg, "portfolio_show_cost", False)
    cfg["hide_portfolio_amount"] = _cfg_bool(
        cfg, "hide_portfolio_amount", False)
    cfg["always_on_top"] = _cfg_bool(cfg, "always_on_top", True)
    cfg["close_to_tray"] = _cfg_bool(cfg, "close_to_tray", True)
    cfg["pause_when_closed"] = _cfg_bool(cfg, "pause_when_closed", False)
    cfg["night_pause"] = _cfg_bool(cfg, "night_pause", True)
    cfg["extended_hours"] = _cfg_bool(cfg, "extended_hours", True)
    for key in ("refresh_open", "refresh_closed"):
        minutes = _to_int(cfg.get(key), SETTINGS_DEFAULTS[key])
        cfg[key] = min(1440, max(1, minutes))
    for key in ("x", "y"):
        cfg[key] = _to_int(cfg.get(key))
    return cfg


def save_config(cfg):
    """Ayarları atomik yazar: yazma kesilse bile eski dosya bozulmaz."""
    global _CONFIG_FROM_BACKUP
    tmp = CONFIG_FILE + ".tmp"
    try:
        folder = os.path.dirname(CONFIG_FILE)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(CONFIG_FILE) and not _CONFIG_FROM_BACKUP:
            try:
                shutil.copy2(CONFIG_FILE, CONFIG_FILE + ".bak")
            except OSError:
                pass
        os.replace(tmp, CONFIG_FILE)
        _CONFIG_FROM_BACKUP = False
        return True
    except (OSError, TypeError, ValueError) as exc:
        log.warning("config yazılamadı: %s", exc)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


SNAPSHOT_NUM_FIELDS = (
    "price", "prev_close", "change_pct", "change_abs",
    "ext_price", "ext_change_pct", "ext_change_abs",
    "open", "day_high", "day_low", "high_52w", "low_52w", "volume",
    "quote_ts", "bar_ts",
)
SNAPSHOT_LIST_FIELDS = ("spark", "spark_times", "spark_volumes")
SNAPSHOT_MAX_POINTS = 500


def _num_list(value):
    """JSON listesini sonlu sayılara indirger; bozuk öğeleri atar."""
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:SNAPSHOT_MAX_POINTS]:
        num = _to_float(item)
        if num is not None:
            out.append(num)
    return out


def _ohlc_list(value):
    """[[o, h, l, c], ...] -> geçerli (float, float, float, float) listesi."""
    if not isinstance(value, list):
        return []
    out = []
    for row in value[:SNAPSHOT_MAX_POINTS]:
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            continue
        nums = [_to_float(x) for x in row[:4]]
        if any(x is None for x in nums):
            continue
        out.append(tuple(nums))
    return out


def load_snapshot(symbols):
    """Son başarılı fiyatları okur: açılışta anında gösterim için."""
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}, None
    if not isinstance(data, dict):
        return {}, None
    quotes = data.get("quotes")
    if not isinstance(quotes, dict):
        return {}, None
    out = {}
    for sym in symbols or []:
        info = quotes.get(sym)
        if not isinstance(info, dict):
            continue
        price = _to_float(info.get("price"))
        prev = _to_float(info.get("prev_close"))
        pct = _to_float(info.get("change_pct"))
        if price is None or not prev or pct is None:
            continue
        # Elle bozulmuş/yarım kalmış dosya çizim sırasında çökmesin:
        # tüm sayısal alanlar ve grafik listeleri burada doğrulanır.
        clean = {}
        for key in SNAPSHOT_NUM_FIELDS:
            clean[key] = _to_float(info.get(key))
        for key in SNAPSHOT_LIST_FIELDS:
            clean[key] = _num_list(info.get(key))
        clean["spark_ohlc"] = _ohlc_list(info.get("spark_ohlc"))
        clean["dividends"] = _dividend_list(info.get("dividends"))
        clean["splits"] = _split_list(info.get("splits"))
        clean["price"] = price
        clean["prev_close"] = prev
        clean["change_pct"] = pct
        clean["change_abs"] = clean["change_abs"] or 0.0
        for text_key in ("name", "currency", "exchange", "exchange_code",
                         "market_state", "timezone", "instrument_type"):
            text = info.get(text_key)
            clean[text_key] = text if isinstance(text, str) else ""
        clean["name"] = clean["name"] or sym
        clean["ext_session"] = (info.get("ext_session")
                                if info.get("ext_session") in ("pre", "post")
                                else None)
        out[sym] = clean
    return out, _to_float(data.get("ts"))


def save_snapshot(quotes):
    """Son fiyatları diske yazar (atomik); hata uygulamayı etkilemez."""
    if not quotes:
        return
    tmp = SNAPSHOT_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "quotes": quotes}, f)
        os.replace(tmp, SNAPSHOT_FILE)
    except (OSError, TypeError, ValueError) as exc:
        log.debug("snapshot yazılamadı: %s", exc)
        try:
            os.remove(tmp)
        except OSError:
            pass


def cleanup_stale_mei(max_age=7 * 24 * 3600):
    """Çökmelerden kalan eski PyInstaller `_MEIxxxx` klasörlerini siler.

    Yalnızca bir haftadan eski klasörlere dokunur: aynı anda çalışan başka
    bir onefile uygulamasının dizinini yanlışlıkla silmemek için.
    """
    if not FROZEN:
        return
    current = os.path.normcase(getattr(sys, "_MEIPASS", "") or "")
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if not temp or not os.path.isdir(temp):
        return
    now = time.time()
    try:
        names = os.listdir(temp)
    except OSError:
        return
    for name in names:
        if not name.startswith("_MEI"):
            continue
        path = os.path.join(temp, name)
        if os.path.normcase(path) == current or not os.path.isdir(path):
            continue
        try:
            if now - os.path.getmtime(path) < max_age:
                continue
            shutil.rmtree(path, ignore_errors=True)
            log.info("eski onefile klasörü silindi: %s", name)
        except OSError:
            pass


def parse_version(text):
    """'v1.2.3' -> (1, 2, 3); geçersizse None."""
    if not isinstance(text, str):
        return None
    match = VERSION_RE.search(text.strip().lstrip("vV"))
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def check_latest_release(timeout=5):
    """GitHub'daki son sürümü sorar; ağ hatasında None döner."""
    try:
        resp = _http_get(UPDATE_URL, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "StockWidget/%s" % APP_VERSION,
        }, timeout=timeout)
        resp.raise_for_status()
        data = resp.json() or {}
    except (requests.exceptions.RequestException, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    version = parse_version(data.get("tag_name") or data.get("name"))
    url = data.get("html_url")
    if not version or not isinstance(url, str):
        return None
    return {"version": ".".join(str(x) for x in version),
            "url": url, "ts": time.time()}


def read_update_cache():
    """Son güncelleme kontrolünün sonucu (günde 1 istek için)."""
    try:
        with open(UPDATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_update_cache(info):
    try:
        with open(UPDATE_FILE, "w", encoding="utf-8") as f:
            json.dump(info, f)
    except (OSError, TypeError, ValueError):
        pass


MARKET_STATE_LABEL = {
    "PRE": "PÖ", "PREPRE": "PÖ", "REGULAR": "açık",
    "POST": "PS", "POSTPOST": "PS", "CLOSED": "kapalı",
}


def is_us_exchange(meta):
    """PÖ/PS rozetinin anlamlı olduğu ABD hisse piyasası mı?

    `exchange_profile` ile aynı kuralları kullanır: borsa kodu, New York saat
    dilimi veya tam borsa adı. Meta tamamen boşsa eski davranış korunur.
    """
    meta = meta or {}
    profile = exchange_profile(meta)
    if profile == "us":
        return True
    if profile in ("tr", "crypto"):
        return False
    has_info = any(meta.get(key) for key in
                   ("exchange_code", "exchangeName", "exchange",
                    "timezone", "exchangeTimezoneName", "fullExchangeName"))
    return not has_info


def fetch_quote(symbol, include_prepost=True):
    url = quote_url(symbol, include_prepost)
    resp = _http_get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    chart = (data or {}).get("chart") or {}
    result = chart.get("result") or []
    if not result or not isinstance(result[0], dict):
        raise ValueError("no data")
    meta = result[0].get("meta") or {}
    events = result[0].get("events") or {}
    dividends = parse_dividends(events)
    splits = parse_splits(events)
    price = _to_float(meta.get("regularMarketPrice"))
    prev = (_to_float(meta.get("chartPreviousClose"))
            or _to_float(meta.get("previousClose")))
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
        c = _to_float(arr["close"][i])
        if c is None:
            continue
        o = _to_float(_at("open", i))
        o = c if o is None else o
        h = _to_float(_at("high", i))
        lo_ = _to_float(_at("low", i))
        h = max(o, c, h if h is not None else o)
        lo_ = min(o, c, lo_ if lo_ is not None else o)
        rows.append((stamps[i], c, o, h, lo_, _to_float(_at("volume", i))))

    if not include_prepost:
        # Seans dışı kapalıyken PÖ/PS barları grafiğe karışmasın
        rows = [r for r in rows if r[0] is None or bar_session(r[0]) is None]

    # Seans dışı (piyasa öncesi/sonrası) fiyat: grafiği besleyen son bar.
    # Böylece kart ve detaydaki fiyat, grafiğin bittiği noktayla birebir aynı
    # olur; piyasa kapandıktan sonra da "kapanışta takılı" görünmez.
    ext_session = None
    ext_price = ext_pct = ext_abs = None
    last_bar_ts = _to_float(rows[-1][0]) if rows else None
    if include_prepost and rows and is_us_exchange(meta):
        ext_session = bar_session(rows[-1][0])
        if ext_session:
            ext_price = float(rows[-1][1])
            # Seans dışı değişim, sitelerde olduğu gibi son normal seans
            # kapanışına (`price`) göre. `prev` bir önceki günün kapanışıdır;
            # PÖ/PS'de taban olarak kullanılırsa yüzde yanlış çıkar.
            ext_pct = (ext_price / float(price) - 1.0) * 100.0
            ext_abs = ext_price - float(price)
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
        "exchange_code": (meta.get("exchangeName")
                          if isinstance(meta.get("exchangeName"), str) else ""),
        "market_state": (meta.get("marketState")
                         if isinstance(meta.get("marketState"), str) else ""),
        "timezone": (meta.get("exchangeTimezoneName")
                     if isinstance(meta.get("exchangeTimezoneName"), str) else ""),
        "instrument_type": (meta.get("instrumentType")
                            if isinstance(meta.get("instrumentType"), str)
                            else ""),
        "quote_ts": _to_float(meta.get("regularMarketTime")),
        "bar_ts": last_bar_ts,
        "price": float(price),
        "prev_close": float(prev),
        "change_pct": (float(price) / float(prev) - 1.0) * 100.0,
        "change_abs": float(price) - float(prev),
        "ext_session": ext_session,
        "ext_price": ext_price,
        "ext_change_pct": ext_pct,
        "ext_change_abs": ext_abs,
        "open": _to_float(opens[0]) if opens else None,
        "day_high": _to_float(day_high),
        "day_low": _to_float(day_low),
        "high_52w": _to_float(meta.get("fiftyTwoWeekHigh")),
        "low_52w": _to_float(meta.get("fiftyTwoWeekLow")),
        "volume": _to_float(volume),
        "spark": closes,
        "spark_times": spark_times,
        "spark_volumes": spark_volumes,
        "spark_ohlc": spark_ohlc,
        "dividends": dividends,
        "splits": splits,
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
            None, False, "Local\\StockWidgetDesktopInstance" + _INSTANCE_TAG)
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
    prefix = {"USD": "$", "EUR": "€", "GBP": "£",
              "TRY": "₺"}.get((currency or "").upper())
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
    return img.resize((w, h), RESAMPLE_LANCZOS)


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
    return img.resize((w, h), RESAMPLE_LANCZOS)


SERIES_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/"
              "{s}?range={r}&interval={i}&events=div%2Csplits")

TF_RANGE = {"1H": ("5d", "15m"), "1A": ("1mo", "1d"), "1Y": ("1y", "1d")}
TF_TTL = {"1H": 15 * 60, "1A": 60 * 60, "1Y": 60 * 60}
TF_LABEL = {"1D": "1G", "1H": "1H", "1A": "1A", "1Y": "1Y"}
TF_TABS = ("1D", "1H", "1A", "1Y")

_SERIES_CACHE = {}
SERIES_CACHE_MAX = 32
_SERIES_DISK_LOADED = False


def _series_data_clean(data):
    """Diskten/memory'den gelen seriyi çizim için güvenli hale getirir."""
    if not isinstance(data, dict):
        return None
    clean = {
        "closes": _num_list(data.get("closes")),
        "times": _num_list(data.get("times")),
        "volumes": _num_list(data.get("volumes")),
        "ohlc": _ohlc_list(data.get("ohlc")),
        "dividends": _dividend_list(data.get("dividends")),
        "splits": _split_list(data.get("splits")),
    }
    return clean if len(clean["closes"]) >= 2 else None


def load_series_disk(now=None):
    """Disk önbelleğini TTL içindeki kayıtlarla belleğe yükler (bir kez)."""
    global _SERIES_DISK_LOADED
    if _SERIES_DISK_LOADED:
        return
    _SERIES_DISK_LOADED = True
    try:
        with open(SERIES_CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return
    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, dict):
        return
    now = time.time() if now is None else now
    for key, rec in entries.items():
        if not isinstance(key, str) or not isinstance(rec, dict):
            continue
        try:
            symbol, tf = key.split("|", 1)
        except ValueError:
            continue
        if tf not in TF_TTL:
            continue
        ts = _to_float(rec.get("ts"))
        if ts is None or now - ts >= TF_TTL[tf]:
            continue
        data = _series_data_clean(rec.get("data"))
        if data:
            _SERIES_CACHE[(symbol, tf)] = (ts, data)


def save_series_disk():
    entries = {}
    for (symbol, tf), (ts, data) in list(_SERIES_CACHE.items())[-SERIES_CACHE_MAX:]:
        clean = _series_data_clean(data)
        if clean:
            entries["%s|%s" % (symbol, tf)] = {"ts": ts, "data": clean}
    _atomic_write_json(SERIES_CACHE_FILE, {"entries": entries})


def fetch_series(symbol, tf):
    """Seçilen zaman aralığı için kapanış serisi (tembel + önbellekli)."""
    load_series_disk()
    key = (symbol, tf)
    now = time.time()
    hit = _SERIES_CACHE.get(key)
    if hit and now - hit[0] < TF_TTL[tf]:
        return hit[1]
    rng, interval = TF_RANGE[tf]
    resp = _http_get(SERIES_URL.format(s=symbol, r=rng, i=interval),
                     timeout=10)
    resp.raise_for_status()
    result = ((resp.json() or {}).get("chart") or {}).get("result") or []
    if not result or not isinstance(result[0], dict):
        raise ValueError("empty series")
    res = result[0]
    events = res.get("events") or {}
    stamps = res.get("timestamp") or []
    quote = (res.get("indicators") or {}).get("quote") or [{}]
    q = quote[0] if isinstance(quote[0], dict) else {}
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
        c = _to_float(raw["close"][i])
        if c is None:
            continue
        o = _to_float(_at("open", i))
        o = c if o is None else o
        h = _to_float(_at("high", i))
        lo_ = _to_float(_at("low", i))
        h = max(o, c, h if h is not None else o)
        lo_ = min(o, c, lo_ if lo_ is not None else o)
        pts.append((stamps[i], c, o, h, lo_, _to_float(_at("volume", i))))
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
        "dividends": parse_dividends(events),
        "splits": parse_splits(events),
    }
    if len(_SERIES_CACHE) >= SERIES_CACHE_MAX:
        _SERIES_CACHE.clear()
    _SERIES_CACHE[key] = (now, data)
    save_series_disk()
    return data


def _retry_after(response, default=THROTTLE_429):
    """429'daki Retry-After'ı saniyeye çevirir (sayı veya HTTP-date)."""
    try:
        value = response.headers.get("Retry-After")
    except AttributeError:
        return default
    try:
        return min(3600, max(60, int(float(value))))
    except (TypeError, ValueError):
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
        seconds = (when - datetime.datetime.now(
            datetime.timezone.utc)).total_seconds()
        return min(3600, max(60, int(seconds)))
    except (AttributeError, TypeError, ValueError, OverflowError):
        return default


def chart_price_at(y, y1, y2, lo, hi):
    """Grafikteki Y koordinatını fiyata çevirir; aralık dışında None."""
    if y2 <= y1 or hi <= lo or y < y1 or y > y2:
        return None
    ratio = (y - y1) / float(y2 - y1)
    return hi - ratio * (hi - lo)


def round_chart_price(price):
    """Grafik tıklamasını makul fiyat ondalığına yuvarlar."""
    value = _to_float(price)
    if value is None or value <= 0:
        return None
    return round(value, 4 if value < 1 else 2)


def set_alarm_level(alarms, symbol, kind, price):
    """`above`/`below` alarm seviyesini ekler; diğer alanları korur."""
    if kind not in ("above", "below"):
        return clean_alarms(alarms)
    value = round_chart_price(price)
    if value is None:
        return clean_alarms(alarms)
    rules = dict(alarms or {})
    rule = dict(rules.get(symbol) or {})
    rule[kind] = value
    rules[symbol] = rule
    return clean_alarms(rules)


def clear_alarm_level(alarms, symbol, kind=None):
    """Tek yönü ya da sembolün tüm alarmlarını kaldırır."""
    rules = dict(alarms or {})
    rule = dict(rules.get(symbol) or {})
    if kind in ("above", "below"):
        rule.pop(kind, None)
    else:
        rule = {}
    if rule:
        rules[symbol] = rule
    else:
        rules.pop(symbol, None)
    return clean_alarms(rules)


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
        self.series_ts = {}
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
        self.canvas.bind("<Button-3>", self._on_chart_right_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        # Esc ile paneli kapat: hem panelde hem ana kartta çalışsın
        self.win.bind("<Escape>", self._on_escape)
        self._esc_id = app.root.bind("<Escape>", self._on_escape, add="+")
        self._dx = 0
        self._dy = 0
        self._plot = None
        self._chart_menu = None
        self._alarm_dialog = None
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
        stale = tf in self.series and self._series_stale(tf)
        if tf == self.tf:
            # Aynı sekme: taze ya da yükleniyorsa yapacak bir şey yok;
            # bayatladıysa aşağıda tazelenir.
            if (tf == "1D" or (tf in self.series and not stale)
                    or self.loading == tf):
                return
        self.tf = tf
        self.errors.discard(tf)
        if tf != "1D" and (tf not in self.series or stale):
            self.loading = tf
            threading.Thread(target=self._fetch_series, args=(tf,),
                             daemon=True).start()
        self.render()
        self._animate_pill(old)

    def _series_stale(self, tf):
        """Önbellekteki seri TTL'i geçtiyse tazelenmeli."""
        ts = self.series_ts.get(tf)
        return ts is None or time.time() - ts > TF_TTL.get(tf, 0)

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
                    self.series_ts[tf] = time.time()
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
                "dividends": list(info.get("dividends") or []),
                "splits": list(info.get("splits") or []),
            }
        data = self.series.get(self.tf) or {}
        return {
            "closes": list(data.get("closes") or []),
            "times": list(data.get("times") or []),
            "volumes": list(data.get("volumes") or []),
            "ohlc": list(data.get("ohlc") or []),
            "dividends": list(data.get("dividends") or []),
            "splits": list(data.get("splits") or []),
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
        dlg = getattr(self, "_alarm_dialog", None)
        if dlg is not None:
            try:
                dlg.destroy()
            except tk.TclError:
                pass
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
        self._draw_event_markers(data, pad, x2, y1, y2)
        self._draw_position_lines(info, lo, hi, rng, pad, x2, y1, y2)
        self._draw_alarm_lines(info, lo, hi, rng, pad, x2, y1, y2)

    def _draw_event_markers(self, data, pad, x2, y1, y2):
        """Grafik aralığındaki temettü (T) ve bölünme (B) işaretleri."""
        stamps = self._plot.get("stamps") or []
        if not stamps or self._plot.get("candle"):
            return
        if self.tf == "1D":
            tolerance = 3 * 3600
        elif self.tf == "1H":
            tolerance = 12 * 3600
        elif self.tf == "1A":
            tolerance = 3 * 86400
        else:
            tolerance = 12 * 86400
        lo_ts, hi_ts = min(stamps), max(stamps)
        markers = [("T", ts, AMBER) for ts, _ in data.get("dividends") or []]
        markers += [("B", ts, ACCENT) for ts, _n, _d in data.get("splits") or []]
        if not markers:
            return
        drawn = 0
        for label, ts, color in sorted(markers, key=lambda item: item[1]):
            if ts < lo_ts - tolerance or ts > hi_ts + tolerance:
                continue
            idx = min(range(len(stamps)), key=lambda i: abs(stamps[i] - ts))
            if abs(stamps[idx] - ts) > tolerance:
                continue
            x = pad + (x2 - pad) * idx / float(max(1, len(stamps) - 1))
            self.canvas.create_text(x, y1 + self.s(5), text=label,
                                    fill=color, font=("Segoe UI", 6, "bold"))
            self.canvas.create_line(x, y1 + self.s(9), x, y2 - self.s(2),
                                    fill=color, dash=(1, 4))
            drawn += 1
            if drawn >= 8:
                break

    def _on_chart_right_click(self, event):
        """Grafikte sağ tık: seviyeden veya elle fiyat girerek alarm kur."""
        if self._closed:
            return
        p = self._plot
        price = None
        if p:
            price = round_chart_price(
                chart_price_at(event.y, p["y1"], p["y2"], p["lo"], p["hi"]))
        info = self.app.last.get(self.symbol) or {}
        rules = (self.app.cfg.get("alarms") or {}).get(self.symbol) or {}
        try:
            old = getattr(self, "_chart_menu", None)
            if old is not None:
                old.destroy()
        except tk.TclError:
            pass
        menu = tk.Menu(self.win, tearoff=0, bg=MENU_BG, fg=FG,
                       activebackground=MENU_ACTIVE, activeforeground=FG,
                       bd=0)
        self._chart_menu = menu
        if price is not None:
            price_txt = fmt_money(price, info.get("currency") or "USD")
            menu.add_command(
                label="Üstünde alarm kur · %s" % price_txt,
                command=lambda: self._set_chart_alarm("above", price))
            menu.add_command(
                label="Altında alarm kur · %s" % price_txt,
                command=lambda: self._set_chart_alarm("below", price))
            menu.add_separator()
        menu.add_command(
            label="Fiyat girerek alarm kur…",
            command=lambda: self._open_alarm_dialog(price))
        if rules:
            menu.add_separator()
            menu.add_command(label="Alarmları düzenle…",
                             command=lambda: self.app.open_alarm_editor(
                                 self.symbol))
            menu.add_command(label="Alarmları kaldır",
                             command=self._clear_chart_alarms)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _set_chart_alarm(self, kind, price):
        self.app.set_chart_alarm(self.symbol, kind, price)
        self.render()

    def _clear_chart_alarms(self):
        self.app.clear_chart_alarms(self.symbol)
        self.render()

    def _open_alarm_dialog(self, price=None):
        """Grafik aralığından bağımsız olarak elle alarm fiyatı gir."""
        dlg = getattr(self, "_alarm_dialog", None)
        if dlg is not None and dlg.winfo_exists():
            dlg.deiconify()
            dlg.lift()
            dlg.focus_set()
            return dlg
        s = self.s
        dlg = tk.Toplevel(self.win)
        self._alarm_dialog = dlg
        dlg.configure(bg=CARD)
        dlg.attributes("-topmost", True)
        dlg.transient(self.win)
        dlg.title("Alarm fiyatı")
        dlg.resizable(False, False)
        try:
            dlg.iconbitmap(ICON_FILE)
        except tk.TclError:
            pass
        dark_title_bar(dlg)
        tk.Label(dlg, text="ALARM FİYATI", bg=CARD, fg=MUTED,
                 font=self.app.f_title).pack(anchor="w", padx=s(14),
                                             pady=(s(12), s(2)))
        tk.Label(dlg, text="Grafik aralığının dışında bir seviye de olabilir.",
                 bg=CARD, fg=DIM, font=self.app.f_foot,
                 anchor="w").pack(fill="x", padx=s(14), pady=(0, s(8)))
        entry = tk.Entry(dlg, bg=RAISED, fg=FG, insertbackground=FG,
                         relief="flat", font=(self.app.mono, 11),
                         justify="right", width=14, highlightthickness=1,
                         highlightbackground=ENTRY_BORDER,
                         highlightcolor=ACCENT)
        entry.pack(fill="x", padx=s(14), ipady=s(5))
        info = self.app.last.get(self.symbol) or {}
        initial = price if price is not None else _to_float(info.get("price"))
        if initial is not None:
            entry.insert(0, ("%.4f" if initial < 1 else "%.2f") % initial)
        error = tk.Label(dlg, text="", bg=CARD, fg=RED,
                         font=self.app.f_foot, anchor="w")
        error.pack(fill="x", padx=s(14), pady=(s(3), 0))

        def submit(kind):
            raw = (entry.get() or "").strip().replace(",", ".")
            value = _to_float(raw)
            if value is None or value <= 0:
                error.config(text="Geçerli, pozitif bir fiyat gir.")
                entry.focus_set()
                return
            self.app.set_chart_alarm(self.symbol, kind, value)
            self.render()
            dlg.destroy()

        buttons = tk.Frame(dlg, bg=CARD)
        buttons.pack(fill="x", padx=s(14), pady=(s(4), s(6)))
        tk.Button(buttons, text="Üstünde alarm kur", bg=ACCENT,
                  fg="#ffffff", bd=0, activebackground=ACCENT_HOVER,
                  activeforeground="#ffffff", font=("Segoe UI", 8, "bold"),
                  cursor="hand2",
                  command=lambda: submit("above")).pack(
            side="left", expand=True, fill="x", ipady=s(4))
        tk.Button(buttons, text="Altında alarm kur", bg=ACCENT,
                  fg="#ffffff", bd=0, activebackground=ACCENT_HOVER,
                  activeforeground="#ffffff", font=("Segoe UI", 8, "bold"),
                  cursor="hand2",
                  command=lambda: submit("below")).pack(
            side="left", expand=True, fill="x", padx=(s(5), 0), ipady=s(4))
        tk.Button(dlg, text="İptal", bg=BTN, fg=FG, bd=0,
                  activebackground=BTN_HOVER, activeforeground=FG,
                  font=("Segoe UI", 8), cursor="hand2",
                  command=dlg.destroy).pack(fill="x", padx=s(14),
                                            pady=(0, s(12)), ipady=s(3))
        dlg.bind("<Return>", lambda e: (submit("above"), "break")[1])
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.bind("<Destroy>", lambda e: (
            setattr(self, "_alarm_dialog", None)
            if e.widget is dlg else None))
        dlg.update_idletasks()
        w = s(330)
        h = dlg.winfo_reqheight()
        sm = ctypes.windll.user32.GetSystemMetrics
        dlg.geometry("%dx%d+%d+%d" % (w, h, sm(0) // 2 - w // 2,
                                      sm(1) // 2 - h // 2))
        entry.focus_set()
        entry.select_range(0, "end")
        return dlg

    def _draw_alarm_lines(self, info, lo, hi, rng, pad, x2, y1, y2):
        """Grafikte kayıtlı üst/alt alarm seviyelerini çiz."""
        rules = (self.app.cfg.get("alarms") or {}).get(self.symbol) or {}
        cur = info.get("currency") or "USD"
        for kind, label in (("above", "üst alarm"),
                            ("below", "alt alarm")):
            value = _to_float(rules.get(kind))
            if value is None or hi <= lo:
                continue
            if value > hi:
                self.canvas.create_text(
                    pad + self.s(2), y1 + self.s(4),
                    text="↑ %s" % fmt_money(value, cur), anchor="w",
                    fill=AMBER, font=("Segoe UI", 6, "bold"))
                continue
            if value < lo:
                self.canvas.create_text(
                    pad + self.s(2), y2 - self.s(4),
                    text="↓ %s" % fmt_money(value, cur), anchor="w",
                    fill=AMBER, font=("Segoe UI", 6, "bold"))
                continue
            y = y2 - (value - lo) / rng * (y2 - y1)
            self.canvas.create_line(pad, y, x2, y, fill=AMBER,
                                    dash=(2, 3))
            self.canvas.create_text(pad + self.s(2), y - self.s(4),
                                    text=label, anchor="w", fill=AMBER,
                                    font=("Segoe UI", 6, "bold"))

    def _draw_position_lines(self, info, lo, hi, rng, pad, x2, y1, y2):
        """Portföyde hedef ve ortalama maliyet varsa grafikte çizgi göster."""
        rec = (self.app.cfg.get("positions") or {}).get(self.symbol) or {}
        for key, label, color in (("target", "hedef", ACCENT),
                                  ("avg", "maliyet", DIM)):
            value = _to_float(rec.get(key))
            if value is None or not (lo <= value <= hi) or hi <= lo:
                continue
            y = y2 - (value - lo) / rng * (y2 - y1)
            self.canvas.create_line(pad, y, x2, y, fill=color, dash=(3, 4))
            self.canvas.create_text(pad + self.s(2), y - self.s(4),
                                    text=label, anchor="w", fill=color,
                                    font=("Segoe UI", 6))

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
        state = MARKET_STATE_LABEL.get(
            (info.get("market_state") or "").upper(), "")
        event_txt = ""
        splits = info.get("splits") or []
        divs = info.get("dividends") or []
        if splits:
            _ts, num, den = splits[-1]
            event_txt = "B %g:%g" % (num, den)
        elif divs:
            event_txt = "T %.2f" % divs[-1][1]
        meta_txt = " · ".join(
            x for x in (info.get("exchange"), cur, state, event_txt) if x)
        c.create_text(pad, s(381), text=meta_txt or "—", anchor="w",
                      fill=DIM, font=("Segoe UI", 7))
        when = info.get("quote_ts")
        if when:
            try:
                stamp = datetime.datetime.fromtimestamp(float(when))
                right_txt = (stamp.strftime("%H:%M")
                             if stamp.date() == datetime.date.today()
                             else stamp.strftime("%d.%m %H:%M"))
            except (OverflowError, OSError, ValueError):
                right_txt = "—"
        else:
            right_txt = datetime.datetime.now().strftime("%H:%M")
        c.create_text(x2, s(381), text=right_txt, anchor="e", fill=DIM,
                      font=("Segoe UI", 7))

class StockWidget:
    def __init__(self):
        self.S = _init_dpi()
        self.cfg = load_config()
        i18n.set_language(self.cfg.get("language", "tr"))
        apply_palette(self.cfg["theme"])
        self.alpha = float(self.cfg["opacity"])
        self.density = self.cfg["density"]
        # Açılışta kart boş kalmasın: son başarılı fiyatlar anında gösterilir.
        self.last, self._snap_ts = load_snapshot(self.cfg["symbols"])
        self.history = load_history()
        self.alarm_history = load_alarm_history()
        self._alarm_mute_until = 0.0
        self.offline = False
        self.stale = initial_stale(bool(self.last), self.cfg)  # canlı yanıt gelene kadar
        self._hover_row = None
        self._selected_idx = 0
        self._view_symbols = list(self.cfg["symbols"])
        self._render_keys = {}
        self._spark_cache = {}
        self._snapshot_blob = None
        self._alarm_state = {}
        self._alarms_dlg = None
        self._alarm_msg = ""
        self._alarm_until = 0.0
        self._market_tip = None
        self._market_detail = ""

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

        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0,
                                takefocus=1)
        self.canvas.pack(fill="both", expand=True)

        self.queue = queue.Queue()
        self.wake = threading.Event()
        self.stop_flag = threading.Event()
        self.tray_icon = None
        self._editor = None
        self._detail = None
        self._moved = False
        self._px = 0
        self._py = 0
        self._row_photos = {}
        self._chart_photo = None
        self._data_ts = newest_quote_ts(self.last, self._snap_ts)
        self._force_refresh = False
        self._update_busy = False
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
        self._record_history()

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
        self.canvas.tag_bind("privacy_btn", "<Enter>",
                             lambda e: self._set_privacy_color(ACCENT))
        self.canvas.tag_bind("privacy_btn", "<Leave>",
                             lambda e: self._set_privacy_color(MUTED))
        self.canvas.tag_bind("privacy_btn", "<Button-1>",
                             lambda e: self.root.after(
                                 10, self.toggle_portfolio_privacy))
        self.canvas.tag_bind("market_dot", "<Enter>",
                             self._show_market_tip)
        self.canvas.tag_bind("market_dot", "<Leave>",
                             lambda e: self._hide_market_tip())
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        self.root.bind("<F5>", lambda e: self._header_refresh())
        self.root.bind("<Up>", lambda e: self._select_relative(-1))
        self.root.bind("<Down>", lambda e: self._select_relative(1))
        self.root.bind("<Return>", self._activate_selected)
        self.root.bind("<Escape>", lambda e: self.close_detail())
        self.root.bind("<Control-Right>",
                       lambda e: self._focus_step(1))
        self.root.bind("<Control-Left>",
                       lambda e: self._focus_step(-1))

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
        else:
            # Günde en fazla 1 GitHub isteği; sessizce yalnızca yenilik varsa bildirir.
            self.root.after(6000, lambda: self.check_updates(silent=True))

    # ---------- personalization ----------

    def _set_density(self):
        self.ROW_H = self.s(46 if self.density == "normal" else 40)
        self._row_f = self.ROW_H / float(self.s(46))

    def ro(self, v):
        return int(round(v * self.S * self._row_f))

    # ---------- ordering / shortcuts ----------

    def _ordered_symbols(self):
        """Görünüm sırası; cfg'deki elle sıralama her zaman korunur."""
        symbols = list(self.cfg.get("symbols") or [])
        focus = self.cfg.get("focus_symbol") or ""
        if self.cfg.get("focus_mode") and focus in symbols:
            return [focus]
        group_filter = self.cfg.get("group_filter") or ""
        if group_filter:
            groups = self.cfg.get("symbol_groups") or {}
            filtered = [s for s in symbols if groups.get(s) == group_filter]
            if filtered:
                symbols = filtered
        mode = self.cfg.get("sort_mode", "manual")
        if mode == "symbol":
            return sorted(symbols)
        if mode == "change":
            def key(sym):
                pct = _to_float((self.last.get(sym) or {}).get("change_pct"))
                return pct if pct is not None else -math.inf
            return sorted(symbols, key=key, reverse=True)
        if mode == "value":
            def key(sym):
                rec = (self.cfg.get("positions") or {}).get(sym) or {}
                qty = _to_float(rec.get("qty")) or 0.0
                price = _to_float((self.last.get(sym) or {}).get("price"))
                return qty * price if qty > 0 and price is not None else -1.0
            return sorted(symbols, key=key, reverse=True)
        return symbols

    def set_sort_mode(self, mode):
        if mode not in ("manual", "change", "symbol", "value"):
            return
        self.cfg["sort_mode"] = mode
        self.sort_var.set(mode)
        save_config(self.cfg)
        self.build_ui()

    def _refresh_group_menu(self):
        if not hasattr(self, "group_menu"):
            return
        self.group_menu.delete(0, "end")
        self.group_menu.add_radiobutton(
            label="Tümü", value="", variable=self.group_var,
            command=lambda: self.set_group_filter(""))
        names = sorted({g for g in (self.cfg.get("symbol_groups") or {}).values()
                        if g})
        for name in names:
            self.group_menu.add_radiobutton(
                label=name, value=name, variable=self.group_var,
                command=lambda n=name: self.set_group_filter(n))

    def set_group_filter(self, name):
        self.cfg["group_filter"] = name if isinstance(name, str) else ""
        self.group_var.set(self.cfg["group_filter"])
        save_config(self.cfg)
        self.build_ui()
        self._restore_position()

    def toggle_focus(self):
        if self.cfg.get("focus_mode"):
            self.cfg["focus_mode"] = False
        else:
            sym = (self.cfg.get("focus_symbol")
                   or (self._view_symbols[0] if self._view_symbols else ""))
            if not sym:
                self.focus_var.set(False)
                return
            self.cfg["focus_symbol"] = sym
            self.cfg["focus_mode"] = True
        self.focus_var.set(bool(self.cfg.get("focus_mode")))
        save_config(self.cfg)
        self.build_ui()
        self._restore_position()

    def set_focus_symbol(self, sym):
        if sym not in (self.cfg.get("symbols") or []):
            return
        self.cfg["focus_symbol"] = sym
        self.cfg["focus_mode"] = True
        self.focus_var.set(True)
        save_config(self.cfg)
        self.build_ui()
        self._restore_position()

    def _focus_step(self, delta):
        symbols = self.cfg.get("symbols") or []
        if not symbols:
            return
        cur = self.cfg.get("focus_symbol") or ""
        idx = symbols.index(cur) if cur in symbols else 0
        self.set_focus_symbol(symbols[(idx + delta) % len(symbols)])

    def mute_alarms(self, minutes=60):
        self._alarm_mute_until = time.time() + max(1, int(minutes)) * 60
        log.info("alarmlar %d dakika susturuldu", minutes)
        self._alarm_msg = "Alarmlar %d dakika susturuldu" % minutes
        self._alarm_until = time.time() + 5
        self._update_status()

    def unmute_alarms(self):
        self._alarm_mute_until = 0.0
        log.info("alarm susturma kaldırıldı")
        self._alarm_msg = "Alarm susturma kaldırıldı"
        self._alarm_until = time.time() + 5
        self._update_status()

    def _move_symbol(self, sym, delta):
        symbols = self.cfg.get("symbols") or []
        if sym not in symbols:
            return
        old = symbols.index(sym)
        new = max(0, min(len(symbols) - 1, old + delta))
        if old == new:
            return
        symbols.insert(new, symbols.pop(old))
        if self.cfg.get("sort_mode") != "manual":
            self.cfg["sort_mode"] = "manual"
            self.sort_var.set("manual")
        save_config(self.cfg)
        self.build_ui()

    def _select_relative(self, delta):
        symbols = self._view_symbols
        if not symbols:
            return
        idx = max(0, min(len(symbols) - 1, self._selected_idx + delta))
        self._selected_idx = idx
        self._on_leave()
        self._hover_row = idx
        hover_ids = self.canvas.find_withtag("hover")
        if idx < len(hover_ids):
            self.canvas.itemconfig(hover_ids[idx], fill=HOVER)

    def _activate_selected(self, event=None):
        if 0 <= self._selected_idx < len(self._view_symbols):
            self.open_detail(self._view_symbols[self._selected_idx])

    def copy_text(self, text):
        """Panoya kopyala; boş değer için sessizce hiçbir şey yapma."""
        if text in (None, ""):
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(text))
        except tk.TclError:
            pass

    @staticmethod
    def open_yahoo(sym):
        webbrowser.open("https://finance.yahoo.com/quote/"
                        + urllib.parse.quote(sym, safe=""))

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0, bg=MENU_BG, fg=FG,
                    activebackground=MENU_ACTIVE, activeforeground=FG, bd=0)
        self.menu = m
        m.add_command(label="Ayarlar…", command=self.open_settings_editor)
        m.add_separator()
        m.add_command(label="Sembol ekle / çıkar…",
                      command=self.open_symbol_editor)
        m.add_command(label="Gruplar…", command=self.open_group_editor)
        m.add_command(label="Portföy…", command=self.open_portfolio_editor)
        m.add_command(label="Alarmlar…", command=self.open_alarm_editor)
        m.add_command(label="Alarmları 1 saat sustur",
                      command=lambda: self.mute_alarms(60))
        m.add_command(label="Alarm susturmayı kaldır",
                      command=self.unmute_alarms)
        self.focus_var = tk.BooleanVar(
            value=bool(self.cfg.get("focus_mode")))
        m.add_checkbutton(label="Odak modu", variable=self.focus_var,
                          command=self.toggle_focus)
        self.group_var = tk.StringVar(
            value=self.cfg.get("group_filter") or "")
        self.group_menu = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=FG,
                                  activebackground=MENU_ACTIVE)
        self._refresh_group_menu()
        m.add_cascade(label="Grup", menu=self.group_menu)
        self.remove_menu = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=FG,
                                   activebackground=MENU_ACTIVE)
        m.add_cascade(label="Hızlı çıkar", menu=self.remove_menu)
        self.sort_var = tk.StringVar(value=self.cfg.get("sort_mode", "manual"))
        self.sort_menu = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=FG,
                                 activebackground=MENU_ACTIVE)
        for label, mode in (("Elle", "manual"), ("Değişim %", "change"),
                            ("Sembol", "symbol"), ("Portföy değeri", "value")):
            self.sort_menu.add_radiobutton(
                label=label, value=mode, variable=self.sort_var,
                command=lambda v=mode: self.set_sort_mode(v))
        m.add_cascade(label="Sıralama", menu=self.sort_menu)
        self.privacy_var = tk.BooleanVar(
            value=bool(self.cfg.get("hide_portfolio_amount")))
        m.add_checkbutton(
            label="Portföy miktarını gizle", variable=self.privacy_var,
            command=lambda: self.set_portfolio_privacy(
                self.privacy_var.get()))
        self.row_menu = tk.Menu(self.root, tearoff=0, bg=MENU_BG, fg=FG,
                                activebackground=MENU_ACTIVE,
                                activeforeground=FG, bd=0)
        m.add_separator()
        m.add_command(label="Yenile", command=self.refresh_now)
        self._menu_update_index = m.index("end") + 1
        m.add_command(label="Güncelleme denetle…", command=self.check_updates)
        m.add_separator()
        m.add_command(label="Gizle", command=self.hide_window)
        m.add_command(label="Çıkış", command=self.exit_app)

    def _style_menus(self):
        for mm in (getattr(self, "menu", None), self.remove_menu,
                   getattr(self, "sort_menu", None),
                   getattr(self, "group_menu", None),
                   getattr(self, "row_menu", None)):
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

    def set_night_pause(self, value):
        self.cfg["night_pause"] = bool(value)
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
        return _rel_seconds(time.time() - self._data_ts)

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
        if not isinstance(pos, dict):
            return False
        for rec in pos.values():
            if not isinstance(rec, dict):
                continue
            qty = _to_float(rec.get("qty"))
            if qty is not None and qty > 0:
                return True
        return False

    def _portfolio_stats(self):
        pos = self.cfg.get("positions") or {}
        extended = self.cfg.get("extended_hours", True)
        val = cost = day = 0.0
        ok = False
        cur = None
        mixed = False
        for sym, p in pos.items():
            if not isinstance(p, dict):
                continue
            qty = _to_float(p.get("qty"))
            avg = _to_float(p.get("avg"))
            if qty is None or avg is None:
                continue
            info = self.last.get(sym)
            if qty <= 0 or not info:
                continue
            price = display_price(info, extended)
            ref = reference_close(info, extended)
            if price is None:
                continue
            ok = True
            sym_cur = info.get("currency")
            if cur is None:
                cur = sym_cur
            elif sym_cur and cur and sym_cur != cur:
                mixed = True
            val += qty * price
            cost += qty * avg
            if ref is not None:
                day += qty * (price - ref)
        return ok, val, cost, day, cur, mixed

    def _portfolio_by_currency(self):
        """Para birimi başına toplamlar; karışık portföyde yanlış toplamayı önler."""
        out = {}
        extended = self.cfg.get("extended_hours", True)
        for sym, rec in (self.cfg.get("positions") or {}).items():
            info = self.last.get(sym)
            if not isinstance(rec, dict) or not info:
                continue
            qty = _to_float(rec.get("qty"))
            avg = _to_float(rec.get("avg"))
            price = display_price(info, extended)
            ref = reference_close(info, extended)
            if qty is None or qty <= 0 or avg is None or price is None:
                continue
            cur = info.get("currency") or "USD"
            bucket = out.setdefault(cur, {"value": 0.0, "cost": 0.0,
                                          "day": 0.0})
            bucket["value"] += qty * price
            bucket["cost"] += qty * avg
            if ref is not None:
                bucket["day"] += qty * (price - ref)
        return out

    def _draw_portfolio(self, y):
        c = self.canvas
        w = self.W
        mid = y + self.s(9)
        self._round_rect(self.PAD - self.s(4), y,
                         w - self.PAD + self.s(4), y + self.s(18),
                         self.s(9), fill=RAISED, tags=("pf",))
        c.create_text(self.PAD, mid, text="Portföy", anchor="w", fill=MUTED,
                      font=("Segoe UI", 7), tags=("pf",))
        ok, val, cost, day, cur, mixed = self._portfolio_stats()
        if not ok:
            c.create_text(w - self.PAD, mid, text="adet gir", anchor="e",
                          fill=DIM, font=("Segoe UI", 7), tags=("pf",))
            return
        hidden = bool(self.cfg.get("hide_portfolio_amount"))
        if mixed:
            # Farklı para birimlerini toplamak yanlış sonuç verir; ayrı göster.
            totals = [fmt_money(v["value"], ccode)
                      for ccode, v in sorted(self._portfolio_by_currency().items())]
            text = " · ".join(totals[:2])
            if len(totals) > 2:
                text += " +%d" % (len(totals) - 2)
            c.create_text(w - self.PAD, mid,
                          text="••••" if hidden else (text or "farklı para birimi"),
                          anchor="e", fill=AMBER if not hidden else FG,
                          font=(self.mono, 7, "bold"), tags=("pf",))
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
        if hidden:
            label = "•••• / ••••" if self.cfg.get("portfolio_show_cost") else "••••"
            font = (self.mono, 8, "bold")
        elif self.cfg.get("portfolio_show_cost"):
            label = "%s / %s" % (fmt_money(val, cur), fmt_money(cost, cur))
            font = (self.mono, 7, "bold")
        else:
            label = fmt_money(val, cur)
            font = (self.mono, 8, "bold")
        c.create_text(px1 - self.s(8), mid, text=label,
                      anchor="e", fill=FG, font=font, tags=("pf",))

    def _update_portfolio(self):
        if getattr(self, "_pf_y", None) is None:
            return
        try:
            self.canvas.delete("pf")
            self._draw_portfolio(self._pf_y)
        except tk.TclError:
            pass

    def _set_privacy_color(self, color):
        try:
            self.canvas.itemconfig(self.privacy_id, fill=color)
        except (tk.TclError, AttributeError):
            pass

    def _update_privacy_button(self):
        try:
            self.canvas.itemconfig(
                self.privacy_id,
                text="◌" if self.cfg.get("hide_portfolio_amount") else "◉")
        except (tk.TclError, AttributeError):
            pass

    def set_portfolio_privacy(self, hidden):
        self.cfg["hide_portfolio_amount"] = bool(hidden)
        save_config(self.cfg)
        var = getattr(self, "privacy_var", None)
        if var is not None:
            var.set(bool(hidden))
        self._update_privacy_button()
        self._update_portfolio()

    def toggle_portfolio_privacy(self):
        self.set_portfolio_privacy(
            not self.cfg.get("hide_portfolio_amount"))

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
        n = len(getattr(self, "_view_symbols", None)
                or self.cfg["symbols"])
        extra = self.s(26) if self._has_portfolio() else 0
        return (self.HEADER_H + n * self.ROW_H + self.s(30) + extra)

    # ---------- UI ----------

    def build_ui(self):
        c = self.canvas
        c.delete("all")
        self.items = {}
        self.row_bounds = []
        self._view_symbols = self._ordered_symbols()
        self._render_keys.clear()
        self._spark_cache.clear()
        self._row_photos.clear()
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
        self.privacy_id = c.create_text(
            W - self.PAD - self.s(39), self.s(16),
            text="◌" if self.cfg.get("hide_portfolio_amount") else "◉",
            anchor="center", fill=MUTED, font=("Segoe UI Symbol", 9),
            tags=("privacy_btn",))
        time_x = W - self.PAD - self.s(53)
        dot_x = time_x - self.s(30)
        self.dot_id = c.create_oval(dot_x, self.s(14),
                                    dot_x + self.s(5), self.s(19),
                                    fill=MUTED, outline="",
                                    tags=("market_dot",))
        self.phase_id = c.create_text(dot_x - self.s(5), self.s(17), text="",
                                      anchor="e", fill=AMBER,
                                      font=("Segoe UI", 6, "bold"))
        self.time_id = c.create_text(time_x, self.s(17), text="--:--",
                                     anchor="e", fill=MUTED,
                                     font=self.f_foot)
        for i, sym in enumerate(self._view_symbols):
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
        fy = self._row_y(len(self._view_symbols))
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
        W, H = self.W, self._row_height()
        vx, vy, vw, vh = virtual_screen()
        x = self.cfg.get("x")
        y = self.cfg.get("y")
        if x is None:
            x = vx + vw - W - self.s(24)
        if y is None:
            y = vy + vh - H - self.s(60)
        x, y = clamp_to_screen(x, y, W, H)
        self.cfg["x"], self.cfg["y"] = x, y
        self.root.geometry("%dx%d+%d+%d" % (W, H, x, y))

    def _render_row(self, sym, info):
        c = self.canvas
        it = self.items.get(sym)
        if not it:
            return
        spark = info.get("spark") or []
        flags = (getattr(self, "_alarm_state", {}).get(sym) or {})
        alarm_flags = tuple(sorted(k for k, v in flags.items() if v))
        pos_rec = (self.cfg.get("positions") or {}).get(sym) or {}
        pos_key = (_to_float(pos_rec.get("qty")), _to_float(pos_rec.get("avg")))
        # Değişmeyen satırı yeniden çizmek yerine mevcut canvas öğelerini koru.
        key = (info.get("price"), info.get("change_pct"),
               info.get("ext_session"), info.get("ext_price"),
               info.get("ext_change_pct"), info.get("name"),
               info.get("currency"), self.offline,
               getattr(self, "stale", False), alarm_flags, pos_key,
               tuple(spark))
        keys = getattr(self, "_render_keys", None)
        if keys is None:
            keys = self._render_keys = {}
        if keys.get(sym) == key:
            return
        keys[sym] = key
        c.delete(it["tag"])
        y = it["y"]
        pct = info["change_pct"]
        up = pct >= 0
        col = GREEN if up else RED
        bg = GREEN_DIM if up else RED_DIM
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
        # sparkline rozetin (PÖ/PS dahil) rengini izler
        spark_col = col
        price_txt = fmt_money(price_val, info.get("currency"))
        price_col = (DIM if getattr(self, "stale", False)
                     else MUTED if self.offline else FG)
        c.itemconfig(it["price"], text=price_txt, fill=price_col)
        # değişim rozeti (trend oklu)
        tw = self.font_pct.measure(txt)
        ph = self.ro(17)
        pw = tw + self.s(14)
        x2 = self.W - self.PAD
        x1 = x2 - pw
        y1 = y + self.ro(26)
        self._round_rect(x1, y1, x2, y1 + ph, ph // 2, fill=bg,
                         tags=(it["tag"],))
        c.create_text((x1 + x2) / 2.0, y1 + ph / 2.0, text=txt, fill=col,
                      font=self.f_pct, tags=(it["tag"],))
        # Aktif alarm: renkten bağımsız küçük elmas işareti
        if alarm_flags:
            c.create_text(self.PAD + self.s(64), y + self.ro(12), text="◆",
                          fill=AMBER, font=("Segoe UI", 6),
                          tags=(it["tag"],))
        # şirket adı ve (varsa) pozisyon K/Z yüzdesi
        name = info.get("name") or ""
        nx = self.PAD + self.s(78)
        pl_txt = ""
        pl_col = DIM
        qty = _to_float(pos_rec.get("qty"))
        avg = _to_float(pos_rec.get("avg"))
        base_price = price_val   # PÖ/PS açıkken gösterilen (seans dışı) fiyat
        if qty and qty > 0 and avg and avg > 0 and base_price is not None:
            pl_pct = (base_price / avg - 1.0) * 100.0
            pl_txt = "%+.1f%%" % pl_pct
            pl_col = GREEN if pl_pct >= 0 else RED
        pl_w = self.font_name.measure(pl_txt) + self.s(6) if pl_txt else 0
        avail = x1 - nx - self.s(6) - pl_w
        if name and avail > self.s(14):
            txtname = self._ellipsize(name, self.font_name, avail)
            if txtname:
                c.create_text(nx, y1 + ph / 2.0, text=txtname, anchor="w",
                              fill=DIM, font=self.f_name,
                              tags=(it["tag"],))
        if pl_txt:
            c.create_text(x1 - self.s(6), y1 + ph / 2.0, text=pl_txt,
                          anchor="e", fill=pl_col, font=self.f_name,
                          tags=(it["tag"],))
        # sparkline (PIL ile anti-aliased; aynı seri için PhotoImage önbelleği)
        sw, sh = self.s(72), self.ro(16)
        if len(spark) > 1:
            sx1, sy1 = self.PAD, y + self.ro(25)
            if PIL_AVAILABLE:
                cache = getattr(self, "_spark_cache", None)
                if cache is None:
                    cache = self._spark_cache = {}
                cache_key = (tuple(spark), sw, sh, spark_col)
                photo = cache.get(cache_key)
                if photo is None:
                    img = render_spark(spark, sw, sh, spark_col,
                                       fill=spark_col)
                    photo = ImageTk.PhotoImage(img, master=self.root)
                    if len(cache) >= 64:
                        cache.clear()
                    cache[cache_key] = photo
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

    def _check_alarms(self):
        """Yeni fiyatlarla eşikleri denetle; bildirimleri tek özette topla."""
        events = []
        for sym, rule in (self.cfg.get("alarms") or {}).items():
            info = self.last.get(sym)
            if not info:
                continue
            use_ext = (self.cfg.get("extended_hours", True)
                       and rule.get("extended", False))
            position = (self.cfg.get("positions") or {}).get(sym)
            events.extend(evaluate_alarm(sym, info, rule, self._alarm_state,
                                         use_ext, position))
        if events:
            self._notify_alarms(events)
        return events

    def _notify_alarms(self, events):
        for message in events:
            log.warning("alarm: %s", message)
        text = events[0]
        if len(events) > 1:
            text += " (+%d alarm)" % (len(events) - 1)
        self.alarm_history = append_alarm_history(self.alarm_history, events)
        save_alarm_history(self.alarm_history)
        now = datetime.datetime.now()
        quiet = (self.cfg.get("quiet_enabled")
                 and is_quiet_time(now, self.cfg.get("quiet_start", 23),
                                   self.cfg.get("quiet_end", 8)))
        muted = getattr(self, "_alarm_mute_until", 0) > time.time()
        if quiet or muted:
            log.info("alarm bildirimi sessize alındı")
            return
        self._alarm_msg = text
        self._alarm_until = time.time() + 60
        self._update_status()
        icon = self.tray_icon
        if not icon:
            return
        try:
            icon.notify(text, "StockWidget alarmı")
        except Exception:
            log.info("alarm tepsi bildirimi gösterilemedi")

    def _record_history(self):
        """Portföyün günlük toplamını (para birimi başına) yerelde sakla."""
        totals = self._portfolio_by_currency()
        if not totals:
            return
        updated = record_history(getattr(self, "history", []), totals)
        old = getattr(self, "history", [])
        if updated != old:
            self.history = updated
            save_history(updated)

    def _show_market_tip(self, event=None):
        text = getattr(self, "_market_detail", "")
        if not text:
            return
        self._hide_market_tip()
        try:
            tip = tk.Toplevel(self.root)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            tip.configure(bg=MENU_BG, highlightthickness=1,
                          highlightbackground=DIVIDER)
            tk.Label(tip, text=text, bg=MENU_BG, fg=FG,
                     font=("Segoe UI", 8), justify="left").pack(
                padx=self.s(8), pady=self.s(5))
            tip.update_idletasks()
            x = self.root.winfo_rootx() + self.W - tip.winfo_reqwidth() - self.s(8)
            y = self.root.winfo_rooty() + self.s(24)
            tip.geometry("+%d+%d" % (max(0, x), y))
            self._market_tip = tip
        except tk.TclError:
            self._market_tip = None

    def _hide_market_tip(self):
        tip = getattr(self, "_market_tip", None)
        self._market_tip = None
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass

    def _update_status(self):
        c = self.canvas
        phase, label, details = self._market_summary()
        self._market_detail = "\n".join(details)
        if self.offline or getattr(self, "stale", False):
            dot = AMBER
        elif phase == "regular":
            dot = GREEN
        elif phase in ("pre", "post"):
            dot = AMBER
        else:
            dot = DIM
        try:
            c.itemconfig(self.dot_id, fill=dot)
            c.itemconfig(self.phase_id, text=label)
            c.itemconfig(self.time_id, text=datetime.datetime.now().strftime("%H:%M"))
            if (getattr(self, "_alarm_until", 0) > time.time()
                    and self._alarm_msg):
                status = "⚠ " + self._alarm_msg[:46]
            elif self.offline:
                status = "çevrimdışı · deneniyor…"
            elif getattr(self, "stale", False):
                status = "önbellek · %s" % self._rel_time()
            else:
                age = (time.time() - self._data_ts) if self._data_ts else None
                status = data_age_text(age, phase)
            c.itemconfig(self.upd_id, text=status)
        except (tk.TclError, AttributeError):
            pass

    def apply_data(self, results, offline):
        self.offline = offline
        if results:
            # Durum satırı istek zamanını değil verinin saatini göstersin:
            # hafta sonu/tatilde aynı Cuma barı tekrar gelse bile "az önce"
            # yazılmaz. bar_ts son 5 dk barı, quote_ts regularMarketTime.
            self._data_ts = newest_quote_ts(results, time.time())
            self.stale = False
        for sym, info in results.items():
            self.last[sym] = info
        if results:
            # Sembol listesinden çıkarılanlar anlık görüntüye de yazılmasın.
            keep = [s for s in (self.cfg.get("symbols") or []) if s in self.last]
            if len(keep) != len(self.last):
                self.last = {s: self.last[s] for s in keep}
            self._check_alarms()
            if (self.cfg.get("sort_mode") != "manual"
                    and self._ordered_symbols() != self._view_symbols):
                self.build_ui()     # sıralama değişti; satırlar yer değiştirdi
            else:
                for sym in results:
                    self._render_row(sym, self.last[sym])
            # Aynı fiyat paketi için diske yeniden yazma (SSD/GC dostu).
            blob = json.dumps(self.last, sort_keys=True,
                              separators=(",", ":"))
            if blob != getattr(self, "_snapshot_blob", None):
                save_snapshot(self.last)
                self._snapshot_blob = blob
        if offline:
            # Çevrimdışıyken başarısız satırların fiyatını da soluklaştır
            for sym, info in self.last.items():
                if sym not in results:
                    self._render_row(sym, info)
        self._update_status()
        self._update_portfolio()
        self._record_history()
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
            x, y = clamp_to_screen(x, y, self.W, self.root.winfo_height())
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
                self._selected_idx = idx
                self.open_detail(self._view_symbols[idx])

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
        if idx is not None:
            self._selected_idx = idx
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

    def _on_leave(self, event=None):
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
        idx = self._row_index_at(event.y)
        menu = self.menu
        if idx is not None and idx < len(self._view_symbols):
            menu = self._build_row_menu(self._view_symbols[idx])
        else:
            self._refresh_remove_menu()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _build_row_menu(self, sym):
        """Satır sağ tık menüsü: alarm, elle sıralama, kopyalama, Yahoo."""
        m = self.row_menu
        m.delete(0, "end")
        m.add_command(label="%s · Alarm kur…" % sym,
                      command=lambda: self.open_alarm_editor(sym))
        rec = (self.cfg.get("positions") or {}).get(sym) or {}
        if rec.get("target"):
            m.add_command(
                label="Hedef fiyata alarm kur (%s)"
                      % fmt_money(rec["target"],
                                  (self.last.get(sym) or {}).get("currency")),
                command=lambda: self._set_target_alarm(sym))
        if self.cfg.get("focus_mode"):
            m.add_command(label="Odak modundan çık",
                          command=self.toggle_focus)
        else:
            m.add_command(label="Sadece bunu göster",
                          command=lambda: self.set_focus_symbol(sym))
        symbols = self.cfg.get("symbols") or []
        pos = symbols.index(sym) if sym in symbols else -1
        m.add_command(label="Yukarı taşı",
                      state="normal" if pos > 0 else "disabled",
                      command=lambda: self._move_symbol(sym, -1))
        m.add_command(label="Aşağı taşı",
                      state="normal" if 0 <= pos < len(symbols) - 1
                      else "disabled",
                      command=lambda: self._move_symbol(sym, 1))
        m.add_separator()
        m.add_command(label="Sembolü kopyala",
                      command=lambda: self.copy_text(sym))
        info = self.last.get(sym) or {}
        price, _ = alarm_quote(info, self.cfg.get("extended_hours", True))
        if price is not None:
            m.add_command(label="Fiyatı kopyala",
                          command=lambda: self.copy_text(
                              fmt_money(price, info.get("currency"))))
        m.add_command(label="Yahoo Finance'te aç",
                      command=lambda: self.open_yahoo(sym))
        if rec.get("target"):
            m.add_command(label="Hedef: %s" % fmt_money(
                rec["target"], info.get("currency")), state="disabled")
        if rec.get("note"):
            m.add_command(label="Not: %s" % rec["note"], state="disabled")
        m.add_separator()
        # Satır sağ tık menüsünde de ana uygulama pencereleri erişilebilir
        # olsun; yoksa Ayarlar yalnızca boş alana sağ tıkta kalıyordu.
        m.add_command(label="Ayarlar…", command=self.open_settings_editor)
        m.add_command(label="Semboller…", command=self.open_symbol_editor)
        m.add_command(label="Portföy…", command=self.open_portfolio_editor)
        m.add_command(label="Gruplar…", command=self.open_group_editor)
        m.add_separator()
        m.add_command(label="Listeden çıkar",
                      command=lambda: self.remove_symbol(sym))
        return m

    def _set_target_alarm(self, sym):
        rec = (self.cfg.get("positions") or {}).get(sym) or {}
        target = _to_float(rec.get("target"))
        if target is None or target <= 0:
            return
        alarms = dict(self.cfg.get("alarms") or {})
        rule = dict(alarms.get(sym) or {})
        rule["above"] = target
        rule.pop("profit", None)
        rule.pop("loss", None)
        alarms[sym] = rule
        self.cfg["alarms"] = clean_alarms(alarms)
        save_config(self.cfg)
        self._alarm_state.pop(sym, None)
        self.build_ui()
        log.info("%s için hedef alarmı kuruldu: %s", sym, target)

    def set_chart_alarm(self, sym, kind, price):
        self.cfg["alarms"] = set_alarm_level(
            self.cfg.get("alarms"), sym, kind, price)
        save_config(self.cfg)
        self._alarm_state.pop(sym, None)
        getattr(self, "_render_keys", {}).pop(sym, None)
        info = self.last.get(sym)
        if info:
            self._render_row(sym, info)
        log.info("%s grafik alarmı %s: %s", sym, kind, price)

    def clear_chart_alarms(self, sym):
        self.cfg["alarms"] = clear_alarm_level(
            self.cfg.get("alarms"), sym)
        save_config(self.cfg)
        self._alarm_state.pop(sym, None)
        getattr(self, "_render_keys", {}).pop(sym, None)
        info = self.last.get(sym)
        if info:
            self._render_row(sym, info)
        log.info("%s grafik alarmları kaldırıldı", sym)

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
            sym = clean_symbol(entry.get())
            if not sym:
                status.config(text="Geçerli bir ticker yaz (örn. AAPL).", fg=AMBER)
                return
            if sym in self.cfg["symbols"]:
                status.config(text="%s zaten listede." % sym, fg=AMBER)
                return
            if len(self.cfg["symbols"]) >= MAX_SYMBOLS:
                status.config(text="Liste dolu (en fazla %d sembol)." % MAX_SYMBOLS,
                              fg=AMBER)
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

    # ---------- group editor ----------

    def open_group_editor(self):
        dlg = getattr(self, "_groups_dlg", None)
        if dlg is not None and dlg.winfo_exists():
            dlg.deiconify()
            dlg.lift()
            dlg.focus_set()
            return dlg
        s = self.s
        dlg = tk.Toplevel(self.root)
        self._groups_dlg = dlg
        dlg.configure(bg=CARD)
        dlg.attributes("-topmost", True)
        dlg.title("Gruplar")
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        try:
            dlg.iconbitmap(ICON_FILE)
        except tk.TclError:
            pass
        dark_title_bar(dlg)
        tk.Label(dlg, text="SEMBOL GRUPLARI", bg=CARD, fg=MUTED,
                 font=self.f_title).pack(anchor="w", padx=s(18),
                                         pady=(s(14), s(2)))
        tk.Label(dlg, text="Grup adı yaz; boş bırakılan sembol grupsuz kalır. "
                           "Menüdeki Grup filtresinden seçebilirsin.",
                 bg=CARD, fg=DIM, font=self.f_foot, justify="left",
                 wraplength=s(320)).pack(anchor="w", padx=s(18),
                                         pady=(0, s(8)))
        holder = tk.Frame(dlg, bg=CARD)
        holder.pack(fill="both", expand=True, padx=s(18))
        cv = tk.Canvas(holder, bg=CARD, highlightthickness=0, bd=0,
                       height=s(330))
        cv.pack(side="left", fill="both", expand=True)
        vs = tk.Scrollbar(holder, orient="vertical", command=cv.yview,
                          width=s(9), bg=CARD, troughcolor=CARD, bd=0,
                          relief="flat", activebackground=BTN,
                          highlightthickness=0)
        table = tk.Frame(cv, bg=CARD)
        win = cv.create_window((0, 0), window=table, anchor="nw")
        cv.configure(yscrollcommand=vs.set)
        table.bind("<Configure>", lambda e: cv.configure(
            scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        vs.pack(side="right", fill="y")
        entries = {}
        groups = self.cfg.get("symbol_groups") or {}
        for idx, sym in enumerate(self.cfg.get("symbols") or []):
            row = tk.Frame(table, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=sym, bg=CARD, fg=FG, font=self.f_sym,
                     width=10, anchor="w").pack(side="left")
            e = tk.Entry(row, bg=RAISED, fg=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 9),
                         highlightthickness=1,
                         highlightbackground=ENTRY_BORDER,
                         highlightcolor=ACCENT)
            if groups.get(sym):
                e.insert(0, groups[sym])
            e.pack(side="left", fill="x", expand=True, ipady=s(3),
                   padx=(s(6), 0))
            entries[sym] = e
        status = tk.Label(dlg, text="", bg=CARD, fg=DIM, font=self.f_foot,
                          anchor="w")
        status.pack(fill="x", padx=s(18), pady=(s(6), 0))

        def save(event=None):
            out = {}
            for sym, entry in entries.items():
                name = (entry.get() or "").strip()
                if name:
                    out[sym] = name[:24]
            self.cfg["symbol_groups"] = clean_symbol_groups(out)
            names = set(self.cfg["symbol_groups"].values())
            if self.cfg.get("group_filter") not in names:
                self.cfg["group_filter"] = ""
                self.group_var.set("")
            save_config(self.cfg)
            self._refresh_group_menu()
            self.build_ui()
            self._restore_position()
            status.config(text="Kaydedildi · %d grup"
                               % len(names), fg=GREEN)

        footer = tk.Frame(dlg, bg=CARD)
        footer.pack(fill="x", padx=s(18), pady=(s(6), s(12)))
        tk.Button(footer, text="Kaydet", bg=ACCENT, fg="#ffffff", bd=0,
                  activebackground=ACCENT_HOVER, activeforeground="#ffffff",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  command=save).pack(side="right", ipadx=s(22), ipady=s(4))
        tk.Button(footer, text="Kapat", bg=BTN, fg=FG, bd=0,
                  activebackground=BTN_HOVER, activeforeground=FG,
                  font=("Segoe UI", 9), cursor="hand2",
                  command=dlg.destroy).pack(side="right", padx=(0, s(6)),
                                            ipadx=s(14), ipady=s(4))
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.bind("<Control-s>", lambda e: (save(), "break")[1])
        dlg.bind("<Destroy>", lambda e: (
            setattr(self, "_groups_dlg", None)
            if e.widget is dlg else None))
        dlg.update_idletasks()
        w = s(360)
        h = min(s(560), dlg.winfo_reqheight())
        sm = ctypes.windll.user32.GetSystemMetrics
        dlg.geometry("%dx%d+%d+%d" % (w, h, sm(0) // 2 - w // 2,
                                      sm(1) // 2 - h // 2))
        return dlg

    # ---------- alarm editor ----------

    def open_alarm_editor(self, focus_sym=None):
        dlg = getattr(self, "_alarms_dlg", None)
        if dlg is not None and dlg.winfo_exists():
            dlg.deiconify()
            dlg.lift()
            dlg.focus_set()
            return dlg
        s = self.s
        dlg = tk.Toplevel(self.root)
        self._alarms_dlg = dlg
        dlg.configure(bg=CARD)
        dlg.attributes("-topmost", True)
        dlg.title("Alarmlar")
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        try:
            dlg.iconbitmap(ICON_FILE)
        except tk.TclError:
            pass
        dark_title_bar(dlg)

        tk.Label(dlg, text="ALARMLAR", bg=CARD, fg=MUTED,
                 font=self.f_title).pack(anchor="w", padx=s(18),
                                         pady=(s(14), s(2)))
        tk.Label(dlg,
                 text="Boş alan alarm yok demektir. Eşik aşıldığında bir kez "
                      "tepsi bildirimi gelir; fiyat geri dönünce alarm yeniden kurulur. "
                      "Kâr/Zarar % alanları pozisyon maliyetine göredir.",
                 bg=CARD, fg=DIM, font=self.f_foot, justify="left",
                 wraplength=s(450)).pack(anchor="w", padx=s(18),
                                         pady=(0, s(6)))

        quiet_row = tk.Frame(dlg, bg=CARD)
        quiet_row.pack(fill="x", padx=s(18), pady=(0, s(6)))
        quiet_on = tk.BooleanVar(value=bool(self.cfg.get("quiet_enabled")))
        tk.Checkbutton(quiet_row, text="Sessiz saat", variable=quiet_on,
                       bg=CARD, fg=MUTED, activebackground=CARD,
                       activeforeground=FG, selectcolor=RAISED, bd=0,
                       highlightthickness=0, font=("Segoe UI", 8),
                       cursor="hand2").pack(side="left")
        q_start = tk.Entry(quiet_row, width=3, bg=RAISED, fg=FG,
                           insertbackground=FG, relief="flat",
                           justify="center", font=(self.mono, 8),
                           highlightthickness=1,
                           highlightbackground=ENTRY_BORDER)
        q_start.insert(0, str(self.cfg.get("quiet_start", 23)))
        q_start.pack(side="left", padx=(s(6), 0), ipady=s(2))
        tk.Label(quiet_row, text="–", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=s(3))
        q_end = tk.Entry(quiet_row, width=3, bg=RAISED, fg=FG,
                         insertbackground=FG, relief="flat",
                         justify="center", font=(self.mono, 8),
                         highlightthickness=1,
                         highlightbackground=ENTRY_BORDER)
        q_end.insert(0, str(self.cfg.get("quiet_end", 8)))
        q_end.pack(side="left", ipady=s(2))
        tk.Label(quiet_row, text="(0–23)", bg=CARD, fg=DIM,
                 font=("Segoe UI", 6)).pack(side="left", padx=(s(4), 0))

        holder = tk.Frame(dlg, bg=CARD)
        holder.pack(fill="both", expand=True, padx=s(18))
        cv = tk.Canvas(holder, bg=CARD, highlightthickness=0, bd=0,
                       height=s(360))
        cv.pack(side="left", fill="both", expand=True)
        vs = tk.Scrollbar(holder, orient="vertical", command=cv.yview,
                          width=s(9), bg=CARD, troughcolor=CARD, bd=0,
                          relief="flat", activebackground=BTN,
                          highlightthickness=0)
        table = tk.Frame(cv, bg=CARD)
        win_id = cv.create_window((0, 0), window=table, anchor="nw")
        cv.configure(yscrollcommand=vs.set)
        table.bind("<Configure>", lambda e: cv.configure(
            scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win_id,
                                                          width=e.width))
        vs.pack(side="right", fill="y")

        cols = ((0, s(62), "SEMBOL", "w"), (1, s(58), "ÜSTÜNDE", "e"),
                (2, s(58), "ALTINDA", "e"), (3, s(52), "DEĞİŞİM %", "e"),
                (4, s(52), "KÂR %", "e"), (5, s(52), "ZARAR %", "e"),
                (6, s(40), "PÖ/PS", "center"), (7, s(20), "", "center"))
        for col, width, label, anchor in cols:
            table.grid_columnconfigure(col, minsize=width)
            tk.Label(table, text=label, bg=CARD, fg=DIM,
                     font=("Segoe UI", 6, "bold"), anchor=anchor).grid(
                row=0, column=col, sticky="ew", padx=(0, s(4)),
                pady=(0, s(4)))

        def mk_num(parent):
            e = tk.Entry(parent, bg=RAISED, fg=FG, insertbackground=FG,
                         relief="flat", width=6, font=(self.mono, 9),
                         justify="right", highlightthickness=1,
                         highlightbackground=ENTRY_BORDER,
                         highlightcolor=ACCENT)
            e.pack(fill="x", ipady=s(3))
            return e

        rows = {}
        alarms = self.cfg.get("alarms") or {}
        for idx, sym in enumerate(self.cfg.get("symbols") or []):
            rule = alarms.get(sym) or {}
            r = idx + 1
            tk.Label(table, text=sym, bg=CARD, fg=FG, font=self.f_sym,
                     anchor="w").grid(row=r, column=0, sticky="w",
                                      pady=s(4))
            cells = {}
            for col, field in enumerate(("above", "below", "pct",
                                         "profit", "loss"), start=1):
                box = tk.Frame(table, bg=CARD)
                box.grid(row=r, column=col, sticky="ew",
                         padx=(0, s(3)), pady=s(2))
                e = mk_num(box)
                if field in rule:
                    e.insert(0, ("%.6g" % rule[field]).replace(".", ","))
                cells[field] = e
            ext = tk.BooleanVar(value=bool(rule.get("extended")))
            chk = tk.Checkbutton(table, variable=ext, bg=CARD, fg=MUTED,
                                 activebackground=CARD, activeforeground=FG,
                                 selectcolor=RAISED, bd=0,
                                 highlightthickness=0, cursor="hand2")
            chk.grid(row=r, column=6, pady=s(2))
            clear = tk.Button(table, text="✕", bg=CARD, fg=DIM, bd=0,
                              activebackground=RED_DIM, activeforeground=RED,
                              font=("Segoe UI", 8), cursor="hand2",
                              command=lambda: clear_row(sym))
            clear.grid(row=r, column=7, pady=s(2))
            rows[sym] = {"above": cells["above"], "below": cells["below"],
                         "pct": cells["pct"], "profit": cells["profit"],
                         "loss": cells["loss"], "extended": ext}

        if not rows:
            tk.Label(table, text="Takip listesi boş.", bg=CARD, fg=MUTED,
                     font=self.f_foot).grid(row=1, column=0, columnspan=8,
                                            pady=s(20))

        def clear_row(sym):
            rec = rows.get(sym)
            if not rec:
                return
            for key in ("above", "below", "pct", "profit", "loss"):
                rec[key].delete(0, "end")
            rec["extended"].set(False)

        def parse(widget):
            txt = (widget.get() or "").strip().replace(",", ".")
            if not txt:
                return None
            try:
                value = float(txt)
            except ValueError:
                return False
            return value if math.isfinite(value) and value > 0 else False

        status = tk.Label(dlg, text="", bg=CARD, fg=DIM, font=self.f_foot,
                          anchor="w")
        status.pack(fill="x", padx=s(18), pady=(s(6), 0))

        def save(event=None):
            out = {}
            for sym, rec in rows.items():
                values = {}
                for key in ("above", "below", "pct", "profit", "loss"):
                    value = parse(rec[key])
                    rec[key].config(highlightbackground=(
                        ENTRY_BORDER if value is not False else RED))
                    if value is False:
                        status.config(text="%s: geçerli, pozitif sayı gir."
                                           % sym, fg=RED)
                        rec[key].focus_set()
                        return
                    if value is not None:
                        values[key] = value
                if values:
                    values["extended"] = bool(rec["extended"].get())
                    out[sym] = values
            try:
                qs = int(q_start.get())
                qe = int(q_end.get())
            except ValueError:
                status.config(text="Sessiz saat 0–23 arası tam sayı olmalı.",
                              fg=RED)
                return
            if not (0 <= qs <= 23 and 0 <= qe <= 23):
                status.config(text="Sessiz saat 0–23 arası olmalı.", fg=RED)
                return
            self.cfg["quiet_enabled"] = bool(quiet_on.get())
            self.cfg["quiet_start"] = qs
            self.cfg["quiet_end"] = qe
            self.cfg["alarms"] = clean_alarms(out)
            save_config(self.cfg)
            self._alarm_state.clear()
            self.build_ui()
            status.config(text="Kaydedildi · %d sembolde alarm"
                               % len(self.cfg["alarms"]), fg=GREEN)

        hist = getattr(self, "alarm_history", [])[-3:]
        if hist:
            lines = [datetime.datetime.fromtimestamp(item["ts"]).strftime(
                "%d.%m %H:%M") + " · " + item["message"] for item in hist]
            tk.Label(dlg, text="Son alarmlar:\n" + "\n".join(lines),
                     bg=CARD, fg=DIM, font=("Segoe UI", 6), justify="left",
                     anchor="w", wraplength=s(450)).pack(
                fill="x", padx=s(18), pady=(s(2), 0))

        footer = tk.Frame(dlg, bg=CARD)
        footer.pack(fill="x", padx=s(18), pady=(s(6), s(12)))
        tk.Button(footer, text="Kaydet", bg=ACCENT, fg="#ffffff", bd=0,
                  activebackground=ACCENT_HOVER, activeforeground="#ffffff",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  command=save).pack(side="right", ipadx=s(22), ipady=s(4))
        tk.Button(footer, text="Kapat", bg=BTN, fg=FG, bd=0,
                  activebackground=BTN_HOVER, activeforeground=FG,
                  font=("Segoe UI", 9), cursor="hand2",
                  command=dlg.destroy).pack(side="right", padx=(0, s(6)),
                                            ipadx=s(14), ipady=s(4))
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.bind("<Control-s>", lambda e: (save(), "break")[1])
        dlg.bind("<Destroy>", lambda e: (
            setattr(self, "_alarms_dlg", None)
            if e.widget is dlg else None))
        table.update_idletasks()
        w = s(495)
        h = min(s(620), dlg.winfo_reqheight())
        sm = ctypes.windll.user32.GetSystemMetrics
        dlg.geometry("%dx%d+%d+%d" % (w, h, sm(0) // 2 - w // 2,
                                      sm(1) // 2 - h // 2))
        if focus_sym in rows:
            rows[focus_sym]["above"].focus_set()
            dlg.after(200, lambda: cv.yview_moveto(
                max(0.0, (list(rows).index(focus_sym)) / float(
                    max(1, len(rows))))))
        return dlg

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
        cur_lbl = tk.Label(head, text=cur, bg=RAISED, fg=MUTED,
                           font=("Segoe UI", 6, "bold"))
        cur_lbl.pack(side="left", padx=(s(8), 0), ipadx=s(4), ipady=s(1))
        tk.Label(dlg, text="Adet, maliyet, hedef ve not gir; boş adet satırı siler.",
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

        # ---- portföy geçmişi ----
        hist_points = history_series(getattr(self, "history", []), cur, 30)
        if len(hist_points) >= 2:
            hist_card = tk.Frame(dlg, bg=RAISED, highlightthickness=1,
                                 highlightbackground=DIVIDER)
            hist_card.pack(fill="x", padx=s(18), pady=(s(8), 0))
            hist_head = tk.Frame(hist_card, bg=RAISED)
            hist_head.pack(fill="x", padx=s(10), pady=(s(6), 0))
            tk.Label(hist_head, text="PORTFÖY GEÇMİŞİ · SON 30 KAYIT",
                     bg=RAISED, fg=DIM,
                     font=("Segoe UI", 6, "bold")).pack(side="left")
            change = history_change(hist_points)
            if change is not None:
                tk.Label(hist_head, text="%+.2f%%" % change, bg=RAISED,
                         fg=GREEN if change >= 0 else RED,
                         font=("Segoe UI", 8, "bold")).pack(side="right")
            hc = tk.Canvas(hist_card, bg=RAISED, height=s(58),
                           highlightthickness=0, bd=0)
            hc.pack(fill="x", padx=s(10), pady=(s(2), s(8)))
            hh = s(56)
            vals = [value for _day, value in hist_points]
            lo, hi = min(vals), max(vals)
            rng = (hi - lo) or 1.0
            line_col = GREEN if (change or 0) >= 0 else RED

            def draw_hist(event=None):
                hw = (event.width if event is not None
                      else hc.winfo_width()) or s(410)
                hc.delete("all")
                pts = []
                for i, value in enumerate(vals):
                    pts.extend((s(2) + (hw - s(4)) * i
                                / float(len(vals) - 1),
                                hh - s(4) - (value - lo) / rng * (hh - s(8))))
                hc.create_line(*pts, fill=line_col,
                               width=max(1, int(round(1.6 * self.S))))
                hc.create_oval(pts[-2] - s(2), pts[-1] - s(2),
                               pts[-2] + s(2), pts[-1] + s(2),
                               fill=line_col, outline="")

            hc.bind("<Configure>", draw_hist)
            hc.after_idle(draw_hist)

        # ---- tablo ----
        body = tk.Frame(dlg, bg=CARD)
        body.pack(fill="x", padx=s(18), pady=(s(12), 0))
        left = tk.Frame(body, bg=CARD)
        left.pack(side="left", fill="both", expand=True)

        MINS = {0: s(112), 1: s(60), 2: s(74), 3: s(78), 4: s(58), 5: s(20)}
        PADS = {0: (s(10), 0), 1: (s(2), 0), 2: (s(2), 0),
                3: (s(6), s(6)), 4: (0, s(6)), 5: (0, 0)}

        header = tk.Frame(left, bg=CARD)
        header.pack(fill="x", pady=(0, s(4)))
        for col in range(6):
            header.grid_columnconfigure(
                col, minsize=MINS[col], weight=1 if col == 3 else 0)
        for col, text, anchor in ((0, "SEMBOL · HEDEF · NOT", "w"),
                                  (1, "ADET", "e"),
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
            target = mk_entry(c0, rowinfo)
            target.configure(width=8)
            if p.get("target"):
                target.insert(0, ("%.6g" % p["target"]).replace(".", ","))
            target.pack(fill="x", ipady=s(1), pady=(s(1), 0))
            note = tk.Entry(c0, bg=RAISED, fg=MUTED, insertbackground=FG,
                            relief="flat", width=10, font=("Segoe UI", 7),
                            highlightthickness=1,
                            highlightbackground=ENTRY_BORDER,
                            highlightcolor=ACCENT)
            if p.get("note"):
                note.insert(0, p["note"])
            note.bind("<FocusIn>", lambda ev, rr=rowinfo: highlight(rr))
            note.pack(fill="x", ipady=s(1), pady=(s(1), 0))

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
                              command=lambda q=qty, a=avg, t=target,
                              n=note: (
                                  q.delete(0, "end"),
                                  a.delete(0, "end"),
                                  t.delete(0, "end"),
                                  n.delete(0, "end"), recalc()))
            clear.pack()

            rowinfo["cells"] = [c0, sym_lbl, target, note, c1, qty, c2, avg,
                                c3, val_lbl, c4, pnl_lbl, c5, clear]
            rows[sym] = {"qty": qty, "avg": avg, "target": target,
                         "note": note, "value": val_lbl, "pnl": pnl_lbl}
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
            groups = {}
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
                price = display_price(info, self.cfg.get("extended_hours", True))
                cost = q * a
                tc += cost
                g = groups.setdefault(info.get("currency") or cur,
                                      {"value": 0.0, "cost": 0.0,
                                       "pnl": 0.0})
                g["cost"] += cost
                if price:
                    value = q * float(price)
                    have_price = True
                    tc_priced += cost
                    pnl_sum += value - cost
                    g["value"] += value
                    g["pnl"] += value - cost
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
            mixed = len(groups) > 1
            cur_lbl.config(text="KARIŞIK" if mixed else cur)
            if mixed:
                def totals(key):
                    return " · ".join(fmt_money(g[key], ccode)
                                      for ccode, g in sorted(groups.items())
                                      if key != "cost" or g["cost"])
                stats["value"][0].config(text="karışık", fg=AMBER)
                stats["value"][1].config(text=totals("value"), fg=DIM)
                stats["cost"][0].config(text="karışık", fg=AMBER)
                stats["cost"][1].config(text=totals("cost"), fg=DIM)
                stats["pnl"][0].config(text="karışık", fg=AMBER)
                stats["pnl"][1].config(text=totals("pnl"), fg=DIM)
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
                t = parse_num(r["target"])
                if t is None or t < 0:
                    recalc()
                    r["target"].focus_set()
                    status.config(text="%s: geçersiz hedef fiyat." % sym,
                                  fg=RED)
                    return
                if q > 0:
                    rec = {"qty": q, "avg": a}
                    if t > 0:
                        rec["target"] = t
                    note = (r["note"].get() or "").strip()[:120]
                    if note:
                        rec["note"] = note
                    out[sym] = rec
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
        show_cost = tk.BooleanVar(
            value=bool(self.cfg.get("portfolio_show_cost")))
        tk.Checkbutton(footer, text="Kartta maliyeti göster",
                       variable=show_cost, bg=CARD, fg=MUTED,
                       activebackground=CARD, activeforeground=FG,
                       selectcolor=RAISED, bd=0, highlightthickness=0,
                       font=("Segoe UI", 8), cursor="hand2",
                       command=lambda: self._set_portfolio_show_cost(
                           show_cost.get())).pack(side="left")
        tk.Button(footer, text="CSV", bg=BTN, fg=FG, bd=0,
                  activebackground=BTN_HOVER, activeforeground=FG,
                  font=("Segoe UI", 8), cursor="hand2",
                  command=self.export_portfolio_csv).pack(
            side="left", padx=(s(8), 0), ipadx=s(8), ipady=s(3))
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
        w, h = s(512), dlg.winfo_reqheight()
        dlg.geometry("%dx%d+%d+%d" % (w, h, sw_ // 2 - w // 2,
                                      sh_ // 2 - h // 2))
        return dlg

    def _set_portfolio_show_cost(self, value):
        self.cfg["portfolio_show_cost"] = bool(value)
        save_config(self.cfg)
        self.build_ui()
        self._restore_position()

    def export_portfolio_csv(self):
        dlg = getattr(self, "_portfolio_dlg", None)
        parent = dlg if dlg is not None and dlg.winfo_exists() else self.root
        path = filedialog.asksaveasfilename(
            parent=parent, title="Portföyü CSV'ye aktar",
            defaultextension=".csv",
            initialfile="portfoy-%s.csv" % datetime.date.today().strftime(
                "%Y%m%d"),
            filetypes=[("CSV", "*.csv"), ("Tüm dosyalar", "*.*")])
        if not path:
            return
        rows = portfolio_csv_rows(self.cfg.get("positions") or {}, self.last)
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(PORTFOLIO_CSV_HEADER)
                writer.writerows(rows)
                totals = self._portfolio_by_currency()
                if totals:
                    writer.writerow([])
                    writer.writerow(["TOPLAM", "", "", "", "", "", "",
                                     "Deger", "Maliyet", "KarZarar",
                                     "GunlukDegisim"])
                    for ccode, bucket in sorted(totals.items()):
                        writer.writerow(["", "", "", "", "", ccode, "",
                                         round(bucket["value"], 4),
                                         round(bucket["cost"], 4),
                                         round(bucket["value"]
                                               - bucket["cost"], 4),
                                         round(bucket["day"], 4)])
        except OSError as exc:
            log.warning("CSV yazılamadı: %s", exc)
            messagebox.showwarning("Portföy", "CSV yazılamadı:\n%s" % exc,
                                   parent=parent)
            return
        log.info("portföy CSV: %s (%d satır)", path, len(rows))
        messagebox.showinfo("Portföy", "CSV kaydedildi:\n%s" % path,
                            parent=parent)

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

    def _pick_language(self, key):
        if key not in ("tr", "en") or key == self.cfg.get("language"):
            return
        self.cfg["language"] = key
        i18n.set_language(key)
        save_config(self.cfg)
        self.close_detail(animate=False)
        for attr in ("_alarms_dlg", "_groups_dlg", "_portfolio_dlg",
                     "_editor"):
            dlg = getattr(self, attr, None)
            if dlg is not None:
                try:
                    dlg.destroy()
                except tk.TclError:
                    pass
        # Menü etiketleri oluşturulurken çevrildiği için yeniden kur.
        for attr in ("menu", "remove_menu", "sort_menu", "group_menu",
                     "row_menu"):
            old = getattr(self, attr, None)
            if old is not None:
                try:
                    old.destroy()
                except tk.TclError:
                    pass
        self._build_menu()
        self.build_ui()
        self._restore_position()
        self._style_menus()
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
            self._setup_tray()
        self._refresh_settings()
        self._settings_note("Dil: %s" % ("English" if key == "en"
                                         else "Türkçe"))

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

    def _pick_night_pause(self, value):
        self.set_night_pause(value)
        self._settings_note("Gece isteği %s."
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

    def export_diagnostics(self):
        dlg = self._settings_dlg
        parent = dlg if dlg is not None and dlg.winfo_exists() else self.root
        path = filedialog.asksaveasfilename(
            parent=parent, title="Tanılama paketi oluştur",
            defaultextension=".zip",
            initialfile="stockwidget-tanilama-%s.zip"
                        % datetime.date.today().strftime("%Y%m%d"),
            filetypes=[("ZIP", "*.zip")])
        if not path:
            return
        try:
            info = diagnostics_info(self.cfg, self.last,
                                    getattr(self, "history", []))
            info += "tk: %s\n" % tk.TkVersion
            if self._detail is not None:
                info += "açık detay: %s\n" % self._detail.symbol
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("sistem.txt", info)
                zf.writestr("config-redacted.json", json.dumps(
                    redact_config(self.cfg), indent=2, ensure_ascii=False))
                for src, name in ((LOG_FILE, "sw.log"),
                                  (ALARM_HISTORY_FILE, "alarm-history.json"),
                                  (SNAPSHOT_FILE, "snapshot.json")):
                    if os.path.exists(src):
                        try:
                            with open(src, "r", encoding="utf-8",
                                      errors="replace") as f:
                                text = f.read()[-200000:]
                            zf.writestr(name, text)
                        except OSError:
                            pass
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            log.warning("tanılama paketi yazılamadı: %s", exc)
            messagebox.showwarning("Tanılama", "Paket yazılamadı:\n%s" % exc,
                                   parent=parent)
            return
        log.info("tanılama paketi: %s", path)
        messagebox.showinfo("Tanılama", "Paket kaydedildi:\n%s" % path,
                            parent=parent)

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

        row, _ = add_row(card, "Dil / Language")
        segmented(row, [("Türkçe", "tr"), ("English", "en")],
                  lambda: self.cfg.get("language", "tr"),
                  self._pick_language).pack(side="right", padx=(0, s(9)))

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
        row, _ = add_row(card, "Ayar dosyası", "config.json")
        small_button(row, "Klasörü aç",
                     self._open_data_dir).pack(side="right",
                                               padx=(0, s(9)))
        row, _ = add_row(card, "Tanılama paketi",
                         "Log + sistem özeti (portföy gizlenir)", last=True)
        small_button(row, "Oluştur",
                     self.export_diagnostics).pack(side="right",
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

        row, _ = add_row(card, "Gece isteğini durdur",
                         "20:05–04:00 ET arası istek yok")
        switch(row, lambda: self.cfg.get("night_pause", True),
               self._pick_night_pause).pack(side="right",
                                            padx=(0, s(11)))

        row, last_lbl = add_row(card, "Son veri",
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
        small_button(footer, "Alarmlar…",
                     self.open_alarm_editor).pack(side="left",
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

    def _phase_for(self, sym):
        info = self.last.get(sym) or {}
        profile = exchange_profile(info, sym)
        if profile == "generic" and not info:
            profile = "us"       # ilk veri gelene kadar eski davranış
        if profile == "tr":
            return tr_phase()
        if profile == "crypto":
            return crypto_phase()
        if profile == "us":
            return market_phase()
        return market_state_phase(info.get("market_state"))

    def _market_active(self):
        """Herhangi bir sembolün piyasası açık mı? (ABD/BIST/kripto)"""
        symbols = list(self.cfg.get("symbols") or [])
        if not symbols:
            return False
        return any(self._phase_for(sym) is not None for sym in symbols)

    def _market_summary(self):
        """(herhangi faz, başlık etiketi, ayrıntı satırları) üretir."""
        profiles = {}
        for sym in self._view_symbols or self.cfg.get("symbols") or []:
            info = self.last.get(sym) or {}
            profile = exchange_profile(info, sym)
            if profile == "generic" and not info:
                profile = "us"
            if profile not in profiles:
                profiles[profile] = self._phase_for(sym)
        if not profiles:
            profiles = {"us": market_phase()}
        phases = list(profiles.values())
        if "regular" in phases:
            any_phase = "regular"
        elif any(p in ("pre", "post") for p in phases):
            any_phase = "pre" if "pre" in phases else "post"
        else:
            any_phase = None
        details = ["%s: %s" % (PROFILE_LABEL.get(profile, profile),
                               phase_label(phase, profile))
                   for profile, phase in profiles.items()]
        if len(profiles) == 1:
            profile, phase = next(iter(profiles.items()))
            label = phase_label(phase, profile)
            if (profile == "us" and phase in ("pre", "post")
                    and not self.cfg.get("extended_hours", True)):
                label = ""
        else:
            label = "çoklu"
        return any_phase, label, details

    def _refresh_minutes(self, is_open):
        key = "refresh_open" if is_open else "refresh_closed"
        default = (INTERVAL_OPEN if is_open else INTERVAL_CLOSED) // 60
        try:
            return max(1, int(self.cfg.get(key, default)))
        except (TypeError, ValueError):
            return default

    def fetch_loop(self):
        """Veri döngüsü: tek bir hata döngüyü kalıcı olarak durdurmamalı."""
        while not self.stop_flag.is_set():
            try:
                delay = self._fetch_cycle()
            except Exception:
                log.exception("veri döngüsü hatası; yeniden denenecek")
                try:
                    self.queue.put(({}, True))
                except Exception:
                    pass
                delay = INTERVAL_RETRY
            self.wake.wait(delay)
            self.wake.clear()

    def _fetch_cycle(self):
        """Bir tur veri çeker ve bir sonraki turun gecikmesini döndürür."""
        extended = self.cfg.get("extended_hours", True)
        is_open = self._market_active()
        night_stop = (self.cfg.get("night_pause", True)
                      and us_quiet_hours())
        if (not is_open and not self._force_refresh
                and (self.cfg.get("pause_when_closed") or night_stop)):
            # Piyasa kapalı/gece: ağ isteği yok, yalnızca açılışı yakalamak
            # için saat kontrol edilir (60 s'de bir, istek üretmez).
            return PAUSE_POLL
        self._force_refresh = False
        symbols = list(self.cfg.get("symbols") or [])
        if not symbols:
            # Boş liste: sadece bekle, çevrimdışı sayma
            self.queue.put(({}, False))
            return self._refresh_minutes(False) * 60
        results, failures, attempted, backoff = self._fetch_symbols(
            symbols, extended)
        if failures:
            log.warning("fetch: %d/%d sembol başarısız", failures, attempted)
        if backoff:
            # 429: kalan sembolleri de zorlamak durumu kötüleştirir.
            # Retry-After'ın üstüne küçük jitter: eşzamanlı istemciler
            # aynı saniyede geri dönmesin.
            self.queue.put((results, not results))
            return backoff + random.uniform(3, min(30, backoff * 0.1))
        is_open = self._market_active()
        interval = self._refresh_minutes(is_open) * 60
        offline = bool(attempted) and not results
        if offline:
            interval = INTERVAL_RETRY
        self.queue.put((results, offline))
        return interval

    def _fetch_symbols(self, symbols, extended):
        """Sembolleri sırayla çeker; 429 gelirse kalanları atlar."""
        results = {}
        failures = attempted = 0
        backoff = None
        for i, sym in enumerate(symbols):
            if self.stop_flag.is_set():
                break
            if i and self.stop_flag.wait(0.4):
                break
            attempted += 1
            try:
                results[sym] = fetch_quote(sym, extended)
            except requests.exceptions.HTTPError as exc:
                failures += 1
                response = getattr(exc, "response", None)
                status = getattr(response, "status_code", 0)
                if status == 429:
                    backoff = _retry_after(response)
                    log.warning("429: kalan semboller atlandı (%s sn)", backoff)
                    break
                log.warning("%s: HTTP %s", sym, status)
            except Exception as exc:
                failures += 1
                log.warning("%s: %s", sym, exc)
        return results, failures, attempted, backoff

    # ---------- güncelleme ----------

    @staticmethod
    def _newer_release(info):
        """Yanıttaki sürüm çalışan sürümden yeniyse True."""
        if not isinstance(info, dict):
            return False
        latest = parse_version(info.get("version"))
        current = parse_version(APP_VERSION)
        if not latest or not current:
            return False
        return latest > current

    def check_updates(self, silent=False):
        """GitHub'daki son sürümü denetler; önbellek sayesinde günde 1 istek."""
        if self._update_busy or self.stop_flag.is_set():
            return
        self._update_busy = True
        threading.Thread(target=self._update_worker,
                         args=(bool(silent),), daemon=True).start()

    def _update_worker(self, silent):
        info = read_update_cache()
        try:
            fresh = (silent and time.time() - float(info.get("ts") or 0)
                     < UPDATE_TTL)
        except (AttributeError, TypeError, ValueError):
            fresh = False
        if not fresh:
            fetched = check_latest_release()
            if fetched:
                write_update_cache(fetched)
                info = fetched
            else:
                info = None
        try:
            # Tk yalnızca ana thread'de kullanılır (bkz. AGENT.md).
            self.root.after(0, lambda: self._update_done(info, silent))
        except (tk.TclError, RuntimeError):
            self._update_busy = False

    def _update_done(self, info, silent):
        self._update_busy = False
        if self._newer_release(info):
            log.info("yeni sürüm bulundu: %s", info["version"])
            self._set_update_hint(info)
            if silent:
                self._notify_update(info)
            else:
                msg = ("StockWidget %s hazır (bu sürüm %s).\n\n"
                       "İndirme sayfası açılsın mı?"
                       % (info["version"], APP_VERSION))
                if messagebox.askyesno("Güncelleme", msg,
                                       parent=self.root):
                    url = info.get("url")
                    if not (isinstance(url, str)
                            and url.startswith("https://")):
                        url = RELEASES_URL
                    webbrowser.open(url)
            return
        if silent:
            return
        if info is None:
            messagebox.showwarning(
                "Güncelleme",
                "Güncelleme bilgisi alınamadı.\nİnternet bağlantınızı "
                "denetleyip yeniden deneyin.", parent=self.root)
        else:
            messagebox.showinfo("Güncelleme",
                                "En son sürümü kullanıyorsunuz (%s)."
                                % APP_VERSION, parent=self.root)

    def _set_update_hint(self, info):
        """Menüdeki güncelleme satırını yeni sürüme işaretle."""
        idx = getattr(self, "_menu_update_index", None)
        if idx is None:
            return
        try:
            self.menu.entryconfig(idx, label="Yeni sürüm: %s" % info["version"])
        except (tk.TclError, TypeError):
            pass

    def _notify_update(self, info):
        """Aynı sürüm için her açılışta değil, yalnızca bir kez tepsi uyarısı."""
        if info.get("notified") == info["version"]:
            return
        icon = self.tray_icon
        if not icon:
            return
        try:
            icon.notify("StockWidget %s hazır. Menüden indirebilirsiniz."
                        % info["version"], APP_NAME)
        except Exception:
            return
        info["notified"] = info["version"]
        write_update_cache(info)

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
                T("Göster / Gizle"),
                lambda *a: self.root.after(0, self.toggle_visibility),
                default=True),
            pystray.MenuItem(T("Yenile"), lambda *a: self.refresh_now()),
            pystray.MenuItem(
                T("Ayarlar…"),
                lambda *a: self.root.after(0, self.open_settings_editor)),
            pystray.MenuItem(
                T("Semboller…"),
                lambda *a: self.root.after(0, self.open_symbol_editor)),
            pystray.MenuItem(
                T("Alarmlar…"),
                lambda *a: self.root.after(0, self.open_alarm_editor)),
            pystray.MenuItem(
                T("Portföy…"),
                lambda *a: self.root.after(0, self.open_portfolio_editor)),
            pystray.MenuItem(
                T("Gruplar…"),
                lambda *a: self.root.after(0, self.open_group_editor)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                T("Odak modu"),
                lambda *a: self.root.after(0, self.toggle_focus),
                checked=lambda item: bool(self.cfg.get("focus_mode"))),
            pystray.MenuItem(
                T("Önceki sembol"),
                lambda *a: self.root.after(0, lambda: self._focus_step(-1))),
            pystray.MenuItem(
                T("Sonraki sembol"),
                lambda *a: self.root.after(0, lambda: self._focus_step(1))),
            pystray.MenuItem(
                T("Alarmları 1 saat sustur"),
                lambda *a: self.root.after(0, lambda: self.mute_alarms(60))),
            pystray.MenuItem(
                T("Alarm susturmayı kaldır"),
                lambda *a: self.root.after(0, self.unmute_alarms)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                T("Windows'ta otomatik başlat"),
                lambda *a: self.root.after(0, self._tray_toggle_startup),
                checked=lambda item: startup_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(T("Çıkış"),
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
        if os.environ.get("SW_DISABLE_TRAY"):
            return
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
        self._hide_market_tip()
        # Ana pencere gizlenirken açık pencereler tek başına kalmasın
        for attr in ("_settings_dlg", "_portfolio_dlg", "_editor",
                     "_alarms_dlg", "_groups_dlg"):
            dlg = getattr(self, attr, None)
            if dlg is None:
                continue
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
    cleanup_stale_mei()
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
