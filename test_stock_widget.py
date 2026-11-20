"""StockWidget için hızlı birim testleri (stdlib unittest)."""
import calendar
import datetime
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

import stock_widget as sw


class _StubFont:
    """tkfont.Font yerine ölçüm yapan basit sahte font."""

    def measure(self, text):
        return len(text) * 10


class HelpersTest(unittest.TestCase):
    def test_holidays_2026(self):
        days = sw.market_holidays(2026)
        for d in (datetime.date(2026, 1, 1),   # Yılbaşı
                  datetime.date(2026, 1, 19),  # MLK
                  datetime.date(2026, 2, 16),  # Presidents
                  datetime.date(2026, 4, 3),   # Good Friday
                  datetime.date(2026, 5, 25),  # Memorial
                  datetime.date(2026, 6, 19),  # Juneteenth
                  datetime.date(2026, 9, 7),   # Labor
                  datetime.date(2026, 11, 26),  # Thanksgiving
                  datetime.date(2026, 12, 25)):  # Noel
            self.assertIn(d, days)

    def test_easter(self):
        self.assertEqual(sw._easter(2024), datetime.date(2024, 3, 31))
        self.assertEqual(sw._easter(2026), datetime.date(2026, 4, 5))

    def test_observed_weekend(self):
        self.assertEqual(sw._observed(2022, 6, 19), datetime.date(2022, 6, 20))
        self.assertEqual(sw._observed(2021, 12, 25), datetime.date(2021, 12, 24))
        self.assertEqual(sw._observed(2026, 1, 1), datetime.date(2026, 1, 1))

    def test_nth_weekday(self):
        self.assertEqual(sw._nth_weekday(2026, 11, 3, 4),
                         datetime.date(2026, 11, 26))
        self.assertEqual(sw._last_weekday(2026, 5, 0),
                         datetime.date(2026, 5, 25))

    def test_fmt_money(self):
        self.assertEqual(sw.fmt_money(1234.5, "USD"), "$1,234.50")
        self.assertEqual(sw.fmt_money(None, "USD"), "—")
        self.assertEqual(sw.fmt_money(10, "JPY"), "10.00 JPY")
        self.assertEqual(sw.fmt_money(5, ""), "5.00")

    def test_fmt_volume(self):
        self.assertEqual(sw.fmt_volume(0), "—")
        self.assertEqual(sw.fmt_volume(1_500_000), "1.5M")
        self.assertEqual(sw.fmt_volume(3_000_000_000), "3.00B")

    def test_hex_rgb(self):
        self.assertEqual(sw._hex_rgb("#3ddc84"), (61, 220, 132))
        self.assertEqual(sw._hex_rgb("#fff"), (255, 255, 255))
        self.assertEqual(sw._hex_rgb("bozuk"), (128, 128, 128))

    def test_ease_out(self):
        self.assertEqual(sw.ease_out(0.0), 0.0)
        self.assertEqual(sw.ease_out(1.0), 1.0)
        self.assertAlmostEqual(sw.ease_out(0.5), 0.875)
        # aralık dışı değerler kırpılır, eğri tek yönlü artar
        self.assertEqual(sw.ease_out(-3), 0.0)
        self.assertEqual(sw.ease_out(9), 1.0)
        dizi = [sw.ease_out(i / 10.0) for i in range(11)]
        self.assertEqual(dizi, sorted(dizi))

    def test_blend_color(self):
        self.assertEqual(sw.blend_color("#000000", "#ffffff", 0.0),
                         "#000000")
        self.assertEqual(sw.blend_color("#000000", "#ffffff", 1.0),
                         "#ffffff")
        self.assertEqual(sw.blend_color("#000000", "#ffffff", 0.5),
                         "#808080")
        # kırpma
        self.assertEqual(sw.blend_color("#102030", "#102030", 5.0),
                         "#102030")

    def test_anim_constants(self):
        self.assertGreater(sw.ANIM_MS, 0)
        self.assertGreater(sw.ANIM_CLOSE_MS, 0)
        self.assertGreater(sw.ANIM_HOVER_MS, 0)
        self.assertLessEqual(sw.ANIM_MS, 250, "geçişler kısa kalmalı")
        self.assertIsInstance(sw.anim_enabled(), bool)

    def test_run_anim_disabled(self):
        saved = sw.anim_enabled
        sw.anim_enabled = lambda: False
        try:
            seen = []
            sw.run_anim(None, 120, seen.append,
                        done=lambda: seen.append("bitti"))
            # animasyon kapalı: tek karede son duruma atlar
            self.assertEqual(seen, [1.0, "bitti"])
        finally:
            sw.anim_enabled = saved

    def test_ellipsize(self):
        fn = _StubFont()
        self.assertEqual(sw.StockWidget._ellipsize(None, "abcdef", fn, 100),
                         "abcdef")
        self.assertEqual(sw.StockWidget._ellipsize(None, "abcdef", fn, 40),
                         "abc…")

    def test_palette_apply(self):
        original = sw.PALETTES["gece"]["card"]
        sw.apply_palette("slate")
        self.assertEqual(sw.CARD, sw.PALETTES["slate"]["card"])
        sw.apply_palette("gece")
        self.assertEqual(sw.CARD, original)

    @unittest.skipUnless(sw.PIL_AVAILABLE, "Pillow yok")
    def test_render_spark(self):
        img = sw.render_spark([1, 2, 3, 2, 4], 40, 16, "#3ddc84",
                              fill="#3ddc84")
        self.assertEqual(img.size, (40, 16))
        self.assertEqual(sw.render_spark([], 40, 16, "#fff").size, (40, 16))

    def test_downsample_ohlc(self):
        ohlc = [(float(i), float(i + 2), float(i - 1), float(i + 1))
                for i in range(100)]
        out = sw.downsample_ohlc(ohlc, 10)
        self.assertEqual(len(out), 10)
        self.assertEqual(out[0][0], 0.0)
        self.assertEqual(out[-1][3], 100.0)
        self.assertTrue(all(b[1] >= b[3] for b in out))

    def test_market_phase(self):
        def at(h, m=0, day=17):
            return datetime.datetime(2026, 11, day, h, m)

        self.assertEqual(sw.market_phase(at(3, 59)), None)
        self.assertEqual(sw.market_phase(at(4, 0)), "pre")
        self.assertEqual(sw.market_phase(at(9, 29)), "pre")
        self.assertEqual(sw.market_phase(at(9, 30)), "regular")
        self.assertEqual(sw.market_phase(at(15, 59)), "regular")
        self.assertEqual(sw.market_phase(at(16, 0)), "post")
        self.assertEqual(sw.market_phase(at(19, 59)), "post")
        self.assertEqual(sw.market_phase(at(20, 0)), None)
        # hafta sonu (21 Kasım 2026 Cumartesi)
        self.assertEqual(sw.market_phase(at(10, 0, day=21)), None)
        # tatil (26 Kasım 2026 Şükran Günü)
        self.assertEqual(sw.market_phase(at(10, 0, day=26)), None)

    def test_market_open_and_active(self):
        saved = sw.market_phase
        try:
            sw.market_phase = lambda et=None: "pre"
            self.assertFalse(sw.market_open())
            self.assertTrue(sw.market_active())
            sw.market_phase = lambda et=None: "regular"
            self.assertTrue(sw.market_open())
            self.assertTrue(sw.market_active())
            sw.market_phase = lambda et=None: None
            self.assertFalse(sw.market_open())
            self.assertFalse(sw.market_active())
        finally:
            sw.market_phase = saved

    def test_bar_session(self):
        import calendar

        def et_epoch(day, hour, minute=0):
            # Kasım: ET = UTC-5; bar_session epoch'u ET'ye çevirir
            utc = datetime.datetime(2026, 11, day, hour, minute)
            utc += datetime.timedelta(hours=5)
            return calendar.timegm(utc.timetuple())

        self.assertEqual(sw.bar_session(et_epoch(17, 4, 0)), "pre")
        self.assertEqual(sw.bar_session(et_epoch(17, 9, 25)), "pre")
        self.assertIsNone(sw.bar_session(et_epoch(17, 9, 30)))
        self.assertIsNone(sw.bar_session(et_epoch(17, 15, 55)))
        self.assertEqual(sw.bar_session(et_epoch(17, 16, 0)), "post")
        self.assertEqual(sw.bar_session(et_epoch(17, 19, 55)), "post")
        self.assertIsNone(sw.bar_session(et_epoch(18, 0, 5)))
        self.assertIsNone(sw.bar_session(et_epoch(17, 20, 10)))
        self.assertIsNone(sw.bar_session(None))
        # Hafta sonu: son bar Cuma 19:55 -> veri hâlâ seans sonrası
        self.assertEqual(sw.bar_session(et_epoch(21, 19, 55)), "post")

    def test_quote_url(self):
        url = sw.quote_url("AAPL")
        self.assertIn("includePrePost=true", url)
        self.assertIn("period1=", url)
        self.assertIn("period2=", url)
        self.assertNotIn("includePrePost", sw.quote_url("AAPL", False))
        self.assertIn("/chart/AAPL?", url)

    def test_trading_day(self):
        def at(hour, day=17):
            return datetime.datetime(2026, 11, day, hour, 0)

        # 04:00 ET öncesi önceki işlem gününe düşer
        self.assertEqual(sw.trading_day(at(3, day=18)),
                         datetime.date(2026, 11, 17))
        self.assertEqual(sw.trading_day(at(4, day=18)),
                         datetime.date(2026, 11, 18))
        # hafta sonu -> Cuma
        self.assertEqual(sw.trading_day(at(12, day=21)),
                         datetime.date(2026, 11, 20))
        # tatil -> önceki işlem günü (26 Kasım 2026 Şükran Günü)
        self.assertEqual(sw.trading_day(at(12, day=26)),
                         datetime.date(2026, 11, 25))

    def test_session_epoch_range(self):
        start, end = sw.session_epoch_range(
            datetime.datetime(2026, 11, 17, 6, 0))
        self.assertEqual(end - start, 16 * 3600 + 5 * 60)
        # 04:00 ET = 09:00 UTC (EST)
        utc = datetime.datetime.fromtimestamp(start, datetime.timezone.utc)
        self.assertEqual((utc.hour, utc.minute), (9, 0))
        # yaz saati: 04:00 EDT = 08:00 UTC
        start_dst, _ = sw.session_epoch_range(
            datetime.datetime(2026, 7, 15, 6, 0))
        utc_dst = datetime.datetime.fromtimestamp(start_dst,
                                                 datetime.timezone.utc)
        self.assertEqual((utc_dst.hour, utc_dst.minute), (8, 0))

    def test_session_labels(self):
        self.assertEqual(sw.SESSION_LABEL["pre"], "PÖ")
        self.assertEqual(sw.SESSION_LABEL["post"], "PS")

    def test_ext_from_last_bar(self):
        import calendar

        def et_epoch(day, hour, minute=0):
            utc = datetime.datetime(2026, 11, day, hour, minute)
            utc += datetime.timedelta(hours=5)
            return calendar.timegm(utc.timetuple())

        def payload(with_post):
            stamps = [et_epoch(17, 15, 55)]
            closes = [4.60]
            if with_post:
                stamps.append(et_epoch(17, 19, 55))
                closes.append(5.10)
            return {"chart": {"result": [{
                "meta": {"regularMarketPrice": 4.68, "previousClose": 4.76,
                         "chartPreviousClose": 4.76, "currency": "USD",
                         "shortName": "TEST"},
                "timestamp": stamps,
                "indicators": {"quote": [{
                    "close": closes, "open": closes, "high": closes,
                    "low": closes, "volume": [0] * len(closes)}]},
            }]}}

        class _Resp:
            def __init__(self, body):
                self.body = body

            def raise_for_status(self):
                pass

            def json(self):
                return self.body

        saved = sw.requests.get

        def fake_get(url, **kwargs):
            return _Resp(payload(fake_get.with_post))

        fake_get.with_post = True
        try:
            sw.requests.get = fake_get
            info = sw.fetch_quote("TEST", True)
            # Grafiğin son barı (=5.10) kart fiyatı olur, kapanış 4.68 değil
            self.assertEqual(info["spark"][-1], 5.10)
            self.assertEqual(info["ext_session"], "post")
            self.assertAlmostEqual(info["ext_price"], 5.10)
            self.assertAlmostEqual(info["ext_change_pct"],
                                   (5.10 / 4.76 - 1.0) * 100.0)

            fake_get.with_post = False
            info = sw.fetch_quote("TEST", True)
            self.assertEqual(info["spark"][-1], 4.60)
            self.assertIsNone(info["ext_session"])
            self.assertIsNone(info["ext_price"])
        finally:
            sw.requests.get = saved



