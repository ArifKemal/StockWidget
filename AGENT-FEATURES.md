# StockWidget — Ücretsiz Paket Ajan Analiz Haritası

Bu dosya, sonraki ajanların kodu yeniden keşfetmeden değişiklik yapabilmesi
için **girdi/çıktı, veri akışı ve değişmez (invariant) haritası** verir.
Kullanıcı dokümanı `README.md`, genel mimari `AGENT.md`'dir; bu dosya
ücretsiz paket turunun sözleşmesidir.

## Dal, commit ve geri alma

| Ne | Değer |
|---|---|
| Dal | `main` (paket `f49011e`, ajan haritası `f9791c9`, görsel/README commit'leri sonrasında) |
| Geri dönüş etiketi | `checkpoint/pre-free-pack-2026-11-20` → `b91eb95` |
| Eski çalışma dalı | `feature/free-pack` birleştirildikten sonra **silindi** |

```powershell
# tüm paketi geri almak istersen (yeni bir dal üzerinde)
git switch -c geri-al checkpoint/pre-free-pack-2026-11-20
```

## Config şeması

`SETTINGS_DEFAULTS` tek kaynaktır; `load_config()` her anahtarı doğrular.
Bilinmeyen anahtarlar korunur, geçersiz satırlar sessizce atılır.

```json
{
  "theme": "gece | slate | grafit | acik",
  "opacity": 0.6,
  "density": "normal | compact",
  "always_on_top": true,
  "refresh_open": 15,
  "refresh_closed": 60,
  "pause_when_closed": false,
  "extended_hours": true,
  "close_to_tray": true,
  "sort_mode": "manual | change | symbol | value",
  "portfolio_show_cost": false,
  "symbols": ["AAPL", "MSFT"],
  "positions": {
    "AAPL": {"qty": 2, "avg": 100, "target": 200, "note": "uzun vade"}
  },
  "alarms": {
    "AAPL": {"above": 210, "below": 180, "pct": 5, "extended": false}
  },
  "x": 1474,
  "y": 441
}
```

Doğrulama zinciri:

1. `_read_config_file`: BOM toleransı, bozuk dosyada `config.json.bak`'a düşer,
   `_CONFIG_FROM_BACKUP` ile o tur yedeği ezmez.
2. `load_config`: kök `dict`, tema, opaklık, yoğunluk, sayısal alanlar.
3. `clean_symbols`: büyük harf, tekrarsız, `SYMBOL_RE`, en fazla `MAX_SYMBOLS`.
4. `clean_positions`: sonlu `qty > 0`, `avg ≥ 0`; opsiyonel `target > 0`,
   `note` en fazla 120 karakter.
5. `clean_alarms`: `above/below/pct > 0`, en az bir alan; `extended` bool.
6. `save_config`: `config.json.tmp` + `fsync` + `os.replace`, önceki iyi dosya
   `.bak`'a kopyalanır.

## Modül düzeyi sözleşmeler

| Fonksiyon | Girdi → Çıktı | Değişmez / not |
|---|---|---|
| `clean_symbol(value)` | herhangi → `str \| None` | büyük harf, boşluksuz, `SYMBOL_RE` |
| `clean_symbols(value)` | list → `list[str]` | tekrarsız, ≤20, boşsa varsayılan 5 |
| `clean_positions(value)` | dict → dict | `qty > 0`, `avg ≥ 0`; target/note opsiyonel |
| `clean_alarms(value)` | dict → dict | boş kural atılır; tüm eşikler pozitif |
| `alarm_quote(info, extended)` | info, bool → `(price, pct)` | PÖ/PS yalnızca `extended` ve `pre/post` |
| `evaluate_alarm(sym, info, rule, state, extended=False)` | → `list[str]` | `state[sym][kind]` latch; geçişte bir olay, koşul bozulunca reset |
| `portfolio_csv_rows(positions, last)` | dict, dict → `list[list]` | para birimleri ayrı; fiyat yoksa boş alan |
| `is_us_exchange(meta)` | dict → bool | bilinen ABD kodları; kod yoksa True |
| `_http_get(url, **kwargs)` | URL → Response | `_HTTP` Session + `_HTTP_LOCK`; testler burada patch'ler |
| `_retry_after(response, default=300)` | → `int` | sayı veya HTTP-date; 60–3600 s |
| `load_snapshot(symbols)` | → `(quotes, ts)` | yalnızca istenen semboller; bozuk alanlar temizlenir |
| `save_snapshot(quotes)` | → `None` | atomik; hata yutulur, uygulama çökmez |
| `cleanup_stale_mei(max_age=7g)` | → `None` | yalnızca `FROZEN`; çalışan `_MEIPASS` korunur |

`fetch_quote(symbol, include_prepost=True)` **tek** Yahoo chart isteği yapar;
aynı yanıttan fiyat, gün istatistikleri, spark/OHLC, `marketState`,
`exchangeTimezoneName`, `regularMarketTime` üretir. `include_prepost=False`
veya ABD dışı borsa ise `ext_session/ext_price` boştur.

## `StockWidget` çalışma zamanı durumu

| Alan | Anlam / değişmez |
|---|---|
| `cfg` | Doğrulanmış config; değişiklikte `save_config` çağrılır |
| `last` | Sembol → son info; açılışta snapshot ile doldurulur |
| `stale` | Açılışta snapshot varsa True; ilk canlı `results` ile False |
| `_view_symbols` | Görünüm sırası; cfg sırasının türevi, cfg yerine kullanılmaz |
| `_selected_idx` | Klavye seçimi; `_view_symbols` indeksi |
| `_render_keys` | `_render_row` önbelleği |
| `_spark_cache` | `(spark, w, h, renk)` → `PhotoImage`; ≥64 kayıtta temizlenir |
| `_snapshot_blob` | Son yazılan `last` JSON'u; aynıysa diske yazılmaz |
| `_alarm_state` | Runtime latch; config'e yazılmaz, alarm kaydında temizlenir |
| `_alarm_msg`, `_alarm_until` | Kart altbilgisinde 60 s gösterilen son alarm |
| `_alarms_dlg` | Açık alarm penceresi; `hide_window` kapatır |

`_render_row` anahtarı şunları içerir: fiyat, değişim %, tüm `ext_*` alanları,
ad, para birimi, `offline`, `stale`, aktif alarm türleri ve `tuple(spark)`.
**Yeni bir satır girdisi eklersen anahtara da ekle**, yoksa güncelleme çizilmez.

## Veri akışı sırası (bozulmaması gereken sıra)

1. `fetch_loop()` → `_fetch_cycle()` → `_fetch_symbols()`; 429'da kalan
   semboller atlanır, `_retry_after` + küçük jitter uygulanır.
2. Sonuç `self.queue` → `poll_queue` (200 ms) → `apply_data(results, offline)`.
3. `apply_data` sırası:
   - `offline` ve `stale` güncelle;
   - `self.last`'a yaz, listeden çıkanları buda;
   - `_check_alarms()` (bildirim, çizimden **önce**);
   - otomatik sıralamada `_ordered_symbols() != _view_symbols` ise
     `build_ui()`, değilse yalnızca değişen satırları `_render_row` ile çiz;
   - `_snapshot_blob` karşılaştır, yalnızca değiştiyse `save_snapshot`;
   - çevrimdışıysa başarısız satırları soluklaştır;
   - `_update_status`, `_update_portfolio`, açık detayı yenile.
4. `build_ui()` her çağrıda `_view_symbols`, `_render_keys`, `_spark_cache`,
   `_row_photos` temizler. `set_sort_mode` / `_move_symbol` / tema / yoğunluk
   değişimi `build_ui` üzerinden gider.

## Menü, kısayol ve pencere sözleşmeleri

- Ana menü: Ayarlar, Sembol ekle/çıkar, Portföy, Alarmlar, Hızlı çıkar,
  Sıralama, Yenile, Güncelleme denetle, Gizle, Çıkış.
- `_menu_update_index` **sabit indeks değildir**; menüye satır eklerken
  `m.index("end") + 1` mantığını koru.
- `row_menu` her sağ tıkta `_build_row_menu(sym)` ile yeniden kurulur:
  alarm kur, yukarı/aşağı taşı, sembol/fiyat kopyala, Yahoo'da aç, hedef/not,
  listeden çıkar.
- Klavye: `F5` yenile, `Up/Down` `_select_relative`, `Enter`
  `_activate_selected`, `Esc` `close_detail`.
- Alarm penceresi: boş alan = alarm yok; kayıt `clean_alarms` → `save_config`
  → `_alarm_state.clear()` → `build_ui()`. PÖ/PS kutusu alarm başınadır.
- Portföy penceresi: adet/maliyet/hedef/not; hedef negatifse kayıt reddedilir.
  CSV `utf-8-sig`, `;` ayraç; `portfolio_csv_rows` + para birimi toplamları.
- Gizleme tek yolu `hide_window()`; `_settings_dlg`, `_portfolio_dlg`,
  `_editor`, `_alarms_dlg` kapatılır.

## Test kancaları ve sınırlar

| Değişken | Etki |
|---|---|
| `SW_DATA_DIR` | Ayar/log/snapshot dizinini ayırır; gerçek `%APPDATA%` korunur |
| `SW_SMOKE=1` | 12 sn sonra kapanır (frozen GUI testi) |
| `SW_INSTANCE_SUFFIX` | Mutex + toggle/quit olay adlarını ayırır; kurulu kopya açıkken test |
| `SW_DISABLE_TRAY=1` | Tepsiyi kapatır (UI matrisi) |
| `SW_SCALE=1.25` | DPI ölçeğini geçici ezer (yalnızca matris) |

Testler ağ için `sw._HTTP.get`, dosya için `sw.CONFIG_FILE` patch'ler;
`requests.get` patch'i artık etkisizdir. Yeni ağ çağrısı `_http_get`
kullanmalı; yeni satır girdisi render anahtarına eklenmeli; sıralama
değişiklikleri cfg sembol sırasını bozmamalı; alarmlar ek Yahoo isteği
üretmemeli.

## Test envanteri

96 test başlıca şunları kapsar:

- config fuzz / BOM / kesik dosya / `.bak` kurtarma / atomik yazma,
- tatil takvimi (2000–2100), erken kapanış, yılbaşı kayması,
- quote/series parse, string/None/sonsuz alanlar, PÖ/PS filtresi,
- 429 + `Retry-After` (sayı ve HTTP-date), kısmi hata,
- snapshot roundtrip, bozuk alan temizliği, zero prev_close,
- eski `_MEI` temizliği, update cache, sürüm karşılaştırma,
- alarm doğrulama, above/below/pct latch, PÖ/PS seçimi,
- portföy CSV, para birimi toplamları, sıralama modları,
- render önbelleği, ABD dışı borsa PÖ/PS bastırma, metadata alanları.

Ek araçlar:

- `tools/ui_matrix.py`: 5 ölçek × 4 tema × 2 yoğunluk + alarm/portföy
  pencereleri; ağsız ve traysiz.
- `tools/smoke_frozen.py`: A) SW_SMOKE + snapshot + eski MEI, B) `--quit`,
  C) ikinci kopya; `SW_INSTANCE_SUFFIX=smoke` kullanır.

