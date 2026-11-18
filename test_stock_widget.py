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

    def test_session_from_meta(self):
        meta = {"currentTradingPeriod": {
            "pre": {"start": 100, "end": 200},
            "regular": {"start": 200, "end": 300},
            "post": {"start": 300, "end": 400},
        }}
        self.assertEqual(sw.session_from_meta(meta, 150), "pre")
        self.assertEqual(sw.session_from_meta(meta, 350), "post")
        self.assertIsNone(sw.session_from_meta(meta, 250))
        self.assertIsNone(sw.session_from_meta({}, 250))
        self.assertIsNone(sw.session_from_meta({"currentTradingPeriod": {
            "pre": {"start": None, "end": None}}}, 150))

    def test_quote_url(self):
        self.assertIn("includePrePost=true", sw.quote_url("AAPL"))
        self.assertNotIn("includePrePost", sw.quote_url("AAPL", False))
        self.assertIn("/chart/AAPL?", sw.quote_url("AAPL"))

    def test_session_labels(self):
        self.assertEqual(sw.SESSION_LABEL["pre"], "PÖ")
        self.assertEqual(sw.SESSION_LABEL["post"], "PS")

    def test_extended_session_fallback(self):
        # Meta'da pencere yoksa saat bazlı tahmin kullanılır
        self.assertEqual(sw.extended_session({}, 100, "pre"), "pre")
        self.assertEqual(sw.extended_session({}, 100, "post"), "post")
        self.assertIsNone(sw.extended_session({}, 100, "regular"))
        self.assertIsNone(sw.extended_session({}, 100))
        # Pencere varsa ama şu anı kapsamıyorsa tahmine düşülmez
        meta = {"currentTradingPeriod": {
            "pre": {"start": 1000, "end": 2000},
            "post": {"start": 3000, "end": 4000}}}
        self.assertIsNone(sw.extended_session(meta, 500, "pre"))


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
