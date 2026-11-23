"""Minimal TR/EN arayüz çevirisi.

Tk widget'ları oluşturulurken metin `tr()` üzerinden geçirilir. Varsayılan dil
Türkçe olduğu için mevcut davranış ve testler değişmez. Dil değişince yeni
oluşturulan tüm Label/Button/Menu/Canvas metinleri çevrilir.

Kapsam: kullanıcı arayüzü metinleri. Log, CLI çıktısı ve config anahtarları
çevrilmez.
"""
from __future__ import annotations

import re

_LANGUAGE = "tr"
_INSTALLED = False

_DIRECT: dict[str, str] = {
    "TAKİP LİSTESİ": "WATCHLIST",
    "Portföy": "Portfolio",
    "son güncelleme": "last update",
    "önbellek": "cached",
    "Son veri": "Last data",
    "son veri": "last data",
    "çevrimdışı": "offline",
    "yükleniyor…": "loading…",
    "güncelleniyor…": "updating…",
    "son güncelleme %s": "last update %s",
    "adet gir": "enter qty",
    "farklı para birimi": "mixed currency",
    "bugün %+.2f": "today %+.2f",
    "Ayarlar…": "Settings…",
    "Ayarlar": "Settings",
    "Sembol ekle / çıkar…": "Add / remove symbols…",
    "Gruplar…": "Groups…",
    "Gruplar": "Groups",
    "Portföy…": "Portfolio…",
    "Alarmlar…": "Alarms…",
    "Alarmlar": "Alarms",
    "Alarmları 1 saat sustur": "Mute alarms for 1 hour",
    "Alarm susturmayı kaldır": "Unmute alarms",
    "Alarm susturma kaldırıldı": "Alarm mute cleared",
    "Odak modu": "Focus mode",
    "Grup": "Group",
    "Tümü": "All",
    "Hızlı çıkar": "Quick remove",
    "Sıralama": "Sort",
    "Elle": "Manual",
    "Değişim %": "Change %",
    "Sembol": "Symbol",
    "Portföy değeri": "Portfolio value",
    "Yenile": "Refresh",
    "Güncelleme denetle…": "Check for updates…",
    "Gizle": "Hide",
    "Çıkış": "Quit",
    "Göster / Gizle": "Show / Hide",
    "Semboller…": "Symbols…",
    "Semboller": "Symbols",
    "Windows'ta otomatik başlat": "Start with Windows",
    "Önceki sembol": "Previous symbol",
    "Sonraki sembol": "Next symbol",
    "Yukarı taşı": "Move up",
    "Aşağı taşı": "Move down",
    "Sembolü kopyala": "Copy symbol",
    "Fiyatı kopyala": "Copy price",
    "Yahoo Finance'te aç": "Open in Yahoo Finance",
    "Listeden çıkar": "Remove from list",
    "Sadece bunu göster": "Show only this",
    "Odak modundan çık": "Exit focus mode",
    "Hedef fiyata alarm kur": "Set target alarm",
    "Gün aralığı": "Day range",
    "Açılış": "Open",
    "Önceki kapanış": "Previous close",
    "Hacim": "Volume",
    "52 hafta": "52 week",
    "gün içi": "intraday",
    "şimdi": "now",
    "mum": "candles",
    "çizgi": "line",
    "veri yok": "no data",
    "grafik yüklenemedi": "chart unavailable",
    "hedef": "target",
    "maliyet": "cost",
    "kapalı": "closed",
    "açık": "open",
    "çoklu": "multi",
    "24s": "24/7",
    "PÖ": "PRE",
    "PS": "POST",
    "PÖ/PS": "PRE/POST",
    "GÖRÜNÜM": "APPEARANCE",
    "VERİ": "DATA",
    "DAVRANIŞ": "BEHAVIOR",
    "GELİŞMİŞ": "ADVANCED",
    "Tema": "Theme",
    "Gece": "Night",
    "Slate": "Slate",
    "Grafit": "Graphite",
    "Açık": "Light",
    "Normal": "Normal",
    "Kompakt": "Compact",
    "güncelleniyor": "updating",
    "az önce": "just now",
    "Dil / Language": "Language",
    "Opaklık": "Opacity",
    "Yoğunluk": "Density",
    "Her zaman üstte": "Always on top",
    "Konumu sıfırla": "Reset position",
    "Piyasa açıkken": "Market open",
    "Piyasa kapalıyken": "Market closed",
    "Yenileme aralığı": "Refresh interval",
    "Piyasa kapalıyken durdur": "Pause when closed",
    "Gece isteğini durdur": "Pause requests at night",
    "Piyasa öncesi/sonrası": "Pre/post market",
    "Kapatınca tepsiye gizle": "Hide to tray on close",
    "Otomatik başlatma": "Start with Windows",
    "Ayar dosyası": "Config file",
    "Klasörü aç": "Open folder",
    "Tanılama paketi": "Diagnostics package",
    "Oluştur": "Create",
    "Sıfırla": "Reset",
    "Kapat": "Close",
    "Kaydet": "Save",
    "Ekle": "Add",
    "Değişiklikler anında uygulanır.":
        "Changes apply immediately.",
    "Değişiklikler Kaydet ile uygulanır.":
        "Changes apply with Save.",
    "TOPLAM DEĞER": "TOTAL VALUE",
    "MALİYET": "COST",
    "K/Z": "P/L",
    "ADET": "QTY",
    "ORTALAMA": "AVERAGE",
    "DEĞER": "VALUE",
    "SEMBOL · HEDEF · NOT": "SYMBOL · TARGET · NOTE",
    "Günlük değişim": "Day change",
    "Kartta maliyeti göster": "Show cost on card",
    "Portföy miktarını gizle": "Hide portfolio amount",
    "Portföy boş.": "Portfolio empty.",
    "Adet, maliyet, hedef ve not gir; boş adet satırı siler.":
        "Enter qty, cost, target and note; empty qty removes the row.",
    "Değiştirme henüz yok": "No change yet",
    "Diğer pencerelerin üstünde kalır": "Stays above other windows",
    "Göster / gizle kısayolu": "Show / hide shortcut",
    "Kapalıysa ✕ uygulamayı kapatır": "If off, ✕ quits the app",
    "Kartı sağ alta taşır": "Moves the card to bottom right",
    "Log + sistem özeti (portföy gizlenir)":
        "Log + system summary (portfolio hidden)",
    "Oturum açılınca başlar": "Starts at sign-in",
    "PÖ / PS fiyat ve değişimi göster": "Show pre/post price and change",
    "Son güncelleme": "Last update",
    "Türkçe": "Turkish",
    "İstek göndermez, açılışı bekler": "Sends no requests, waits for open",
    "20:05–04:00 ET arası istek yok": "No requests between 20:05–04:00 ET",
    "Gece isteği duruyor.": "Night requests paused.",
    "Gece isteği sürüyor.": "Night requests running.",
    "geçersiz": "invalid",
    "geçersiz sayı.": "invalid number.",
    "maliyet yok": "no cost",
    "ALARMLAR": "ALARMS",
    "ÜSTÜNDE": "ABOVE",
    "ALTINDA": "BELOW",
    "DEĞİŞİM %": "CHANGE %",
    "KÂR %": "PROFIT %",
    "ZARAR %": "LOSS %",
    "Sessiz saat": "Quiet hours",
    "Son alarmlar": "Recent alarms",
    "Alarmları düzenle…": "Edit alarms…",
    "Alarmları kaldır": "Clear alarms",
    "Fiyat girerek alarm kur…": "Set alarm by price…",
    "ALARM FİYATI": "ALARM PRICE",
    "Alarm fiyatı": "Alarm price",
    "Grafik aralığının dışında bir seviye de olabilir.":
        "The level may be outside the chart range.",
    "Üstünde alarm kur": "Set alarm above",
    "Altında alarm kur": "Set alarm below",
    "Geçerli, pozitif bir fiyat gir.": "Enter a valid positive price.",
    "İptal": "Cancel",
    "üst alarm": "upper alarm",
    "alt alarm": "lower alarm",
    "Takip listesi boş.": "Watchlist empty.",
    "Boş alan alarm yok demektir. Eşik aşıldığında bir kez tepsi bildirimi gelir; fiyat geri dönünce alarm yeniden kurulur. Kâr/Zarar % alanları pozisyon maliyetine göredir.":
        "Empty field means no alarm. A tray notification is shown once when "
        "the threshold is crossed; it re-arms when the price returns. "
        "Profit/Loss % uses the position cost.",
    "SEMBOL GRUPLARI": "SYMBOL GROUPS",
    "Grup adı yaz; boş bırakılan sembol grupsuz kalır. Menüdeki Grup filtresinden seçebilirsin.":
        "Type a group name; empty symbols stay ungrouped. "
        "Use the Group filter in the menu.",
    "Ticker yazıp Enter'a bas.": "Type a ticker and press Enter.",
    "(liste boş)": "(list empty)",
    "(boş)": "(empty)",
    "Portföyü CSV'ye aktar": "Export portfolio to CSV",
    "Tüm dosyalar": "All files",
    "Ayarlar varsayılana döndü.": "Settings reset to defaults.",
    "Konum sıfırlandı.": "Position reset.",
    "Klasör açılamadı.": "Folder could not be opened.",
    "Tanılama paketi oluştur": "Create diagnostics package",
    "Paket yazılamadı:": "Could not write package:",
    "CSV yazılamadı:": "Could not write CSV:",
    "Yeni sürüm": "New version",
    "Güncelleme": "Update",
    "İndirme sayfası açılsın mı?": "Open the download page?",
    "En son sürümü kullanıyorsunuz": "You are up to date",
    "Güncelleme bilgisi alınamadı.": "Could not check for updates.",
}

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^son güncelleme az önce$"), "last update just now"),
    (re.compile(r"^son güncelleme (\d+) dk önce$"),
     r"last update \1 min ago"),
    (re.compile(r"^son güncelleme (\d+) sa önce$"),
     r"last update \1 h ago"),
    (re.compile(r"^son güncelleme (\d+) gün önce$"),
     r"last update \1 d ago"),
    (re.compile(r"^önbellek · az önce$"), "cached · just now"),
    (re.compile(r"^önbellek · (\d+) dk önce$"), r"cached · \1 min ago"),
    (re.compile(r"^önbellek · (\d+) sa önce$"), r"cached · \1 h ago"),
    (re.compile(r"^önbellek · (\d+) gün önce$"), r"cached · \1 d ago"),
    (re.compile(r"^son güncelleme (.+)$"), r"last update \1"),
    (re.compile(r"^önbellek · (.+)$"), r"cached · \1"),
    (re.compile(r"^işlem yok · son veri (.+)$"),
     r"no trades · last data \1"),
    (re.compile(r"^son veri (.+)$"), r"last data \1"),
    (re.compile(r"^Yeni sürüm: (.+)$"), r"New version: \1"),
    (re.compile(r"^Grup: (.+)$"), r"Group: \1"),
    (re.compile(r"^(.+) · Alarm kur…$"), r"\1 · Set alarm…"),
    (re.compile(r"^Üstünde alarm kur · (.+)$"),
     r"Set alarm above · \1"),
    (re.compile(r"^Altında alarm kur · (.+)$"),
     r"Set alarm below · \1"),
    (re.compile(r"^Hedef fiyata alarm kur \((.+)\)$"),
     r"Set target alarm (\1)"),
    (re.compile(r"^(\d+) dk önce$"), r"\1 min ago"),
    (re.compile(r"^(\d+) sa önce$"), r"\1 h ago"),
    (re.compile(r"^(\d+) gün önce$"), r"\1 d ago"),
    (re.compile(r"^(.+) üzerine çıktı \(şimdi (.+)\)$"),
     r"\1 crossed above (now \2)"),
    (re.compile(r"^(.+) altına indi \(şimdi (.+)\)$"),
     r"\1 fell below (now \2)"),
    (re.compile(r"^(.+) günlük değişim (.+)$"),
     r"\1 daily change \2"),
    (re.compile(r"^(.+) maliyete göre kâr (.+)$"),
     r"\1 profit vs cost \2"),
    (re.compile(r"^(.+) maliyete göre zarar (.+)$"),
     r"\1 loss vs cost \2"),
    (re.compile(r"^Alarmlar (\d+) dakika susturuldu$"),
     r"Alarms muted for \1 minutes"),
    (re.compile(r"^(.+): açık$"), r"\1: open"),
    (re.compile(r"^(.+): kapalı$"), r"\1: closed"),
    (re.compile(r"^(.+): çoklu$"), r"\1: multi"),
    (re.compile(r"^(.+): PÖ$"), r"\1: PRE"),
    (re.compile(r"^(.+): PS$"), r"\1: POST"),
    (re.compile(r"^(.+) · (.+) · açık$"), r"\1 · \2 · open"),
    (re.compile(r"^(.+) · (.+) · kapalı$"), r"\1 · \2 · closed"),
    (re.compile(r"^bugün (.+)$"), r"today \1"),
    (re.compile(r"^(\d+) sembolde alarm$"), r"alarms on \1 symbols"),
    (re.compile(r"^Kaydedildi · (.+)$"), r"Saved · \1"),
    (re.compile(r"^(.+) kaldırıldı\.$"), r"\1 removed."),
    (re.compile(r"^(.+) eklendi\.$"), r"\1 added."),
]