class _FakeCanvas:
    """Tk tuvali yerine çizilen öğelerin etiketlerini kaydeder."""

    def __init__(self):
        self.items = []
        self._id = 0

    def _add(self, kind, tags, opts=None):
        self._id += 1
        self.items.append({"id": self._id, "kind": kind,
                           "tags": tuple(tags or ()), "opts": dict(opts or {})})
        return self._id

    def delete(self, tag):
        self.items = [it for it in self.items
                      if it["id"] != tag and tag not in it["tags"]]

    def itemconfig(self, item, **kwargs):
        pass

    def create_text(self, *args, **kwargs):
        return self._add("text", kwargs.get("tags"), kwargs)

    def create_rectangle(self, *args, **kwargs):
        return self._add("rect", kwargs.get("tags"), kwargs)

    def create_arc(self, *args, **kwargs):
        return self._add("arc", kwargs.get("tags"), kwargs)

    def create_line(self, *args, **kwargs):
        return self._add("line", kwargs.get("tags"), kwargs)

    def create_oval(self, *args, **kwargs):
        return self._add("oval", kwargs.get("tags"), kwargs)

    def create_image(self, *args, **kwargs):
        return self._add("image", kwargs.get("tags"), kwargs)


class RowRenderTest(unittest.TestCase):
    """Kart satırı yenilenirken eski çizimler tuvalde kalmamalı."""

    def _widget(self):
        w = sw.StockWidget.__new__(sw.StockWidget)
        w.canvas = _FakeCanvas()
        w.items = {"AAA": {"tag": "row_AAA", "y": 0, "price": None}}
        w.cfg = {"extended_hours": True, "symbols": ["AAA"]}
        w.W = 300
        w.PAD = 10
        w.offline = False
        w.S = 1.0
        w._row_photos = {}
        w.font_pct = _StubFont()
        w.font_name = _StubFont()
        w.f_pct = ("Segoe UI", 8, "bold")
        w.f_name = ("Segoe UI", 7)
        w.ro = lambda v: int(round(v))
        w.s = lambda v: int(round(v))
        w._ellipsize = lambda text, font, px: text
        return w

    def _info(self, **over):
        info = {"change_pct": 7.14, "change_abs": 0.34, "price": 5.10,
                "currency": "USD", "name": "Test Inc", "spark": [],
                "ext_session": "post", "ext_price": 5.10,
                "ext_change_pct": 7.14}
        info.update(over)
        return info

    def test_row_badge_cleared_between_refreshes(self):
        w = self._widget()
        w._render_row("AAA", self._info())
        first = len(w.canvas.items)
        # Rozet metni kısalıp rengi değişince eski rozet silinmeli
        w._render_row("AAA", self._info(ext_change_pct=-3.61,
                                        ext_price=4.40,
                                        change_pct=-6.79))
        self.assertEqual(len(w.canvas.items), first)
        for it in w.canvas.items:
            self.assertIn("row_AAA", it["tags"])

    def test_spark_color_follows_ext_session(self):
        """PÖ/PS rozeti kırmızıysa sparkline da kırmızı olmalı."""
        w = self._widget()
        with mock.patch.object(sw, "PIL_AVAILABLE", False):
            w._render_row("AAA", self._info(change_pct=3.0,
                                            ext_change_pct=-1.5,
                                            ext_price=4.0,
                                            spark=[1, 2, 3]))
        lines = [it for it in w.canvas.items
                 if it["kind"] == "line" and it["tags"] == ("row_AAA",)]
        self.assertTrue(lines)
        self.assertEqual(lines[-1]["opts"]["fill"], sw.RED)

    def test_spark_color_follows_regular_session(self):
        w = self._widget()
        with mock.patch.object(sw, "PIL_AVAILABLE", False):
            w._render_row("AAA", self._info(change_pct=3.0,
                                            ext_change_pct=-1.5,
                                            ext_session=None,
                                            spark=[1, 2, 3]))
        lines = [it for it in w.canvas.items
                 if it["kind"] == "line" and it["tags"] == ("row_AAA",)]
        self.assertEqual(lines[-1]["opts"]["fill"], sw.GREEN)


