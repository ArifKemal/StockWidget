"""Piyasa profilleri ve BIST seans/tatil takvimi.

Ücretsiz ve çevrimdışıdır: hiçbir ağ isteği yapmaz. ABD tatilleri
`stock_widget.market_holidays` içinde üretilir; bu modül ABD dışı profilleri,
Türkiye tatillerini ve 7/24 kripto davranışını tanımlar.

Not: Dini bayram tarihleri 2024–2030 için tabloda tutulur. BIST resmî tatil
takvimi değiştiğinde bu tablo güncellenmelidir; yeni yıllar için tam gün
kapanışları ve arife yarım günleri eklenmelidir.
"""
from __future__ import annotations

import datetime

Profile = str

US_EXCHANGE_CODES: frozenset[str] = frozenset({
    "NMS", "NYQ", "ASE", "PCX", "BTS", "CBO", "CHX", "NSX",
    "ARCX", "XNAS", "XNYS", "IEX", "MEMX",
})
TR_EXCHANGE_CODES: frozenset[str] = frozenset({"IST", "BIST", "XIST"})
CRYPTO_CODES: frozenset[str] = frozenset({"CCC", "CRYPTOCURRENCY"})

MARKET_STATE_LABEL: dict[str, str] = {
    "PRE": "PÖ", "PREPRE": "PÖ", "REGULAR": "açık",
    "POST": "PS", "POSTPOST": "PS", "CLOSED": "kapalı",
}

# BIST: tam gün kapalı dini bayramlar ve arife yarım günleri (13:00'e kadar).
TR_RELIGIOUS_HOLIDAYS: dict[int, tuple[tuple[int, int], ...]] = {
    2024: ((4, 10), (4, 11), (4, 12), (6, 16), (6, 17), (6, 18), (6, 19)),
    2025: ((3, 30), (3, 31), (4, 1), (6, 6), (6, 7), (6, 8), (6, 9)),
    2026: ((3, 20), (3, 21), (3, 22), (5, 27), (5, 28), (5, 29), (5, 30)),
    2027: ((3, 9), (3, 10), (3, 11), (5, 17), (5, 18), (5, 19), (5, 20)),
    2028: ((2, 26), (2, 27), (2, 28), (5, 5), (5, 6), (5, 7), (5, 8)),
    2029: ((2, 14), (2, 15), (2, 16), (4, 24), (4, 25), (4, 26), (4, 27)),
    2030: ((2, 4), (2, 5), (2, 6), (4, 13), (4, 14), (4, 15), (4, 16)),
}
TR_HALF_DAYS: dict[int, tuple[tuple[int, int], ...]] = {
    2024: ((4, 9), (6, 15)),
    2025: ((3, 29), (6, 5)),
    2026: ((3, 19), (5, 26)),
    2027: ((3, 8), (5, 16)),
    2028: ((2, 25), (5, 4)),
    2029: ((2, 13), (4, 23)),
    2030: ((2, 3), (4, 12)),
}
TR_FIXED_HOLIDAYS: tuple[tuple[int, int], ...] = (
    (1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29),
)
TR_MARKET_OPEN = datetime.time(10, 0)
TR_MARKET_CLOSE = datetime.time(18, 0)
TR_HALF_CLOSE = datetime.time(13, 0)


def tr_now(now: datetime.datetime | None = None) -> datetime.datetime:
    """Türkiye saati (UTC+3, yaz saati uygulaması yok)."""
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is not None:
        now = now.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return now + datetime.timedelta(hours=3)


def tr_holidays(year: int) -> set[datetime.date]:
    """BIST tam gün kapalı günleri (resmî + dini bayramlar)."""
    days = {datetime.date(year, month, day)
            for month, day in TR_FIXED_HOLIDAYS}
    for month, day in TR_RELIGIOUS_HOLIDAYS.get(year, ()):
        days.add(datetime.date(year, month, day))
    return days


def tr_half_days(year: int) -> set[datetime.date]:
    return {datetime.date(year, month, day)
            for month, day in TR_HALF_DAYS.get(year, ())}


def is_tr_holiday(day: datetime.date) -> bool:
    return day.weekday() < 5 and day in tr_holidays(day.year)


def tr_phase(now: datetime.datetime | None = None) -> str | None:
    """BIST fazı: yalnızca hafta içi 10:00–18:00 (arife 13:00).

    `now` verilmezse UTC'den Türkiye saatine çevrilir. Açıkça verilen naive
    datetime İstanbul yerel saati kabul edilir (testler ve elle çağrılar).
    """
    if now is None:
        local = tr_now()
    elif now.tzinfo is not None:
        local = tr_now(now)
    else:
        local = now
    day = local.date()
    if local.weekday() >= 5 or day in tr_holidays(day.year):
        return None
    if day in tr_half_days(day.year) and local.time() >= TR_HALF_CLOSE:
        return None
    if TR_MARKET_OPEN <= local.time() < TR_MARKET_CLOSE:
        return "regular"
    return None


def crypto_phase() -> str:
    return "regular"


def exchange_profile(info: dict | None, symbol: str = "") -> Profile:
    """Yahoo meta + sembolden piyasa profili: us/tr/crypto/generic."""
    meta = info or {}
    code = str(meta.get("exchange_code") or meta.get("exchange")
               or "").strip().upper()
    timezone = str(meta.get("timezone") or "").strip().lower()
    instrument = str(meta.get("instrument_type") or "").strip().upper()
    sym = symbol.upper()
    if (instrument == "CRYPTOCURRENCY" or code in CRYPTO_CODES
            or sym.endswith("-USD")):
        return "crypto"
    if (code in TR_EXCHANGE_CODES or timezone == "europe/istanbul"
            or sym.endswith(".IS")):
        return "tr"
    if code in US_EXCHANGE_CODES:
        return "us"
    return "generic"


PROFILE_LABEL: dict[Profile, str] = {
    "us": "ABD", "tr": "BIST", "crypto": "Kripto", "generic": "Borsa",
}


def market_state_phase(state: str | None) -> str | None:
    """Yahoo marketState -> pre/regular/post/None."""
    return {
        "PRE": "pre", "PREPRE": "pre",
        "REGULAR": "regular",
        "POST": "post", "POSTPOST": "post",
    }.get((state or "").upper())


def phase_label(phase: str | None, profile: str) -> str:
    """Kısa durum etiketi (PÖ/PS yalnızca ABD'de anlamlı)."""
    if phase == "regular":
        return "24s" if profile == "crypto" else "açık"
    if profile == "us" and phase in ("pre", "post"):
        return "PÖ" if phase == "pre" else "PS"
    return "kapalı"
