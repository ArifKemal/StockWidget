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


if __name__ == "__main__":
    unittest.main()