class ConfigTest(unittest.TestCase):
    def _load_with(self, payload):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            json.dump(payload, f)
            path = f.name
        old = sw.CONFIG_FILE
        try:
            sw.CONFIG_FILE = path
            return sw.load_config()
        finally:
            sw.CONFIG_FILE = old
            os.unlink(path)

    def test_defaults(self):
        cfg = self._load_with({})
        self.assertEqual(cfg["theme"], "gece")
        self.assertEqual(cfg["density"], "normal")
        self.assertAlmostEqual(cfg["opacity"], 0.97)
        self.assertTrue(cfg["symbols"])

    def test_invalid_values(self):
        cfg = self._load_with({"theme": "yok", "opacity": 5,
                               "density": "x"})
        self.assertEqual(cfg["theme"], "gece")
        self.assertEqual(cfg["opacity"], 1.0)
        self.assertEqual(cfg["density"], "normal")

    def test_settings_defaults(self):
        cfg = self._load_with({})
        self.assertTrue(cfg["always_on_top"])
        self.assertTrue(cfg["close_to_tray"])
        self.assertFalse(cfg["pause_when_closed"])
        self.assertTrue(cfg["extended_hours"])
        self.assertEqual(cfg["refresh_open"], 15)
        self.assertEqual(cfg["refresh_closed"], 60)

    def test_settings_invalid(self):
        cfg = self._load_with({
            "always_on_top": "belki",
            "close_to_tray": "hayır",
            "pause_when_closed": "evet",
            "refresh_open": "x",
            "refresh_closed": 9999,
        })
        self.assertTrue(cfg["always_on_top"])
        self.assertFalse(cfg["close_to_tray"])
        self.assertTrue(cfg["pause_when_closed"])
        self.assertEqual(cfg["refresh_open"], 15)
        self.assertEqual(cfg["refresh_closed"], 1440)