def set_language(language: str) -> None:
    global _LANGUAGE
    _LANGUAGE = "en" if language == "en" else "tr"


def get_language() -> str:
    return _LANGUAGE


def tr(text):
    """Türkçe arayüz metnini seçili dile çevirir; veri değerlerine dokunmaz."""
    if _LANGUAGE != "en" or not isinstance(text, str) or not text:
        return text
    if "\n" in text:
        return "\n".join(tr(line) for line in text.split("\n"))
    hit = _DIRECT.get(text)
    if hit is not None:
        return hit
    for pattern, replacement in _PATTERNS:
        if pattern.match(text):
            return pattern.sub(replacement, text)
    return text


def install_tk_translation() -> None:
    """Tk widget/canvas metinlerini `tr()` üzerinden geçir (bir kez)."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    import tkinter as tk
    from tkinter import messagebox

    def wrap_init(cls):
        original = cls.__init__

        def init(self, *args, **kwargs):
            if "text" in kwargs:
                kwargs["text"] = tr(kwargs["text"])
            original(self, *args, **kwargs)

        cls.__init__ = init

    for cls in (tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton):
        wrap_init(cls)

    def wrap_configure(cls):
        for name in ("configure", "config"):
            original = getattr(cls, name)

            def make(original):
                def configure(self, *args, **kwargs):
                    if "text" in kwargs:
                        kwargs["text"] = tr(kwargs["text"])
                    return original(self, *args, **kwargs)

                return configure

            setattr(cls, name, make(original))

    for cls in (tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton):
        wrap_configure(cls)

    def wrap_menu(method_name):
        original = getattr(tk.Menu, method_name)

        def make(original):
            def method(self, *args, **kwargs):
                if "label" in kwargs:
                    kwargs["label"] = tr(kwargs["label"])
                return original(self, *args, **kwargs)

            return method

        setattr(tk.Menu, method_name, make(original))

    for name in ("add_command", "add_cascade", "add_checkbutton",
                 "add_radiobutton", "entryconfig", "entryconfigure"):
        wrap_menu(name)

    original_create_text = tk.Canvas.create_text

    def create_text(self, *args, **kwargs):
        if "text" in kwargs:
            kwargs["text"] = tr(kwargs["text"])
        return original_create_text(self, *args, **kwargs)

    tk.Canvas.create_text = create_text

    for name in ("itemconfig", "itemconfigure"):
        original = getattr(tk.Canvas, name)

        def make(original):
            def itemconfig(self, *args, **kwargs):
                if "text" in kwargs:
                    kwargs["text"] = tr(kwargs["text"])
                return original(self, *args, **kwargs)

            return itemconfig

        setattr(tk.Canvas, name, make(original))

    original_title = tk.Wm.title

    def title(self, string=None):
        return original_title(self, tr(string) if string is not None else None)

    tk.Tk.title = title
    tk.Toplevel.title = title

    def wrap_box(name):
        original = getattr(messagebox, name)

        def box(*args, **kwargs):
            if len(args) >= 2:
                args = (tr(args[0]), tr(args[1])) + args[2:]
            elif "message" in kwargs:
                kwargs["message"] = tr(kwargs["message"])
            return original(*args, **kwargs)

        setattr(messagebox, name, box)

    for name in ("showinfo", "showwarning", "showerror", "askyesno"):
        wrap_box(name)
