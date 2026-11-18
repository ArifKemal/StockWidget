"""StockWidget için hızlı birim testleri (stdlib unittest)."""
import datetime
import json
import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