class HelperValidationTest(unittest.TestCase):
    def test_clean_symbol(self):
        for raw, want in (("aapl", "AAPL"), (" brk-b ", "BRK-B"),
                          ("^gspc", "^GSPC"), ("es=f", "ES=F"),
                          ("BTC-USD", "BTC-USD")):
            self.assertEqual(sw.clean_symbol(raw), want)
        for bad in ("", "   ", None, 1, ["A"], "A B", "TOOLONGSYMBOL"):
            self.assertIsNone(sw.clean_symbol(bad), bad)

    def test_clean_symbols(self):
        self.assertEqual(sw.clean_symbols(["aapl", "AAPL", 1, None, ""]),
                         ["AAPL"])
        self.assertEqual(sw.clean_symbols("nope"), sw.DEFAULT_SYMBOLS)
        self.assertEqual(sw.clean_symbols([]), sw.DEFAULT_SYMBOLS)
        many = ["S%d" % i for i in range(40)]
        self.assertEqual(len(sw.clean_symbols(many)), sw.MAX_SYMBOLS)

    def test_clean_positions(self):
        out = sw.clean_positions({
            "aapl": {"qty": "10", "avg": "150"},
            "BAD SYM": {"qty": 1, "avg": 1},
            "NEG": {"qty": -1, "avg": 5},
            "ZERO": {"qty": 0, "avg": 5},
            "LIST": [1, 2],
        })
        self.assertEqual(out, {"AAPL": {"qty": 10.0, "avg": 150.0}})
        self.assertEqual(sw.clean_positions([]), {})

    def test_portfolio_stats_string_qty(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app.cfg = {"positions": {"AAPL": {"qty": "10", "avg": "150"}}}
        self.assertTrue(app._has_portfolio())
        app.cfg = {"positions": {"AAPL": {"qty": -1, "avg": 1}}}
        self.assertFalse(app._has_portfolio())
        app.cfg = {"positions": {"AAPL": [1, 2]}}
        self.assertFalse(app._has_portfolio())

    def test_portfolio_stats_mixed_currency(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app.cfg = {"positions": {"AAPL": {"qty": 2, "avg": 100},
                                 "SAP": {"qty": 1, "avg": 100}}}
        app.last = {"AAPL": {"price": 110.0, "prev_close": 100.0,
                             "currency": "USD"},
                    "SAP": {"price": 120.0, "prev_close": 100.0,
                            "currency": "EUR"}}
        ok, val, cost, day, cur, mixed = app._portfolio_stats()
        self.assertTrue(ok)
        self.assertTrue(mixed)
        self.assertEqual(cur, "USD")
        self.assertAlmostEqual(val, 340.0)
        self.assertAlmostEqual(day, 40.0)


class HolidayCalendarTest(unittest.TestCase):
    def test_independence_day(self):
        # 4 Temmuz 2026 Cumartesi -> 3 Temmuz Cuma gözlenir
        self.assertIn(datetime.date(2026, 7, 3), sw.market_holidays(2026))
        # 2027 Pazar -> Pazartesi
        self.assertIn(datetime.date(2027, 7, 5), sw.market_holidays(2027))
        self.assertIn(datetime.date(2025, 7, 4), sw.market_holidays(2025))

    def test_new_year_spills_to_previous_year(self):
        # 1 Ocak 2022 Cumartesi -> 31 Aralık 2021 kapalı
        self.assertIn(datetime.date(2021, 12, 31), sw.market_holidays(2022))
        self.assertTrue(sw.is_market_holiday(datetime.date(2021, 12, 31)))
        self.assertIsNone(sw.market_phase(datetime.datetime(2021, 12, 31, 11, 0)))

    def test_holiday_phase_closed(self):
        self.assertIsNone(sw.market_phase(datetime.datetime(2026, 7, 3, 10, 0)))
        self.assertIsNone(sw.market_phase(datetime.datetime(2026, 12, 25, 10, 0)))

    def test_early_close(self):
        closes = sw.early_closes(2026)
        self.assertIn(datetime.date(2026, 11, 27), closes)   # Şükran sonrası
        self.assertIn(datetime.date(2026, 12, 24), closes)   # Noel arifesi
        self.assertNotIn(datetime.date(2026, 7, 3), closes)  # tatil günü
        # 13:05'te normal seans bitmiş olmalı
        self.assertEqual(sw.market_phase(datetime.datetime(2026, 11, 27, 13, 5)),
                         "post")
        self.assertEqual(sw.market_phase(datetime.datetime(2026, 11, 27, 12, 59)),
                         "regular")

    def test_holiday_properties(self):
        for year in range(2000, 2101):
            days = sw.market_holidays(year)
            self.assertEqual(len(days), len(set(days)), year)
            for d in days:
                self.assertLess(d.weekday(), 5, "%s %s" % (year, d))
            expected = 10 if year >= 2022 else 9
            self.assertEqual(len(days), expected, year)


class ConfigRobustnessTest(unittest.TestCase):
    """Bozuk config uygulamayı kilitlememeli; yazma atomik olmalı."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="swcfg-")
        self.old = sw.CONFIG_FILE
        sw.CONFIG_FILE = os.path.join(self.dir, "config.json")
        sw._CONFIG_FROM_BACKUP = False
        self._log_level = sw.log.level
        sw.log.setLevel(logging.CRITICAL)

    def tearDown(self):
        sw.log.setLevel(self._log_level)
        sw.CONFIG_FILE = self.old
        sw._CONFIG_FROM_BACKUP = False
        for name in os.listdir(self.dir):
            os.unlink(os.path.join(self.dir, name))
        os.rmdir(self.dir)

    def _write(self, payload, path=None, raw=None):
        path = path or sw.CONFIG_FILE
        with open(path, "w", encoding="utf-8") as f:
            if raw is not None:
                f.write(raw)
            else:
                json.dump(payload, f)

    def test_payload_fuzz_never_raises(self):
        payloads = [
            [], None, 5, "metin", {"theme": []}, {"theme": {}},
            {"x": "abc", "y": "abc"}, {"x": [], "y": {}},
            {"symbols": [1, None, "aapl", "", "AAPL"]},
            {"positions": {"A": {"qty": "5"}}},
            {"positions": {"A": [1]}}, {"positions": []},
            {"opacity": []}, {"density": []}, {"refresh_open": []},
            {"extended_hours": []},
        ]
        for payload in payloads:
            self._write(payload)
            cfg = sw.load_config()
            self.assertIsInstance(cfg, dict)
            self.assertIsInstance(cfg["symbols"], list)
            self.assertTrue(all(isinstance(x, str) for x in cfg["symbols"]))
            self.assertIsInstance(cfg["positions"], dict)
            self.assertIn(cfg["theme"], sw.PALETTES)
            self.assertIsNone(cfg["x"])

    def test_bom_and_truncated_file(self):
        self._write(None, raw="\ufeff" + json.dumps({"theme": "slate"}))
        self.assertEqual(sw.load_config()["theme"], "slate")
        self._write(None, raw='{"theme": "sl')
        self.assertEqual(sw.load_config()["theme"], "gece")

    def test_backup_recovery(self):
        self._write({"theme": "slate", "symbols": ["ONS"]},
                    path=sw.CONFIG_FILE + ".bak")
        self._write(None, raw="{ bozuk")
        cfg = sw.load_config()
        self.assertEqual(cfg["theme"], "slate")
        self.assertEqual(cfg["symbols"], ["ONS"])
        self.assertTrue(sw._CONFIG_FROM_BACKUP)

    def test_save_is_atomic_and_keeps_backup(self):
        self.assertTrue(sw.save_config({"theme": "gece"}))
        self.assertTrue(sw.save_config({"theme": "slate"}))
        with open(sw.CONFIG_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["theme"], "slate")
        with open(sw.CONFIG_FILE + ".bak", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["theme"], "gece")

    def test_save_failure_keeps_old_file(self):
        self.assertTrue(sw.save_config({"theme": "gece"}))
        with mock.patch.object(sw.os, "replace", side_effect=OSError("disk")):
            self.assertFalse(sw.save_config({"theme": "slate"}))
        with open(sw.CONFIG_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["theme"], "gece")

    def test_save_does_not_clobber_backup_after_recovery(self):
        self._write({"theme": "slate"}, path=sw.CONFIG_FILE + ".bak")
        self._write(None, raw="{ bozuk")
        cfg = sw.load_config()
        self.assertTrue(sw._CONFIG_FROM_BACKUP)
        sw.save_config(cfg)
        with open(sw.CONFIG_FILE + ".bak", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["theme"], "slate")


class _Resp:
    def __init__(self, payload=None, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise sw.requests.exceptions.HTTPError(
                "HTTP %s" % self.status_code, response=self)

    def json(self):
        return self._payload


def _chart_payload(closes, stamps, price=1.0, prev=1.0):
    return {"chart": {"result": [{
        "meta": {"regularMarketPrice": price, "chartPreviousClose": prev,
                 "currency": "USD", "shortName": "Test"},
        "timestamp": stamps,
        "indicators": {"quote": [{
            "close": closes, "open": list(closes),
            "high": list(closes), "low": list(closes),
            "volume": [1] * len(closes),
        }]},
    }]}}


class QuoteParsingTest(unittest.TestCase):
    def _fetch(self, payload, include_prepost=False, status=200):
        with mock.patch.object(sw.requests, "get",
                               return_value=_Resp(payload, status)):
            return sw.fetch_quote("TEST", include_prepost)

    def test_empty_result(self):
        with self.assertRaises(ValueError):
            self._fetch({"chart": {"result": []}})
        with self.assertRaises(ValueError):
            self._fetch({"chart": None})
        with self.assertRaises(ValueError):
            self._fetch({})

    def test_missing_meta_fields(self):
        payload = _chart_payload([1.0], [0])
        del payload["chart"]["result"][0]["meta"]["regularMarketPrice"]
        with self.assertRaises(ValueError):
            self._fetch(payload)

    def test_string_and_null_values_are_coerced(self):
        stamps = [calendar.timegm(datetime.datetime(2026, 11, 18, h).timetuple())
                  for h in (15, 16, 17)]
        payload = _chart_payload(["5", None, "6"], stamps, "6", "5")
        info = self._fetch(payload)
        self.assertEqual(info["price"], 6.0)
        self.assertEqual(info["prev_close"], 5.0)
        self.assertEqual(len(info["spark"]), 2)
        self.assertAlmostEqual(info["change_pct"], 20.0)

    def test_include_prepost_filters_session_bars(self):
        # UTC: pre 10:00, regular 15:00, post 22:00 (18 Kasım 2026, EST)
        stamps = [calendar.timegm(datetime.datetime(2026, 11, 18, h).timetuple())
                  for h in (10, 15, 22)]
        payload = _chart_payload([1.0, 2.0, 3.0], stamps, 3.0, 1.0)
        with_pre = self._fetch(payload, include_prepost=True)
        self.assertEqual(with_pre["ext_session"], "post")
        self.assertEqual(with_pre["ext_price"], 3.0)
        self.assertEqual(len(with_pre["spark"]), 3)
        without = self._fetch(payload, include_prepost=False)
        self.assertIsNone(without["ext_session"])
        self.assertEqual(len(without["spark"]), 1)
        self.assertEqual(without["spark"], [2.0])

    def test_retry_after(self):
        self.assertEqual(sw._retry_after(_Resp(headers={"Retry-After": "120"})),
                         120)
        self.assertEqual(sw._retry_after(_Resp(headers={"Retry-After": "1"})),
                         60)
        self.assertEqual(sw._retry_after(_Resp(headers={"Retry-After": "x"})),
                         sw.THROTTLE_429)
        self.assertEqual(sw._retry_after(None), sw.THROTTLE_429)


class FetchLoopTest(unittest.TestCase):
    def _app(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app.stop_flag = threading.Event()
        return app

    def test_429_skips_rest_and_backs_off(self):
        calls = []

        def fake(sym, extended=True):
            calls.append(sym)
            if sym == "A":
                raise sw.requests.exceptions.HTTPError(
                    "429", response=_Resp(status=429,
                                          headers={"Retry-After": "180"}))
            return {"symbol": sym}

        with mock.patch.object(sw, "fetch_quote", side_effect=fake):
            results, failures, attempted, backoff = self._app()._fetch_symbols(
                ["A", "B", "C"], True)
        self.assertEqual(calls, ["A"])
        self.assertEqual(results, {})
        self.assertEqual(failures, 1)
        self.assertEqual(attempted, 1)
        self.assertEqual(backoff, 180)

    def test_failures_do_not_stop_the_loop(self):
        def fake(sym, extended=True):
            if sym == "B":
                raise ValueError("bozuk")
            return {"symbol": sym}

        with mock.patch.object(sw, "fetch_quote", side_effect=fake):
            results, failures, attempted, backoff = self._app()._fetch_symbols(
                ["A", "B", "C"], True)
        self.assertEqual(sorted(results), ["A", "C"])
        self.assertEqual((failures, attempted, backoff), (1, 3, None))


class VersionSyncTest(unittest.TestCase):
    def test_version_files_match(self):
        root = os.path.dirname(os.path.abspath(sw.__file__))
        with open(os.path.join(root, "version_info.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("filevers=(%s)" % ", ".join(
            (sw.APP_VERSION.split(".") + ["0", "0", "0"])[:4]), text)
        with open(os.path.join(root, "installer.iss"), encoding="utf-8") as f:
            iss = f.read()
        self.assertIn('#define MyAppVersion "%s"' % sw.APP_VERSION, iss)


class DetailSeriesTest(unittest.TestCase):
    def test_staleness(self):
        panel = sw.DetailPanel.__new__(sw.DetailPanel)
        panel.series = {"1H": {}}
        panel.series_ts = {}
        self.assertTrue(panel._series_stale("1H"))
        panel.series_ts["1H"] = time.time()
        self.assertFalse(panel._series_stale("1H"))
        panel.series_ts["1H"] = time.time() - sw.TF_TTL["1H"] - 1
        self.assertTrue(panel._series_stale("1H"))


class SnapshotTest(unittest.TestCase):
    """Açılışta son fiyatlar gösterilebilmeli; bozuk dosya sorun çıkarmamalı."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="swsnap-")
        self.path = os.path.join(self.dir, "snapshot.json")
        self._patch = mock.patch.object(sw, "SNAPSHOT_FILE", self.path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    @staticmethod
    def _quote(**over):
        info = {"price": "10.5", "prev_close": "10.0",
                "change_pct": "5.0", "change_abs": "0.5",
                "spark": [1, 2], "spark_times": [0, 60],
                "spark_volumes": [], "spark_ohlc": [], "name": "Test"}
        info.update(over)
        return info

    def test_roundtrip_filters_and_coerces(self):
        sw.save_snapshot({"AAPL": self._quote(), "MSFT": self._quote(),
                          "BAD": self._quote(price=None)})
        quotes, ts = sw.load_snapshot(["AAPL", "EXIT"])
        self.assertEqual(sorted(quotes), ["AAPL"])
        self.assertEqual(quotes["AAPL"]["price"], 10.5)
        self.assertEqual(quotes["AAPL"]["change_pct"], 5.0)
        self.assertEqual(quotes["AAPL"]["spark"], [1, 2])
        self.assertIsInstance(ts, float)
        self.assertGreater(ts, 0)

    def test_empty_snapshot_is_not_written(self):
        sw.save_snapshot({})
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(sw.load_snapshot(["AAPL"]), ({}, None))

    def test_corrupt_snapshot_is_ignored(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ bozuk")
        self.assertEqual(sw.load_snapshot(["AAPL"]), ({}, None))
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"quotes": []}, f)
        self.assertEqual(sw.load_snapshot(["AAPL"]), ({}, None))

    def test_corrupt_fields_are_sanitized(self):
        sw.save_snapshot({"AAPL": {
            "price": 10, "prev_close": 9, "change_pct": 1,
            "spark": ["x", None, "11", 12],
            "spark_times": [1, "a"],
            "spark_ohlc": [[1, 2, 3, 4], [1, 2], "x",
                           [1, 2, None, 4], [9, 8, 7, 6]],
            "name": 5, "currency": None, "ext_session": "after"}})
        q = sw.load_snapshot(["AAPL"])[0]["AAPL"]
        self.assertEqual(q["spark"], [11.0, 12.0])
        self.assertEqual(q["spark_times"], [1.0])
        self.assertEqual(q["spark_ohlc"],
                         [(1.0, 2.0, 3.0, 4.0), (9.0, 8.0, 7.0, 6.0)])
        self.assertEqual(q["name"], "AAPL")
        self.assertEqual(q["currency"], "")
        self.assertIsNone(q["ext_session"])

    def test_zero_prev_close_rejected(self):
        # Sıfıra bölme değişim yüzdesinde çökme demek
        sw.save_snapshot({"AAPL": self._quote(prev_close=0)})
        self.assertEqual(sw.load_snapshot(["AAPL"])[0], {})

    def test_missing_spark_lists_default_empty(self):
        sw.save_snapshot({"AAPL": {"price": 1, "prev_close": 1,
                                   "change_pct": 0,
                                   "spark": "bozuk"}})
        quotes, _ = sw.load_snapshot(["AAPL"])
        self.assertEqual(quotes["AAPL"]["spark"], [])
        self.assertEqual(quotes["AAPL"]["spark_times"], [])
        self.assertEqual(quotes["AAPL"]["change_abs"], 0.0)


class MeiCleanupTest(unittest.TestCase):
    """onefile çökmelerinden kalan eski _MEI klasörleri temizlenmeli."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="swmei-")
        self.cur = os.path.join(self.dir, "_MEIcur")
        self.old = os.path.join(self.dir, "_MEIold")
        self.fresh = os.path.join(self.dir, "_MEInew")
        self.other = os.path.join(self.dir, "baska")
        for p in (self.cur, self.old, self.fresh, self.other):
            os.makedirs(p)
        past = time.time() - 7200
        os.utime(self.old, (past, past))
        self._envi = mock.patch.dict(os.environ,
                                     {"TEMP": self.dir, "TMP": self.dir})
        self._envi.start()
        self._mei = mock.patch.object(sw.sys, "_MEIPASS", self.cur,
                                      create=True)
        self._mei.start()

    def tearDown(self):
        self._mei.stop()
        self._envi.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_removes_only_stale_mei_dirs(self):
        with mock.patch.object(sw, "FROZEN", True):
            sw.cleanup_stale_mei(max_age=3600)
        self.assertTrue(os.path.isdir(self.cur))
        self.assertTrue(os.path.isdir(self.fresh))
        self.assertTrue(os.path.isdir(self.other))
        self.assertFalse(os.path.exists(self.old))

    def test_noop_when_not_frozen(self):
        with mock.patch.object(sw, "FROZEN", False):
            sw.cleanup_stale_mei(max_age=0)
        self.assertTrue(os.path.isdir(self.old))


class UpdateCheckTest(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(sw.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(sw.parse_version("StockWidget 1.2"), (1, 2, 0))
        self.assertEqual(sw.parse_version("1.10.9"), (1, 10, 9))
        for bad in ("", "sürüm", "v", None, 5, [1]):
            self.assertIsNone(sw.parse_version(bad), bad)

    def test_newer_release(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        self.assertTrue(app._newer_release({"version": "1.2.0"}))
        self.assertTrue(app._newer_release({"version": "1.10.0"}))
        self.assertFalse(app._newer_release({"version": "1.1.0"}))
        self.assertFalse(app._newer_release({"version": "1.0.9"}))
        self.assertFalse(app._newer_release({"version": "bozuk"}))
        self.assertFalse(app._newer_release({}))
        self.assertFalse(app._newer_release(None))

    def test_check_latest_release_parses_tag(self):
        with mock.patch.object(sw.requests, "get",
                               return_value=_Resp({"tag_name": "v1.2.0",
                                                   "html_url": "https://x"})):
            info = sw.check_latest_release()
        self.assertEqual(info["version"], "1.2.0")
        self.assertEqual(info["url"], "https://x")
        self.assertIsInstance(info["ts"], float)

    def test_check_latest_release_uses_name(self):
        with mock.patch.object(sw.requests, "get",
                               return_value=_Resp({"name": "StockWidget 1.3.1",
                                                   "html_url": "https://y"})):
            self.assertEqual(sw.check_latest_release()["version"], "1.3.1")

    def test_check_latest_release_bad_payloads(self):
        payloads = [None, [], {}, {"tag_name": "v1.0.0"},
                    {"tag_name": "bozuk", "html_url": "https://x"},
                    {"tag_name": "v1.0.0", "html_url": 5}]
        for payload in payloads:
            with mock.patch.object(sw.requests, "get",
                                   return_value=_Resp(payload)):
                self.assertIsNone(sw.check_latest_release(), payload)

    def test_check_latest_release_network_error(self):
        with mock.patch.object(sw.requests, "get",
                               side_effect=sw.requests.exceptions.ConnectionError):
            self.assertIsNone(sw.check_latest_release())
        with mock.patch.object(sw.requests, "get",
                               return_value=_Resp({}, status=500)):
            self.assertIsNone(sw.check_latest_release())

    def test_manual_check_reports_when_no_data(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app._update_busy = True
        app.root = mock.Mock()
        with mock.patch.object(sw, "messagebox") as mb:
            app._update_done(None, False)
        mb.showwarning.assert_called_once()
        self.assertFalse(app._update_busy)

    def test_manual_check_says_up_to_date(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app._update_busy = True
        app.root = mock.Mock()
        with mock.patch.object(sw, "messagebox") as mb:
            app._update_done({"version": sw.APP_VERSION,
                              "url": "u", "ts": time.time()}, False)
        self.assertTrue(mb.showinfo.called)
        self.assertFalse(mb.askyesno.called)

    def test_silent_update_does_not_pop_dialog(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app._update_busy = True
        app.root = mock.Mock()
        app.tray_icon = None
        app.menu = mock.Mock()
        app._menu_update_index = 7
        with mock.patch.object(sw, "messagebox") as mb, \
                mock.patch.object(sw, "write_update_cache") as cache:
            app._update_done({"version": "9.9.9", "url": "u",
                              "ts": time.time()}, True)
        self.assertFalse(mb.askyesno.called)
        self.assertFalse(mb.showinfo.called)
        self.assertTrue(app.menu.entryconfig.called)
        self.assertFalse(cache.called)   # tepsi yoksa uyarı da yok

    def test_manual_check_ignores_fresh_cache(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app.root = mock.Mock()
        app._update_busy = True
        fresh = {"version": "1.1.0", "url": "u", "ts": time.time()}
        newer = {"version": "9.9.9", "url": "u", "ts": time.time()}
        with mock.patch.object(sw, "read_update_cache", return_value=fresh), \
                mock.patch.object(sw, "check_latest_release",
                                 return_value=newer) as check, \
                mock.patch.object(sw, "write_update_cache") as cache:
            app._update_worker(False)
        check.assert_called_once()
        cache.assert_called_once_with(newer)
        self.assertEqual(app.root.after.call_args[0][0], 0)

    def test_silent_check_uses_fresh_cache(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app.root = mock.Mock()
        app._update_busy = True
        fresh = {"version": "1.1.0", "url": "u", "ts": time.time()}
        with mock.patch.object(sw, "read_update_cache", return_value=fresh), \
                mock.patch.object(sw, "check_latest_release") as check, \
                mock.patch.object(sw, "write_update_cache") as cache:
            app._update_worker(True)
        check.assert_not_called()
        cache.assert_not_called()

    def test_manual_update_falls_back_to_releases_page(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app.root = mock.Mock()
        app.menu = mock.Mock()
        app._menu_update_index = 0
        with mock.patch.object(sw, "messagebox") as mb, \
                mock.patch.object(sw, "webbrowser") as wb:
            mb.askyesno.return_value = True
            app._update_busy = True
            app._update_done({"version": "9.9.9"}, False)   # url yok
            wb.open.assert_called_once_with(sw.RELEASES_URL)
            wb.open.reset_mock()
            app._update_busy = True
            app._update_done({"version": "9.9.9",
                              "url": "https://github.com/x"}, False)
            wb.open.assert_called_once_with("https://github.com/x")

    def test_notify_only_once_per_version(self):
        app = sw.StockWidget.__new__(sw.StockWidget)
        app.tray_icon = mock.Mock()
        info = {"version": "9.9.9", "url": "u", "ts": time.time(),
                "notified": "9.9.9"}
        with mock.patch.object(sw, "write_update_cache") as cache:
            app._notify_update(info)
            self.assertFalse(app.tray_icon.notify.called)
            self.assertFalse(cache.called)
            info.pop("notified")
            app._notify_update(info)
            self.assertTrue(cache.called)
        self.assertTrue(app.tray_icon.notify.called)
        self.assertEqual(info["notified"], "9.9.9")


class UpdateCacheTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="swupd-")
        self.path = os.path.join(self.dir, "update.json")
        self._patch = mock.patch.object(sw, "UPDATE_FILE", self.path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_roundtrip_and_validation(self):
        self.assertIsNone(sw.read_update_cache())
        info = {"version": "1.2.0", "url": "https://x", "ts": 1.0}
        sw.write_update_cache(info)
        self.assertEqual(sw.read_update_cache(), info)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("[1, 2]")
        self.assertIsNone(sw.read_update_cache())
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ bozuk")
        self.assertIsNone(sw.read_update_cache())

    def test_write_failure_is_silent(self):
        sw.UPDATE_FILE = self.dir          # dosya değil, klasör
        sw.write_update_cache({"version": "1.0.0"})


if __name__ == "__main__":
    unittest.main()