## CI ve release

- `test`: Python 3.11/3.12/3.13, ruff, coverage ≥30, `--version`.
- `audit`: `pip-audit` (ayrı Ubuntu job).
- `build`: PyInstaller onedir + onefile, exe sürümü, `SW_SMOKE`, UI matrisi,
  Inno derleme, sessiz kurulum → `--version` → sessiz kaldırma + log artifact.
- `release`: testler, iki derleme, portatif ZIP, SHA256SUMS, CycloneDX
  `sbom.json`, Winget/Scoop manifestleri, GitHub Release asset'leri.
- `ci.yml` yalnızca `main` push ve PR'da çalışır. Eski `feature/free-pack`
  dalı `main`e birleştirildikten sonra silindi; bu not geçmiş kaydıdır.
  Yeni değişikliklerde merge/PR öncesi yerel doğrulama zorunludur.

## Bilinçli sınırlar / açık uçlar

- Seans ve tatil takvimi NYSE; ABD dışı borsa tatilleri yok. `marketState`
  yalnızca gösterge/rozet içindir, veri toplama sıklığını değiştirmez.
- Alarmlar yalnızca uygulama açıkken çalışır; arka plan servisi yok.
- Otomatik indirme/kurulum yok (bilinçli güvenlik kararı); yalnızca bildirim.
- SignPath/Authenticode, Winget/Scoop deposuna PR dış hesap gerektirir;
  manifestler yalnızca üretilir, yayınlanmaz.
- UPX/Nuitka denenmedi; onefile açılış maliyeti antivirüs taramasına bağlı.
