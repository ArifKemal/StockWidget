# AGENTS.md — Borsa Widget (StockWidget)

Windows masaüstü hisse widget'ı. Tek dosya Python/Tkinter uygulaması; sembol listesi
`config.json`'dan gelir (varsayılan AAPL, MSFT, NVDA, GOOGL, AMZN), Yahoo Finance'in
ücretsiz chart endpoint'ini kullanır. UI metinleri Türkçe, UTF-8.

## Dosyalar
- `stock_widget.py` — uygulamanın tamamı (UI, veri çevrimi, tray, kısayol, portföy, ayarlar, otomatik başlatma)
- `README.md` — kullanıcı dokümanı (indirme, hızlı başlangıç, özellikler, veri kaynağı, ayarlar)
- `AGENT.md` — bu dosya: mimari kurallar + değişiklik günlüğü
- `docs/agent/AGENT-FEATURES.md` — ücretsiz paket turunun ajan analiz haritası (config
  şeması, fonksiyon sözleşmeleri, veri akışı, test kancaları, geri alma)
- `AGENT-MEMORY.md` — yalnızca yerel ajan hafızası; `.gitignore`'da, repoya
  girmez (kullanıcı tercihleri, kurulum durumu, regresyon tuzakları)
- `tests/test_stock_widget.py` — stdlib `unittest` birim testleri (ağa çıkmaz)
- `market_calendar.py` — ABD/BIST/kripto profilleri, TR tatilleri (tipli modül)
- `i18n.py` — TR/EN arayüz çevirisi; Tk metinlerini tek noktadan çevirir
- `mypy.ini` — kademeli tip kontrolü (önce `market_calendar.py`)
- `LICENSE` — MIT (2026 Arif Kemal)
- `packaging/StockWidget-onefile.spec` — PyInstaller **onefile** derleme tanımı (ana indirme)
- `packaging/StockWidget.spec` — PyInstaller onedir derleme tanımı (ZIP yedeği)
- `packaging/installer.iss` — Inno Setup 6 kullanıcı bazlı kurulum betiği (isteğe bağlı)
- `packaging/version_info.txt` — exe sürüm bilgisi (PyInstaller)
- `tools/bump_version.py` — sürümü kaynak + `packaging/version_info.txt` + `packaging/installer.iss`'e yazar
- `tools/screenshot.py` — README görsellerini gerçek uygulamadan üretir
  (sabit sahte veri, ağsız, 2x; widget topmost, backdrop onun altında;
  kısayol thread'i "registered" ile değiştirilir; boş yakalarsa mevcut
  dosyayı silmez, sıfırdan farklı çıkış kodu verir)
- `tools/ui_matrix.py` — tema × yoğunluk × `SW_SCALE` GUI matrisi (ağsız, traysiz)
- `tools/render_manifests.py` — Winget/Scoop şablonlarını sürüm+hash ile doldurur
- `packaging/winget`, `packaging/scoop` — ücretsiz dağıtım manifest şablonları
- `.github/dependabot.yml` — pip ve GitHub Actions güncellemesi; şu an
  `open-pull-requests-limit: 0` ile kapalı (depo tek dallı kalsın diye)
- `.github/workflows/ci.yml` / `release.yml` — test+derleme / etiketli sürüm
- `tools/legacy/toggle.vbs` — kaynak modunda masaüstü kısayolu (kurulu sürümde `StockWidget.exe --toggle`)
- `tools/legacy/install_startup.ps1` / `tools/legacy/uninstall_startup.ps1` — eski kaynak modu otostart betikleri
- `requirements.txt` — requests, pystray, pillow (pystray/pillow opsiyonel)
- `docs/ekran-ana.png`, `docs/ekran-detay.png`, `docs/ekran-ayarlar.png` —
  README ekran görüntüleri (`tools/screenshot.py` üretir; veri sahte, ağ yok)
- `docs/imzalama.md` — kod imzalama (SmartScreen / SignPath) durumu ve adımları
- `config.json` / `sw.log` / `snapshot.json` / `update.json` — kaynak modunda çalışma zamanı dosyaları, `.gitignore`'da
- `%APPDATA%\StockWidget\` — kurulu/portatif sürümde ayar + log + son fiyatlar (SW_DATA_DIR ile değiştirilebilir)
- `build/`, `dist/`, `dist-onefile/`, `Output/` — derleme çıktıları, `.gitignore`'da

## Repo düzeni ve geri dönüş (2026-11-22)

Tek dal: **main**. Klasör düzeni:

- Kök: `stock_widget.py`, `market_calendar.py`, `i18n.py`, `README.md`,
  `LICENSE`, `AGENT.md`, `mypy.ini`, `requirements*.txt`
- `tests/test_stock_widget.py` — unittest
- `assets/stock.ico` — kaynak + PyInstaller ikonu
- `packaging/` — `.spec`, `installer.iss`, `version_info.txt`, Winget/Scoop
- `docs/agent/AGENT-FEATURES.md`; `AGENT-MEMORY.md` (yerel, `.gitignore`'da)
- `tools/` ve `tools/legacy/` (eski kaynak-modu scriptleri)

Komutlar **kök dizinden** çalışır:
```powershell
python -m unittest discover -s tests -t .
python -m PyInstaller --noconfirm --clean packaging/StockWidget.spec
python -m PyInstaller --noconfirm --clean --distpath dist-onefile packaging/StockWidget-onefile.spec
ISCC.exe packaging\installer.iss
```

Klasör düzeni öncesi geri dönüş:
`git switch -c geri-al checkpoint/pre-reorg-2026-11-22`
(etiket `0c07b84`). Ayrıntılı kalıcı notlar:
`AGENT-MEMORY.md` (yerel; `.gitignore`'da).

## Mimari kuralları (bozmadan değişiklik yap)
- **Tk tek thread.** Ağ işi `fetch_loop` thread'inde döner; sonuçlar `self.queue`'ya yazılır,
  `poll_queue` (root.after ~150–200 ms) ana thread'de tüketir. **Thread'den Tk widget'ına asla dokunma.**
- **Tray (pystray) callback'leri kendi thread'inde çalışır.** Tk'ye dokunanlar (`toggle_visibility`,
  `open_symbol_editor`, `exit_app`, `_tray_toggle_startup`) `root.after(0, ...)` ile ana thread'e taşınır
  (`_create_tray_icon`); sadece `refresh_now` (`threading.Event.set`) thread-safe olup doğrudan çağrılabilir.
- Her dış olay kuyruk üzerinden gelir: `self.queue` (fiyat verisi + offline bayrağı),
  `self.hotkey_queue` (kısayol olayları: `registered` / `unavailable` / `toggle`).
- **Güncelleme denetimi** ayrı bir daemon thread'de ağ isteği yapar; sonuç
  `root.after(0, ...)` ile ana thread'e taşınır. `update.json` en fazla 24 saatte
  bir tazelenir (`UPDATE_TTL`), böylece sessiz denetim günde 1 GitHub isteğidir.
- **`snapshot.json`** yalnızca ana thread'de (`apply_data`) atomik yazılır; açılışta
  `__init__` içinde `build_ui`'den önce okunur. İçeriği elle bozulmuş olabileceği
  için `load_snapshot` tüm sayıları ve grafik listelerini yeniden doğrular.
  Aynı fiyat paketi tekrar yazılmaz (`_snapshot_blob`).
- **Sıralama yalnızca görünümdür:** `cfg["symbols"]` elle sırayı korur;
  `_ordered_symbols()` `_view_symbols`'ü üretir. `_release`, sağ tık menüsü ve
  klavye daima `_view_symbols` kullanmalı; cfg indeksine göre satır açma.
- **Alarm state'i çalışma zamanındadır** (`_alarm_state`), config'e yazılmaz.
  `evaluate_alarm` eşik geçişinde bir kez olay üretir; koşul bozulunca sıfırlanır.
  Alarm, PÖ/PS fiyatını yalnızca hem global hem alarm ayarı açıksa kullanır.
- **Çizim önbelleği:** `_render_row` aynı anahtarla çağrılırsa hiçbir şey silmez;
  sparkline `_spark_cache` ile `PhotoImage` düzeyinde paylaşılır. `build_ui`
  iki önbelleği de temizler. Yeni çizim girdisi eklerken `_render_row` anahtarına
  eklemeyi unutma.
- **HTTP:** `_HTTP` (requests.Session) + `_HTTP_LOCK`; testler `sw._HTTP.get`
  patch'ler. Yeni ağ çağrıları `requests.get` değil `_http_get` kullanmalı.
- Test kancaları: `SW_SCALE` DPI ölçeğini, `SW_DISABLE_TRAY=1` tepsiyi kapatır,
  `SW_INSTANCE_SUFFIX` mutex/olay adlarını ayırır (kurulu kopya açıkken duman
  testi çalıştırmak için). Üçü de yalnızca test amaçlıdır.
- **Piyasa profili:** `_phase_for` ABD için `market_phase`, BIST için
  `market_calendar.tr_phase`, kripto için 24/7 kullanır. Yeni bir borsa türü
  eklerken `exchange_profile` + `_phase_for` + `_market_summary` üçlüsünü
  birlikte güncelle; `pause_when_closed` `_market_active` üzerinden çalışır.
- **i18n:** Yeni bir kullanıcı metni eklerken Tk `text`/`label` otomatik
  çevrilir; `i18n._DIRECT` sözlüğüne İngilizce karşılığını ekle. Log/CLI ve
  config anahtarları çevrilmez. Varsayılan dil `tr` olduğu için testler korunur.
- **Tanılama:** `redact_config` portföy adet/maliyet ve alarm eşiklerini
  paketlemez; `diagnostics_info` saf fonksiyondur, test edilir.
- Döngüler `self.stop_flag` (threading.Event) ile durur; çıkışta thread'ler daemon olduğu için
  süreç sonlanır, kaynaklar (hotkey kaydı, mutex) serbest kalır.
- Tek örnek: `acquire_single_instance()` adlandırılmış mutex. İkinci kopya `--toggle`
  ise `TOGGLE_EVENT`'i, `--quit` ise `QUIT_EVENT`'i işaretler (`request_signal`),
  aksi halde sessizce çıkar. Ana kopya `signal_watch_loop` ile
  `WaitForMultipleObjects` üzerinden bu olayları `hotkey_queue`'ya aktarır.
- **Donmuş (exe) mod ayrımı:** `FROZEN` iken `ASSET_DIR` = `sys._MEIPASS` (ikon,
  README, LICENSE), kalıcı veri `DATA_DIR` = `%APPDATA%\StockWidget` (veya
  `SW_DATA_DIR`). Kaynak modunda `ASSET_DIR` = proje klasörü. Eski script yanındaki
  `config.json` ilk açılışta `migrate_legacy_config()` ile taşınır. Otostart
  komutu `app_launch_command()`: donmuşta exe, kaynakta `pythonw + script`.
- **Kurulum ve sinyaller:** Inno `PrepareToInstall` yükseltmeden önce
  `StockWidget.exe --quit` çalıştırır; `[UninstallRun]` aynısını yapar. `--quit`
  mutex'ten önce işlenir; çalışan kopya yoksa uygulamayı başlatmadan çıkar.
  `poll_queue` "quit" olayında `exit_app()` çağırıp `return` eder; `finally`
  bloğu `stop_flag` set edildiğinde `root.after` planlamaz (destroy sonrası
  `TclError` yok).
- Pencere gizleme tek yol: `hide_window()` (detay panelini de kapatır). `root.withdraw()`'ı
  doğrudan çağırma — açık detay paneli ekranda asılı kalır. Karttaki ✕ ve
  `WM_DELETE_WINDOW` `close_window()`'a bağlıdır: `close_to_tray` açık ve tepsi ya da
  global kısayol çalışıyorsa gizler, aksi halde `exit_app()` (pencere kaybolmasın).
- **Tema renkleri modül globalleridir.** `apply_palette(name)` bunları `globals()` ile
  yeniden bağlar; çizim kodu renkleri **çağrı anında** okuduğu için tema değişimi anında yansır.
  Yeni bir renk kullanacaksan önce `PALETTES` sözlüğüne anahtar ekle, sabit hex yazma.
- **Grafikler PIL ile çizilir** (`render_spark`): 4× süper-örnekleme + LANCZOS küçültme;
  `PhotoImage` referansları (`_row_photos`, `_chart_photo`) GC'ye karşı tutulur.
  PIL yoksa canvas çizimine düşülür (`PIL_AVAILABLE`).
- **Yoğunluk** satır içi dikey ölçüleri `ro()` (satır ölçeği) ile çarpar; yatay ölçüler `s()`
  kalır. Yeni satır içi dikey ofset eklerken `s()` değil `ro()` kullan.
- **Tanılama `sw.log`'a yazılır** (`setup_logging`); `pythonw.exe`'de stdout/stderr yoktur.
  Yeni hata yollarında `log.exception` / `log.warning` kullan, `print` kullanma.
- **Ayarlar penceresi** (`open_settings_editor`): iki sütunlu gruplu kartlar, anında
  uygulama, altta Sıfırla/Kapat. Renkler modül globali olduğu için tema değişimi
  `_refresh_settings()` ile pencereyi `after_idle` yeniden kurar (`_build_settings`);
  yeni ayar eklerken `SETTINGS_DEFAULTS` + `load_config` doğrulaması + satır ekle.
  Widget'lar `cfg`'yi doğrudan okur; her değişiklik `save_config` ile diske yazılır.

## Veri ve API disiplini (ücretsiz endpoint, 429 riski)
- Sembol başına döngüde **1 istek**; semboller arasında 0.4 s bekleme.
- Aralıklar: piyasa açık 15 dk, kapalı 60 dk (Ayarlar'dan 5–30 / 15–120 dk);
  hata sonrası 90 s. HTTP 429 → `Retry-After` (60–3600 s; yoksa 300 s) beklenir
  ve kalan semboller atlanır. `pause_when_closed` açıksa piyasa
  kapalıyken hiç istek gönderilmez, yalnızca 60 s'de bir saat kontrol edilir.
- Endpoint: `query1.finance.yahoo.com/v8/finance/chart/{sembol}?interval=5m`
  + açık `period1`/`period2` (aktif işlem gününün 04:00–20:05 ET penceresi).
  `range=1d` piyasa öncesi saatlerde önceki seansa düşebildiği için kullanılmaz.
- `fetch_loop()` turu `_fetch_cycle()` içinde çalışır ve try/except ile sarılır:
  beklenmeyen bir hata veri döngüsünü kalıcı olarak durdurmaz.
- Yeni özellik eklerken istek sayısını artırma; mevcut yanıttaki alanları kullan
  (fiyat, önceki kapanış, para birimi, meta, timestamp serisi).
- İstisna: detay paneli zaman aralıkları (**1H/1A/1Y**) — yalnızca sekme ilk açıldığında
  1 istek (`fetch_series`), `_SERIES_CACHE` TTL 15 dk / 1 saat / 1 saat. 1G her zaman
  döngü verisinden çizilir. Sonuç thread'den `_res` kuyruğuyla döner, `render()` ana
  thread'de çağrılır; panel kapalıysa `_poll_results` kendini yeniden planlamaz.

## Bu oturumda eklenen/değişenler (kronolojik)
1. **Detay paneli** — satıra tıklayınca grafik + meta; tekrar tıklayınca kapanır; pencere gizlenince kapanır.
2. **Global kısayol: Ctrl+Alt+S** — `hotkey_loop()` ayrı thread'de `RegisterHotKey` +
   `PeekMessageW` (WM_HOTKEY = 0x0312); `MOD_NOREPEAT` desteklenmezse sade moda düşer;
   `PeekMessage` döngüsü 50 ms, çıkışta `UnregisterHotKey`.
   Sonuç `hotkey_queue` → `poll_queue` → `toggle_visibility()`.
   Kayıt başarısızsa Ayarlar penceresindeki kısayol etiketi "kaydedilemedi" olur (`_set_hotkey_hint`).
   Gizleme artık `hide_window()` üzerinden gider (detay paneli tutarlılığı).
3. **README** — kısayol özelliği, kullanım satırı ve sorun giderme notu eklendi.
4. **Thread güvenliği** —
   - Tray menüsü callback'leri (`_create_tray_icon`) artık `root.after(0, ...)` ile ana thread'e
     taşınıyor; pystray callback'leri tray thread'inde çalıştığı için doğrudan Tk çağrısı
     donma/çökme riski taşıyordu.
   - Sembol doğrulama (`do_add`) ayrı thread'de; sonuç `root.after` ile UI'a dönüyor — ana thread artık donmuyor.
   - `poll_queue` try/except/finally ile sağlamlaştırıldı: bir istisna kuyruk döngüsünü kalıcı durdurmaz.
5. **Doğruluk düzeltmeleri** —
   - Satır fiyatı artık `fmt_money` kullanıyor (para birimi tutarlı); `$` hardcoded değildi.
   - Boş sembol listesi "çevrimdışı" sayılmıyor (`fetch_loop`).
   - Çevrimdışıyken başarısız satırların fiyatı da soluklaşıyor (`apply_data`).
   - `acquire_single_instance` `CreateMutexW.restype` düzeltildi (64-bit HANDLE kırpılması).
6. **NYSE tatil günleri** — `market_holidays()` + yardımcılar (`_nth_weekday`, `_last_weekday`,
   `_easter`, `_observed`); `market_open()` tatil günlerini kapalı sayar.
7. **tools/legacy/toggle.vbs** — `taskkill /F` davranışı açıklandı (WM_CLOSE gizler, sonlandırmaz).
8. **Grafik zaman aralıkları** — detay paneline `1G / 1H / 1A / 1Y` sekmeleri
   (`TF_TABS`, `TF_LABEL`). 1G döngü verisinden; 1H/1A/1Y `fetch_series()` ile tembel
   çekilir (modül düzeyi `_SERIES_CACHE`, `TF_TTL`). Sonuç `_res` kuyruğu →
   `root.after(200, _poll_results)` → `render()`. Panel 300×398; grafik 140–202,
   eksen etiketleri 212; istatistikler 243–349; meta 381.
9. **Retry + ✕ davranışı** —
   - `set_tf` aynı sekmede hata aldıysa yeniden deniyor (erken dönüş yalnızca yüklü /
     yükleniyor durumlarında; hata varsa `_fetch_series` tekrar başlar).
   - Sağ üstteki ✕ artık `hide_window()` çağırıyor (çıkış değil, **tray'e gizle**);
     tam çıkış sağ tık → **Çıkış** veya tray menüsü → **Çıkış**.
10. **Grafik hover (belirgin)** — detay grafiğinde `<Motion>` ile en yakın nokta seçilir;
    parlak (ACCENT) dikey imleç + yatay seviye çizgisi + beyaz halkalı nokta ve grafiğin
    altında rozetli okuma çubuğu (zaman · büyük fiyat · renkli yüzde rozeti). 1G'de baz
    önceki kapanış, diğer aralıklarda serinin ilk noktası. Bunun için `fetch_quote`
    `spark_times` döndürür (kapanışlarla hizalı, 60 noktaya indirgenmiş); grafik
    geometrisi `_plot`'ta saklanır, eksen etiketleri `axislbl` ile gizlenir. `round_rect`
    artık `tags` alır; hover öğeleri `chov` etiketiyle tek seferde silinir.
11. **UI cila + kişiselleştirme** —
    - `PALETTES` + `apply_palette()`: Gece / Slate / Grafit / Açık temalar; sabit hex renkler
      `CARD`, `FG`, `RAISED`, `TRACK`, `MENU_BG`… globallerine taşındı.
    - Sağ tık menüsüne **Tema / Opaklık / Yoğunluk** alt menüleri; `config.json`'da
      `theme`, `opacity`, `density` saklanır (`load_config` doğrular).
    - `density=compact` → `ROW_H` 40, satır içi dikey ölçüler `ro()` ile ölçeklenir.
    - Fiyatlar `pick_mono()` ile tabular (Cascadia Mono/Consolas) yazı tipinde → rakam
      değişince zıplama yok. Rozetlerde ▲/▼ trend oku.
    - Satır alt satırında şirket adı (`_ellipsize` ile kısaltılır) ve göreli zaman
      (`_rel_time`, `_status_tick` 20 sn'de bir tazeler).
    - Sparkline ve detay grafiği `render_spark()` ile anti-aliased: gradyan alan dolgusu,
      ince grid, önceki kapanış kesikli çizgisi, yuvarlak uç noktası.
12. **Portföy modu** — `config.json`'da `positions` (`{sembol: {qty, avg}}`);
    `_portfolio_stats()` toplam değer / maliyet / günlük P&L hesaplar (fiyat `self.last`'tan).
    `_has_portfolio()` `_row_height()`'a s(26) ekler; ana kartta **Portföy** şeridi
    (`_draw_portfolio`, `pf` etiketi, `apply_data` → `_update_portfolio`).
    Düzenleme: sağ tık → **Portföy…** (`open_portfolio_editor`; boş satır = pozisyon silinir).
13. **Grafik paketi** — `fetch_quote`/`fetch_series` artık OHLC + hacim döndürür
    (`spark_ohlc`, `spark_volumes`; seride `ohlc`, `volumes`). `render_spark(volumes=...)`
    alt %22'de hacim çubukları; `render_candles()` mum grafiği; `downsample_ohlc()`
    en çok 70 muma indirger. Detayda sağ fiyat ekseni (`_draw_axis`; grafik x2'si
    s(28) daraltılır) ve sekme satırının sağında **mum/çizgi** düğmesi (`modebtn`,
    `DetailPanel.mode`).
14. **Altyapı** — `setup_logging()` → döndürülen `sw.log` (RotatingFileHandler, 200 KB×2);
    `poll_queue` hataları `log.exception`, fetch hataları `log.warning`.
    `tests/test_stock_widget.py` stdlib `unittest` (tatiller, fmt, palet, config, render,
    downsample); `.gitignore` + git deposu.
15. **Doküman tazeleme** — README baştan yazıldı: portföy, tema/opaklık/yoğunluk,
    mum/çizgi + hacim, hover okuması, tray/kısayol davranışı, `config.json` anahtar
    tablosu, gerçek dosya listesi, sınırlar ve sorun giderme. Kodla çelişen iki nokta
    düzeltildi: hacim çubukları **çizgi** modunda çizilir (mum modunda değil), seri
    seyreltme 1H/1A/1Y için 150, gün içi için 60 nokta. AGENT.md dosya listesi
    güncellendi; "iki sembol takip eder (ONDS, BRUN)" yerine `config.json`'dan gelen
    liste yazıldı (bugünkü varsayılan: AAPL, MSFT, NVDA, GOOGL, AMZN).
16. **Dağıtım / herkesin kullanabileceği sürüm** —
    - Exe/donmuş mod: `APP_NAME`, `APP_VERSION`, `FROZEN`, `ASSET_DIR`, `ICON_FILE`,
      `_data_dir()` (`SW_DATA_DIR` override), `DATA_DIR`/`CONFIG_FILE`/`LOG_FILE`,
      `migrate_legacy_config()`, exe'ye uygun `set_startup()`.
    - `--toggle` / `--quit` / `--version` / `--paths`; `TOGGLE_EVENT` + `QUIT_EVENT`
      isimli Win32 olayları, `signal_watch_loop` (`WaitForMultipleObjects`).
      İkinci kopya sinyal gönderip çıkar; `--quit` mutex'ten önce işlenir.
    - `poll_queue` "quit" olayını işler ve destroy sonrası `root.after` planlamaz.
      Tepsi başlatma hatası uygulamayı düşürmez (`_tray_run` loglar).
    - Paketleme: `packaging/StockWidget.spec` (PyInstaller onedir, `--noconsole`, ikon, sürüm),
      `packaging/installer.iss` (Inno Setup 6, kullanıcı bazlı `%LOCALAPPDATA%\Programs\StockWidget`,
      kısayollar, isteğe bağlı otostart, yükseltmede `--quit`, kaldırmada ayarları korur),
      `packaging/version_info.txt`, `tools/bump_version.py`.
    - CI/release: `.github/workflows/ci.yml` her push'ta test + PyInstaller;
      `release.yml` `v*` etiketinde portatif ZIP + kurulum paketini Release'e ekler.
    - `LICENSE` (MIT), README indirme-önce yeniden yazıldı, `docs/` ekran görüntüleri
      `tools/screenshot.py` ile üretildi.
    - GitHub'da `v1.0.0` etiketiyle Release #2 başarıyla yayınlandı; portatif ZIP'in
      SHA-256'sı indirilerek doğrulandı (`b1766a8e…`), kurulum paketi de aynı iş
      akışında üretildi.
    - Repo metadata: açıklama, homepage (`releases/latest`) ve topics API ile
      ayarlandı (`gh` gerekmeden, git kimlik bilgisindeki token kullanıldı).
    - Release ZIP düzeltmesi: `v1.0.0` asseti README/LICENSE içermiyordu (workflow
      düzeltmesi etiketten sonra geldi). Doğrulanmış exe bozulmadan ZIP'e
      `README.md`, `LICENSE` ve `docs/` eklendi; asset değiştirildi
      (`sha256:bc34995d…`). `Compress-Archive` (PS 5.1) ters eğik çizgi yazdığı
      için ZIP, `/` ayırıcı kullanan Python `zipfile` ile üretildi — ileride yerel
      paketlemede buna dikkat. CI'daki `pwsh` bu sorunu yaşamaz.
    - Doğrulama: 13 test, kaynak ve exe `--version`/`--toggle`/`--quit`, exe'nin
      `%APPDATA%` yerine `SW_DATA_DIR`'a config+log yazması, ISCC derlemesi.
      Kurulumun sessiz çalıştırılması bu makinede güvenlik ilkesi nedeniyle
      denenemedi; betik ISCC ile hatasız derlendi.
17. **Kurulum ön kontrolü + kısıtlı makine desteği** —
    - Bu makinede kurulumun sessizce ölmesinin nedeni bulundu: Inno, destek
      dosyalarını `%TEMP%`'e açamıyordu (`Error 5`). `TEMP`/`TMP` yazılabilir bir
      klasöre alınınca kurulum dosyaları kopyaladı; ancak setup sürecine
      Başlat menüsü klasörü, kısayol (`IPersistFile::Save`) ve HKCU yazımı
      politika ile engellendi (`Error 5`). Yani sorun betikte değil, ortamda.
    - `packaging/installer.iss`: `PrepareToInstall` artık `{app}` ve HKCU yazılabilirliğini
      deniyor; engellenmişse ham hata yerine Türkçe mesaj + portatif ZIP önerisi
      verip temiz çıkıyor (oluşturduğu boş klasörü siliyor). `[Icons]` girdileri
      `CanCreateShortcuts` / `CanCreateDesktopIcon` ile korunuyor: kısayol
      yazılamazsa kurulum düşmüyor, `ssPostInstall`'da bilgi kutusu çıkıyor.
    - Notlar: ISPP satır başındaki `#13#10`'ı preprocessor direktifi sanıyor;
      Pascal Script'te yerel `const` bölümü desteklenmiyor (`var` kullan).
    - README sorun giderme: `Error 5`, `%TEMP%` izni ve "kısayol oluşmadı ama
      kuruldu" başlıkları eklendi.
    - `Output/StockWidget-1.0.0-setup.exe` yeniden derlendi ve Release asseti
      değiştirildi (sürüm aynı; yalnızca kurulum betiği iyileşti,
      `sha256:14732457…`).
    - Portatif ZIP son hâli: repo dokümanlarıyla eşitlendi (`README.md`,
      `LICENSE`, `docs/*.md` + ekran görüntüleri), `sha256:64b9c458…`.
18. **Tek dosya (onefile) dağıtımı — v1.1.0'ın ana indirmesi** —
    - Ürün küçük bir widget olduğu için kurulum paketi ana indirme olmaktan
      çıkarıldı. Yeni sıralama: `StockWidget-<sürüm>.exe` (onefile, ana),
      `StockWidget-<sürüm>-setup.exe` (isteğe bağlı), `-portable.zip` (yedek).
    - `packaging/StockWidget-onefile.spec` eklendi (`EXE(...)` içine `a.binaries` /
      `a.datas`, `COLLECT` yok, `runtime_tmpdir=None`, `console=False`). Yerel
      derleme ~26 MB; `--version`, `--paths`, `--toggle`, `--quit` uçtan uca
      denendi. Onefile her açılışta `%TEMP%`'e açıldığı için ilk pencere birkaç
      saniye gecikir; README bunu açıkça yazıyor ve ZIP'i yedek gösteriyor.
    - `ci.yml`: onedir + onefile derlemesi ve iki exe için `--version` duman
      testi. `release.yml`: onefile derleme, `StockWidget-$V.exe` üretimi +
      sürüm doğrulaması, 3 asset yükleme.
    - `tools/bump_version.py` artık `packaging/installer.iss` içindeki `MyAppVersion`
      varsayılanını da günceller (UTF-8 BOM korunarak; BOM yoksa Inno Türkçe
      karakterleri bozar).
    - Not: onefile testinde "ikinci kopya" hatası görüldü; nedeni uygulama
      değil, önceki testlerden kalan bir `pythonw.exe`'nin mutex'i tutmasıydı.
      Test öncesi `Get-Process pythonw` kontrol edilmeli.
    - Not: penceresiz (`console=False`) exe'nin stdout'u PowerShell `&` ile
      **boş** gelir; sürüm doğrulaması `cmd /c` ile (çıktı yakalanarak)
      yapılmalı. `v1.1.0` Release'inin ilk koşusu tam bu yüzden düştü; etiket
      düzeltilmiş commit'e taşınıp yeniden atıldı.
    - README "İndir" tablosu yeniden sıralandı; tek dosya / kurulum / ZIP
      bölümleri, "Aç / kapa" tablosu ve Paketleme bölümü güncellendi.
    - `v1.1.0` yayınlandı (Release başarılı). Assetler:
      `StockWidget-1.1.0.exe` `sha256:e20f6860…` (22.3 MB),
      `StockWidget-1.1.0-portable.zip` `sha256:38e76062…` (README 136 satıra
      indirildikten sonra içindeki README yenilenip asset tekrar yüklendi),
      `StockWidget-1.1.0-setup.exe` `sha256:f0241530…`. İndirilen tek dosya
      exe'nin `FileVersion`/`ProductVersion` = 1.1.0 ve `--version` çıktısı
      doğrulandı.
    - Release ZIP'i `docs/` içermiyordu (workflow yalnızca README/LICENSE
      kopyalıyordu). `release.yml` artık `docs/` klasörünü de kopyalıyor;
      `v1.1.0` ZIP'i README + LICENSE + `docs/` ile yeniden üretilip asset
      değiştirildi. GitHub indirme CDN'i eski dosyayı önbelleğe aldığı için
      doğrulamada URL'ye `?t=<unix>` eklenmeli.
19. **README sadeleştirme** —
    - 300 satırlık README 136 satıra indirildi: indirme ve hızlı başlangıç öne
      alındı, özellikler tek liste, veri/ayar bölümleri kısaltıldı, sorun giderme
      7 ve sınırlar 4 maddeye indirildi. Teknik ayrıntılar AGENT.md'de kalıyor.
20. **Portföy düzenleyicisi yenilendi** —
    - Eski "kart + iki etiketli alan" düzeni yerine modern bir tablo: solda
      TOPLAM DEĞER / MALİYET / K/Z özet şeridi (accent çizgili), sütun başlıkları
      (SEMBOL / ADET / ORTALAMA / DEĞER / K/Z), satır ayırıcıları.
    - Satıra odaklanınca ya da fareyle üzerine gelince satır vurgulanır; ✕ ile
      satır temizlenir. Geçersiz sayıda alan kırmızı çerçeveyle işaretlenir ve
      satırda "geçersiz" yazar; Kaydet bu durumda kaydetmez.
    - Fiyatı olmayan sembolde "veri yok" gösterilir (eskiden maliyeti fiyat
      sayıp K/Z'yi 0 gösteriyordu). Toplam K/Z yalnızca fiyatı olan satırlardan
      hesaplanır; mutlak K/Z özetin alt satırında.
    - Uzun listeler 280 px'lik kaydırılabilir alanda (fare tekerleği + ince
      kaydırma çubuğu); pencere ekranın ortasında açılır. Enter = Kaydet,
      Esc = Kapat, Ctrl+S = Kaydet.
    - Duman testi (`build/pf_check.py`, git dışı): 4 sembolle kaydetme ve
      geçersiz giriş reddi; `build/pf_theme.py`: açık tema + 10 sembolle
      kaydırma. Ekran görüntüleri `build/pf-*.png`.
21. **Ayarlar penceresi (Faz 1)** —
    - Sağ tık menüsündeki Tema / Opaklık / Yoğunluk / otostart girdileri tek
      pencerede toplandı: **Ayarlar…** → iki sütunlu gruplu kartlar (Görünüm,
      Gelişmiş / Veri, Davranış). Değişiklikler anında uygulanır ve kaydedilir;
      altta **Sıfırla** (yalnızca ayarlar; semboller/portföy/otostart korunur)
      ve **Kapat**.
    - Yeni ayarlar: "Her zaman üstte", yenileme aralığı seçenekleri (açıkken
      5/15/30, kapalıyken 15/60/120 dk), "piyasa kapalıyken yenilemeyi durdur",
      "kapatınca tepsiye gizle" ve "konumu sıfırla". Eski menü alt menüleri
      kaldırıldı; Semboller/Portföy düğmeleri pencerenin altına taşındı.
    - `config.json` şeması: `always_on_top`, `refresh_open`, `refresh_closed`,
      `pause_when_closed`, `close_to_tray`. `load_config` bilinmeyen/bozuk
      değerleri varsayılana çeker (`_cfg_bool`, 1–1440 dk sınırı).
    - `fetch_loop` aralıkları artık `cfg`'den okur; kapalıyken duraklatma
      yalnızca 60 s'de bir `market_open()` kontrolü yapar (ağ isteği yok).
      Elle **Yenile** duraklatmayı bir kez aşar (`_force_refresh`).
    - ✕ / Alt+F4 `close_window()`: `close_to_tray` açık ve tepsi ya da kısayol
      çalışıyorsa gizler, aksi halde uygulamayı kapatır (pencere kaybolmaz).
    - Tepsi menüsüne de **Ayarlar…** eklendi; pencere gizliyken de erişilebilir.
    - Opaklık Canvas kaydırıcısı (dolgulu accent çizgi + topuz), switch'ler ve
      segment düğmeleri ortak görsel dilde; seçili segment accent alt çizgiyle.
    - Duman testi (`build/settings_check.py`, git dışı): tema/opaklık/aralık/
      topmost/duraklatma/kapatma/konum/sıfırlama; `build/loop_check.py`:
      duraklatma + elle yenileme (ağsız sahte `fetch_quote`). Görseller
      `build/settings-*.png`.
22. **Kart başlığında yenile düğmesi** —
    - ✕'nin soluna ⟳ eklendi; saat/piyasa noktası sola kaydı. Tıklama
      `refresh_now()` çağırır (duraklatmayı bir kez aşar), simge 0,9 s accent
      ile vurgulanır; hover accent, normalde DIM.
    - Simge üzerinde çift tıklama sembol düzenleyicisini açmaz
      (`_on_double_click` "current" etiketini kontrol eder).
    - Glif notu: `Segoe UI` bold U+27F3'ü tofu kutusu olarak çiziyor;
      `("Segoe UI Symbol", 11)` normal kullanılmalı.
23. **Tepsi simgesi düzeltmesi** —
    - Belirti: derlenmiş (onefile) exe'de tepsi simgesi hiç oluşmuyordu;
      `sw.log`'a `PermissionError: [WinError 5]` düşüyordu.
    - Neden: `pystray` → `ChangeWindowMessageFilterEx`. Bu çağrı yalnızca
      explorer yeniden başladığında simgenin geri gelmesini sağlar; başarısız
      olması simgeyi engellemez. Malwarebytes gibi güvenlik yazılımları imzasız
      exe'lerde bu API'yi engelleyebiliyor.
    - Çözüm: `_patch_tray_message_filter()` pystray'in fonksiyonunu sarıp
      `OSError`'ı yutuyor (tek satır info log). `_setup_tray` bunu simge
      oluşturmadan önce çağırıyor.
    - Tanı: `_log_tray_state()` 1,5 s sonra `tepsi simgesi: hazır` /
      `görünür değil` yazar. Doğrulandı: `tepsi simgesi: hazır`.
    - Not: aynı güvenlik yazılımı imzasız exe'nin `%APPDATA%`'ya yazmasını da
      engelleyebilir (config/log kaydedilmez); istisna eklenmeli. Kaynak modda
      sorun yok. Windows 11 yeni simgeleri **^** gizli alanına koyabilir.
24. **Piyasa öncesi/sonrası (PÖ/PS) verisi** —
    - URL'e `includePrePost=true` eklendi (`quote_url`). Ek istek yok.
    - Seans dışı fiyat artık `fullday*` alanlarından değil, **grafiği besleyen
      son 5 dk barından** okunur (`bar_session(ts)` barın ET saatine bakar:
      04:00–09:30 `pre`, 16:00–20:05 `post`). Böylece kart/detay fiyatı
      grafiğin bittiği noktayla birebir aynı olur; `fulldayPrice` seans sonrası
      işlemleri tam yansıtmadığı için kart kapanış fiyatında takılı kalıyordu.
      Değişim `fiyat / prev_close - 1` ile hesaplanır (grafik hover'ı da aynı).
    - Seans etiketi: `_update_status` önce `market_phase()` bakar; seans
      kapalıyken verideki `ext_session` varsa onu yazar (hafta sonu/tatilde de
      PS görünür, çünkü gösterilen fiyat seans sonrası veridir).
    - Görünüm: satır fiyatı ve rozeti seans dışı değeri gösterir
      (`PÖ ▼ -0,64%` / `PS ▲ +1,2%`); saat yanındaki nokta normal seansta
      yeşil, seans dışında amber, kapalıyken soluk; noktanın solunda PÖ/PS
      etiketi. Detay panelinde büyük fiyat + rozet seans dışı, alt satırda
      "son kapanış ... (...%)". Normal seans değerleri detayda kalır.
    - Ayar: `extended_hours` (varsayılan `true`), Ayarlar → VERİ.
      Kapatınca `fetch_quote(sym, False)` çağrılır ve rozet gizlenir.
    - `pause_when_closed` artık `market_active()` kullanır: seans dışı açıkken
      yenileme durmaz.
    - Test: `market_phase`, `market_open/active`, `bar_session`,
      `fetch_quote` son bar -> ext eşlemesi, `quote_url`, `SESSION_LABEL`.
    - 1G grafik: `range=1d` piyasa öncesi saatlerde önceki seansa düşebildiği
      için URL artık açık `period1`/`period2` kullanıyor
      (`session_epoch_range`: işlem günü 04:00–20:05 ET; 04:00 öncesi önceki
      işlem günü). Grafik canlı fiyatı ayrı nokta olarak eklemez; son bar neyse
      grafik ve kart onu gösterir. Eksenin sağ etiketi "şimdi" ya da son barın
      yerel saati.
25. **README sadeleştirme + yeni ekran görüntüleri** —
    - README'den "Kullanım", "Geliştirme", "Sorun çıkarsa" ve "Sınırlar"
      bölümleri kaldırıldı; komutlar AGENT.md'deki doğrulama bölümünde kalıyor.
      Detay paneli bilgisi Özellikler'e tek madde olarak taşındı.
    - `docs/ekran-ana.png` ve `docs/ekran-detay.png` gerçek veriyle yeniden
      üretildi: PÖ/PS rozetleri, "son kapanış" satırı ve 04:00–20:05 ET grafiği
      görünüyor. Üretici: `build/docs_shots.py` (geçici, `build/` gitignore'da;
      `_init_dpi` 2.0'a çekilip arayüz 2x yakalanıyor, açık zemine kompozit).
26. **Esc ile detay panelini kapatma** —
    - İstek: hisse grafiği açıkken Esc ile geri çıkılsın.
    - `DetailPanel` iki yere `<Escape>` bağlıyor: kendi penceresi ve
      `app.root` (ana kart odaktayken de çalışsın). İkisi de `_on_escape` →
      `close()`; handler `"break"` döndürür.
    - `close()` artık `app.root.unbind("<Escape>", self._esc_id)` ile root
      bağını temizler; panel açık değilken Esc hiçbir şey yapmaz. Ayar/sembol
      pencerelerinin kendi Esc bağları ayrı toplevel'da olduğu için etkilenmez.
    - Doğrulama: `build/check_escape.py` (geçici) — panelde Esc, kart odaklı
      Esc, kapalıyken Esc ve bağ temizliği: 4/4 geçti.
27. **Kısa geçiş animasyonları** —
    - İstek: geçişlere hızlı motion'lar.
    - Yeni yardımcılar (`stock_widget.py`): `anim_enabled()` (Windows
      `SPI_GETCLIENTAREAANIMATION`; sistemde animasyon kapalıysa hepsi atlanır),
      `ease_out()` (cubic ease-out), `blend_color()`, `run_anim()` (16 ms
      kareler, `alive()` ile iptal) ve `fade()`.
    - Detay paneli: açılışta 130 ms solma + 10 px yukarı kayma; kapanışta 90 ms
      solma + yarım kayma, sonunda pencere yok edilir (`close(animate=...)`;
      panel değiştirilirken animasyonsuz).
    - Sekmeler: etkin sekme vurgusu artık ayrı `tabpill` katmanı; 1G→1H gibi
      geçişte vurgu 130 ms'de eski sekmeden yenisine kayar.
    - Kart: göster/gizle 130/90 ms solma; `_fade_gen` sayacı ile hızlı
      toggle'larda eski animasyon iptal edilir.
    - Satır vurgusu: 90 ms renk geçişi; `_hover_gen` sayacı hızlı fare
      hareketinde eski animasyonu iptal eder.
    - Ölçüm (`build/check_motion.py`, geçici): panel açılış alpha 0.32→0.97
      (~150 ms, y 247→240), kapanış alpha→0 (~125 ms'de yok), sekme vurgusu
      x 28.9→55.0 (~160 ms), kart gizle alpha→0 + withdraw (~116 ms), kart
      göster 0.32→0.97 (~150 ms). Testler: 27/27.
28. **Kart rozetinin sol tarafındaki renk artığı** —
    - Belirti: yüzdelik rozetlerinin solunda koyu kırmızı/yeşil yarım daire
      kalıntılar; rozet metni kısalınca/genişleyince belirginleşiyordu.
    - Neden: `_render_row` rozet arka planını (`_round_rect`) satır etiketi
      vermeden çiziyordu; `c.delete(it["tag"])` bu şekilleri silmediği için
      her yenilemede eski rozet tuvalde kalıyordu (metin ve fiyat siliniyordu).
    - Düzeltme: rozet arka planına `tags=(it["tag"],)` eklendi; yenilemede eski
      rozet tamamen siliniyor.
    - Doğrulama: yeni `test_row_badge_cleared_between_refreshes` (eski kodda
      15 öğe, beklenen 9; düzeltmeyle 9) ve `build/check_badge.py` (geçici):
      yeşil +7.14% → kırmızı -3.61% yenilemesinde rozet solunda eski kodda
      16 artık piksel, düzeltmeyle 0. Testler: 28/28.
29. **Durum satırı istek zamanı yerine veri zamanı** —
    - Belirti: hafta sonu/tatilde Cuma'nın PÖ/PS barı tekrar geldiğinde kart
      "son güncelleme az önce" diyordu; kullanıcı fiyatların güncellenmediğini
      sanıyordu (istek başarılı, veri 2 günlük).
    - `fetch_quote` aynı yanıttan son 5 dk barının zamanını `bar_ts` olarak
      döndürür (ek istek yok); `SNAPSHOT_NUM_FIELDS`'a eklendi.
    - `apply_data`, `_data_ts`'i `bar_ts`/`quote_ts` en büyüğünden alır.
      Durum satırı `data_age_text()` ile: 20 dk'dan eski veri "son veri …",
      PÖ/PS penceresinde bar yoksa "işlem yok · son veri …" yazar.
    - Ayarlar'daki satır **Son veri** oldu; `i18n` TR/EN kalıpları eklendi.
    - Testler: `bar_ts` eşlemesi, yaş metinleri, snapshot roundtrip; toplam 139.
30. **Gece isteği duraklatma** —
    - ABD'de 20:05–04:00 ET (ayrıca hafta sonu/tatil) Yahoo yeni 5 dk barı
      vermez; eski davranışta `refresh_closed` ile gece boyunca boş istek
      atılıyordu (15 dk aralıkla ~64 istek).
    - `us_quiet_hours()` saf; `_fetch_cycle`, `night_pause` açık ve
      `_market_active()` False iken `PAUSE_POLL` döner (60 s, ağ yok).
      BIST/kripto açıksa `is_open` True olduğu için duraklama uygulanmaz.
    - Elle **Yenile** (`_force_refresh`) bir kez aşar. Varsayılan açık;
      Ayarlar → Veri → "Gece isteğini durdur".
    - Testler: pencere sınırları, hafta sonu/tatil, ağ çağrılmaması,
      elle yenileme.
31. **PÖ/PS yüzdesinin tabanı** —
    - Gerçek fiyatla karşılaştırma (stockanalysis.com): ONDS PÖ fiyatı 4,05
      doğruydu, ama kart **-4,26%** gösterirken site **+7,71%** gösteriyordu.
    - Neden: `ext_pct` bir önceki günün kapanışına (`prev` = 4,23) göre
      hesaplanıyordu. Seans dışı değişimin tabanı **son normal seans kapanışı**
      (`price` = 3,76) olmalı; siteler de böyle gösterir.
    - `fetch_quote` artık `ext_price / price - 1` kullanır; kart, detay,
      alarm ve hover aynı değeri görür. Ek istek yok.
    - Test: `test_extended_change_uses_last_regular_close` (4,05/3,76 → +7,71%).
32. **Portföy ve satır K/Z seans dışı fiyatı izlesin** —
    - Belirti: kart PÖ +8,24% gösterirken portföy rozeti Cuma'nın -11,86%
      değerinde kalıyordu; satır K/Z'si de son normal kapanışa göreydi.
    - `display_price()` (değer/K-Z için `ext_price`) ve `reference_close()`
      (günlük taban: seans dışında `price`, normal seansta `prev_close`)
      eklendi.
    - `_portfolio_stats`, `_portfolio_by_currency`, satır K/Z, portföy
      düzenleyici ve CSV aynı fiyatı kullanır; ek istek yok.
    - 1G grafik referans çizgisi/hover tabanı ve detaydaki "Önceki kapanış"
      satırı da aynı kuralı kullanır (`reference_close`,
      `previous_close_value`); PÖ'de 4,23 yerine 3,76 görünür.
    - Doğrulama: ONDS 4,07 → PÖ +8,24%, K/Z -53,2%; BRUN 3,90 → +9,55%,
      K/Z -85,6%; portföy rozeti +8,51% (ağırlıklı). Testler 154.
33. **Baştan sona denetim (2026-11-23)** —
    - Uçuştaki fetch, listeden çıkarılan sembolü geri getirince `apply_data`
      `KeyError` üretiyordu; `poll_queue` yakaladığı için o tur sessizce
      kayboluyordu. `_render_row` artık yalnızca `self.last`'ta kalan
      semboller için çağrılır; `ApplyDataRaceTest` eklendi.
    - EN arayüzde 6 metin Türkçe kalıyordu (boş takip listesi, geçerli ticker,
      sessiz saat uyarıları, portföy geçmişi başlığı, "karışık"). `_DIRECT`
      tamamlandı; `I18nTest` genişletildi.
    - Güncelleme denetimi GitHub API 403 (anonim kota) alınca "ulaşılamadı"
      diyordu. Artık önce `releases/latest` HTML yönlendirmesi okunur (API
      kotası yok, günde tek istek); API yalnızca yedek. Canlı doğrulandı: 1.1.0.
    - Denetim kapsamı: 158 test, ruff/mypy, UI matrisi, frozen smoke A/B/C,
      Inno derlemesi, manifest/bump/screenshot araçları, canlı 1H/1A/1Y,
      takvim profilleri, menü bağlantıları ve stockanalysis fiyat kontrolü.
34. **Kullanıcıya dönük kalan yolların denetimi (2026-11-23)** —
    - Tepsi menüsü: gerçek `pystray.Menu`/`MenuItem`, sahte Icon ile 17/17 —
      Ayarlar, Semboller, Portföy, Gruplar, Alarmlar, Odak, önceki/sonraki,
      Yenile, sustur/kaldır, otostart, göster/gizle, çıkış. Gerçek simge
      oluşumu ayrıca `sw.log` "tepsi simgesi: hazır" ile doğrulandı.
    - `--toggle` sinyali: kaynak kopya + `SW_INSTANCE_SUFFIX=togglesig`;
      ikinci kopya `--toggle` pencereyi gizledi, tekrar gösterdi; `--quit`
      birinci kopyayı temiz kapattı (6/6).
    - `set_startup`: sandbox HKCU anahtarında aç/kapat; değer
      `app_launch_command()` ile eşleşti, `startup_enabled()` doğru döndü,
      gerçek `Run\StockWidget` değeri değişmedi.
    - Sessiz kurulum/yükseltme/kaldırma (ayrı AppId/dizin sandbox): 1.0.9
      kurulumu → 1.1.0 yükseltmesi → kaldırma; hepsi exit 0, tek kaldırıcı,
      `DisplayVersion` 1.0.9→1.1.0, Run/kısayollar oluştu ve silindi.
      Gerçek kurulumun exe hash'i, masaüstü/Başlat kısayolları ve Run değeri
      değişmedi.
    - Bulgu/düzeltme: kaldırma boş `{app}` klasörünü bırakıyordu.
      `[UninstallDelete] Type: filesandordirs; Name: "{app}"` eklendi;
      sandbox testinde klasör tamamen silindi. Veriler `%APPDATA%`'da
      olduğu için ayarlar korunur.
35. **Ayarları sıfırlama onayı** —
    - Sıfırla, `SETTINGS_DEFAULTS` içindeki `alarms` ve `symbol_groups`
      anahtarlarını da sildiği için yanlışlıkla veri kaybı riski taşıyordu.
    - `_confirm_reset_settings()` eklendi: "alarmlar ve sembol grupları da
      silinir; semboller, portföy ve otomatik başlatma korunur" mesajıyla
      onay ister; Hayır'da hiçbir şey yapılmaz.
    - `reset_settings()` programatik/test yolu değişmedi. Metinler TR/EN;
      `ResetConfirmTest` iptal ve onay yollarını doğrular.
36. **Sembol ekleme düzeltmesi (2026-11-23)** —
    - Kullanıcı "küçük yazınca anlamıyor / hiç bulamıyor" dedi. Ölçüm:
      küçük harf zaten `clean_symbol()` ile büyütülüyordu; asıl kırılanlar
      `NASDAQ:AAPL` / `BIST:ASELS` (reddediliyordu), BIST sembolleri
      (`ASELS`, `BIM` → Yahoo 404) ve sınıf hisseleri (`BRK.B` → Yahoo
      `BRK-B` ister) idi.
    - `clean_symbol()`: borsa öneki (`NASDAQ:`, `NYSE:`, `BIST:` → `.IS`),
      sınıf hissesi noktası (`BRK.B` → `BRK-B`), boşluk temizliği.
      `symbol_candidates()` + `resolve_symbol()`: yalnızca ekleme sırasında,
      ilk biçim 404 ise `.IS` yedeği; başarıda ikinci istek yok. Hata türleri
      `format` / `notfound` / `network` olarak ayrıldı.
    - Ekleme akışı artık `root.after`'ı worker thread'den çağırmıyor
      ("main thread is not in main loop" RuntimeError'ı ekleme penceresini
      "doğrulanıyor…"da bırakabiliyordu); sonuç `queue.Queue` + `dlg.after`
      ile ana thread'de toplanıyor, 90 sn zaman aşımında düğme geri açılıyor.
    - Canlı doğrulama: `aapl`→AAPL, `asels`→ASELS.IS (2 istek), `BIST:asels`
      →ASELS.IS, `brk.b`→BRK-B, `NASDAQ:AAPL`→AAPL, `ZZZZZZ`→anlaşılır hata.
      Testler 167; `SymbolResolveTest` + genişletilmiş `HelperValidationTest`.

## Doğrulama (kod değişince çalıştır)
```bat
cd "C:\Users\<kullanıcı>\Projects\stock-widget"
python -m py_compile stock_widget.py
python -m unittest discover -s tests -t .
python tools\ui_matrix.py                  :: tema x yoğunluk x DPI (ağsız, traysiz)
set SW_SMOKE=1 && python stock_widget.py   :: 12 sn sonra kendini kapatır (duman testi)
python stock_widget.py --version
python stock_widget.py --toggle            :: çalışan kopyayı göster/gizle
python stock_widget.py --quit              :: temiz çıkış

:: paketleme (yerel)
python -m PyInstaller --noconfirm --clean --distpath dist-onefile packaging/StockWidget-onefile.spec
dist-onefile\StockWidget.exe --version
dist-onefile\StockWidget.exe --paths

:: donmus duman (tek dosya; %TEMP% altina acilir, ayarlari kirletmez)
python -m PyInstaller --noconfirm --clean --distpath build\test-snap --workpath build\work-snap packaging/StockWidget-onefile.spec
python tools\smoke_frozen.py   :: A: SW_SMOKE+snapshot+_MEI temizligi, B: --quit, C: ikinci kopya

python -m PyInstaller --noconfirm --clean packaging/StockWidget.spec
dist\StockWidget\StockWidget.exe --version
dist\StockWidget\StockWidget.exe --paths

:: kurulum paketi (Inno Setup 6 kuruluysa)
& "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" packaging/installer.iss
```

Onefile exe `%TEMP%`'e açıldığı için kısıtlı makinelerde test ederken
`$env:TEMP` / `$env:TMP` yazılabilir bir klasöre verilmeli. "ikinci kopya"
logu görülürse önce eski `pythonw.exe` / `StockWidget.exe` süreçlerini kapat.

`SW_DATA_DIR` ile ayar/log dizinini geçici bir klasöre alıp gerçek `%APPDATA%`
verisini kirletmeden test et:

```powershell
$env:SW_DATA_DIR = "$env:TEMP\sw_test"
python stock_widget.py
```

## Dayanıklılık turu (1.1.1 hazırlığı)

Kod denetiminde çıkan hatalar giderildi; her madde testle doğrulandı (77 test).

1. **Config artık çökemez.** `load_config` kök nesnenin `dict` olmasını, `theme`
   tipini, `x`/`y`/`opacity`/`refresh_*` sayısallığını, sembolleri (`clean_symbols`:
   büyük harf, tekrarsız, ≤20, regex) ve pozisyonları (`clean_positions`: sonlu
   `qty > 0`, `avg ≥ 0`) doğrular. Önceden `{"theme": []}` veya `[]` kökü
   `TypeError`/`AttributeError` ile açılışı tamamen engelliyordu.
2. **Atomik yazma + yedek.** `save_config` geçici dosya + `os.replace` kullanır,
   önceki iyi dosyayı `config.json.bak`'a kopyalar. `_read_config_file` bozuk
   dosyada `.bak`'a düşer ve o tur `.bak`'ı ezmez (`_CONFIG_FROM_BACKUP`).
3. **Takvim.** `market_holidays` artık **4 Temmuz**'u içerir; `is_market_holiday`
   yılbaşının 31 Aralık'a taştığı durumu komşu yılla yakalar; `early_closes`
   (şükran sonrası, 24 Aralık, 3 Temmuz) 13:00 ET'de seansı kapatır.
4. **Veri döngüsü ölemez.** `fetch_loop` → `_fetch_cycle` + try/except; 429'da
   `Retry-After` okunur ve kalan semboller atlanır (`_fetch_symbols`). Başarısız
   sembol diğerlerini durdurmaz.
5. **Veri tutarlılığı.** `fetch_quote`/`fetch_series` alanları `_to_float` ile
   normalize eder (string/None/sonsuz güvenli); `include_prepost=False` iken PÖ/PS
   barları grafiğe karışmaz; sparkline rengi PÖ/PS rozetinin rengini izler
   (önceden normal seans renginde kalıyordu).
6. **Portföy.** `_has_portfolio` string `qty` ile çökmez; farklı para birimleri
   toplanmaz, satırda "farklı para birimi" uyarısı çıkar.
7. **Pencere/DPI.** `virtual_screen()` + `clamp_to_screen()` tüm monitörleri
   kapsar; monitör sökülünce kart erişilemez yerde kalmaz. Gizlerken Ayarlar,
   Portföy ve Semboller pencereleri de kapanır.
8. **Detay paneli.** `series_ts` ile TTL sonrası sekme yeniden açıldığında seri
   tazelenir (README'nin vaadi artık doğru). `_SERIES_CACHE` 32 kayıtla sınırlı.
9. **Sembol ekleme.** `clean_symbol` + 20 sembol sınırı; ağ isteğinden önce
   biçim doğrulanır.
10. **Paketleme/CI.** Kurulum kısayolları `--toggle` geçirir (kapalıyken kısayol
    uygulamayı açar); `requirements.txt` sabitlendi; CI matrisi 3.11/3.12/3.13,
    `ruff`, `coverage` (≥40), `mypy`, `SW_SMOKE` GUI testi ve Inno Setup
derlemesi içerir;
    release `SHA256SUMS.txt` üretir.
11. **Temizlik.** Kullanılmayan `traceback` importu ve ölü `last_ok` kaldırıldı;
    `ruff check` temiz.
12. **Açılışta boş kart yok.** Başarılı her turdan sonra son fiyatlar
    `snapshot.json`'a atomik yazılır; `StockWidget.__init__` bunu `build_ui`'den
    önce okur. Dosya bozuk/elle değiştirilmişse sayısal alanlar ve grafik
    listeleri `load_snapshot` içinde yeniden doğrulanır (geçersiz mumlar atılır,
    `ext_session` yalnızca `pre`/`post`), yani bozuk snapshot da çökme nedeni
    olamaz. Sembol listesinden çıkarılanlar dosyaya yazılmaz.
13. **Güncelleme bildirimi.** Menüye "Güncelleme denetle…" eklendi; sessiz
    denetim açılıştan 6 s sonra yapılır ve `update.json` ile **günde en fazla 1**
    GitHub isteğine iner. Yeni sürüm varsa menü satırı "Yeni sürüm: x.y.z"
    olur; tepsi varsa sürüm başına yalnızca bir kez bildirim gösterilir.
    Elle denetim önbelleği atlar, sonucu (güncel / ulaşılamadı / indirilsin mi)
    iletişim kutusuyla söyler. Uygulama kendi kendine indirme yapmaz.
14. **onefile artıkları.** Donmuş modda açılışta `%TEMP%` altındaki 7 günden
    eski `_MEI…` klasörleri silinir; çalışan dizin (`sys._MEIPASS`) ve yeni
    klasörler korunur. Mutex alındıktan sonra çalıştığı için ikinci kopyayla
    yarışmaz.

Yeni testler: `ConfigRobustnessTest` (fuzz, BOM, kesik dosya, yedek kurtarma,
atomik yazma, yazma hatası), `HolidayCalendarTest` (2000–2100 özellik testi),
`QuoteParsingTest` (boş/bozuk yanıt, string fiyat, PÖ/PS filtresi, `Retry-After`),
`FetchLoopTest` (429, kısmi hata), `RowRenderTest` (spark rengi), `VersionSyncTest`,
`DetailSeriesTest`, `SnapshotTest` (roundtrip, bozuk dosya, alan temizleme),
`MeiCleanupTest` (yaş/çalışan dizin ayrımı), `UpdateCheckTest`/`UpdateCacheTest`
(sürüm karşılaştırma, önbellek TTL, sessiz bildirim).

Donmuş doğrulama (2026-11-20, `tools/smoke_frozen.py`): onefile `--version` →
`StockWidget 1.1.0`; **A)** `SW_SMOKE` exit 0 (~16 sn), `snapshot.json` yazıldı,
sahte eski `_MEI` klasörü silindi; **B)** `--quit` çalışan kopyayı ~3 sn'de
temiz kapattı; **C)** argümansız ikinci kopya sessizce çıktı, birinci yaşamaya
devam etti, sonra `--quit` ile kapandı. Not: `cmd /c` GUI uygulamayı beklemez;
`--quit` doğrulaması için `Start-Process`/Python `subprocess` ile bekle.

## Ücretsiz iyileştirme turu (main'e birleşti)

Geri dönüş noktası: `checkpoint/pre-free-pack-2026-11-20` (b91eb95).
Yeni özellikler `feature/free-pack` üzerinde geliştirildi ve 2026-11-20'de
`main`e fast-forward birleştirildi; dal silindi. Geri dönüş etiketi duruyor.

> Ayrıntılı, ajanlar için sözleşme düzeyi harita: **`docs/agent/AGENT-FEATURES.md`**
> (config şeması, fonksiyon girdi/çıktıları, `apply_data` sırası, render
> anahtarı, menü/kısayol kuralları, test kancaları, CI/release, geri alma).

1. **Alarmlar.** `cfg["alarms"]`: sembol başına `above`, `below`, `pct`,
   `extended`. `clean_alarms` doğrular; `evaluate_alarm` eşik geçişinde bir kez
   olay üretir ve koşul bozulunca sıfırlanır. Bildirim: tepsi (tek özet) + kart
   altında 60 s uyarı + satırda ◆. Sağ tık → "Alarm kur…" ilgili sembole odaklar.
2. **Veri tazeliği.** `snapshot.json`'dan gelen satırlar `stale` iken soluk ve
   altbilgide "önbellek · x önce"; canlı yanıtta düzelir. `quote_ts` ile detayda
   verinin gerçek saati; `market_state` ile PÖ/PS/ açık/kapalı etiketi.
3. **Sıralama ve kısayollar.** `sort_mode`: manual/change/symbol/value; elle
   sıra cfg'de korunur, görünüm `_view_symbols` ile türetilir. Satır sağ tık:
   yukarı/aşağı taşı, sembol/fiyat kopyala, Yahoo'da aç. F5/↑/↓/Enter/Esc.
4. **Performans.** Değişmeyen satır çizilmez (`_render_keys`), sparkline
   `PhotoImage` önbelleği (`_spark_cache`, 64 kayıt), aynı snapshot tekrar
   yazılmaz, `requests.Session` + kısa kilit. 429'a jitter; Retry-After artık
   HTTP tarihini de çözer. İstek sayısı değişmedi.
5. **Portföy.** Hedef fiyat + not (config, sağ tık ve düzenleyici), para birimi
   başına ayrı toplamlar (kart ve düzenleyici), kartta maliyet seçeneği,
   `portfolio_csv_rows` + UTF-8 BOM'lu `;` ayraçlı CSV dışa aktarma.
6. **Borsa farkındalığı.** Aynı Yahoo yanıtından `exchangeName`,
   `marketState`, `exchangeTimezoneName`, `regularMarketTime` okunur. ABD dışı
   bilinen borsalarda PÖ/PS rozeti bastırılır; seans/tatil takvimi hâlâ NYSE.
7. **Test/altyapı.** 78 → 96 test; `tools/ui_matrix.py` 5 ölçek × 4 tema × 2
   yoğunluk + alarm/portföy pencerelerini doğrular. CI: pip-audit (ayrı job),
   coverage eşiği 30, Inno sessiz kurulum/kaldırma testi, log artifact'i.
   Release: CycloneDX `sbom.json`. Dependabot yapılandırıldı ancak açık PR
   limiti 0 (depo tek dallı kalsın diye kapalı); güvenlik `pip-audit` ile
   izleniyor. Winget/Scoop şablonları ve `tools/render_manifests.py`.
8. **Bilinçli sınırlar.** Otomatik güncelleme indirme yok (yalnızca bildirim);
   ABD dışı borsa tatil takvimi yok; UPX/Nuitka denenmedi (AV/risk); SignPath
   başvurusu dış hesap gerektirir.

## Dal düzeni ve README (2026-11-20)

- `feature/free-pack` `main`e **fast-forward** birleştirildi, ardından silindi;
  tek dal `main`. Geri dönüş için `checkpoint/pre-free-pack-2026-11-20`
  etiketi duruyor. Uzak dalı silmek kullanıcıya bırakıldı.
- README, galeri denemesinden önceki yapısına döndürüldü (iki görsel + İndir +
  Hızlı başlangıç + Özellikler + Veri kaynağı + Ayarlar). İçerik güncel:
  alarm, sıralama, klavye, portföy (hedef/not/CSV), hacim + fiyat ekseni,
  `alarms` / `sort_mode` / `portfolio_show_cost` anahtarları.
- `tools/screenshot.py` sadeleştirildi: yalnızca `ekran-ana.png` ve
  `ekran-detay.png` üretir; veri sabit (ağ yok), widget topmost/backdrop altta,
  boş yakalamada mevcut dosya korunur; kısayol thread'i "registered" ile
  değiştirilir. Diğer üç görsel kaldırıldı.
- Not: push yalnızca kullanıcı isterse yapılır.
- **CI onarımı (2026-11-20):** `audit` işi `requests==2.32.5` + `pillow==11.3.0`
  pinlerinde 78 zafiyet buluyordu → `requests==2.34.2`, `pillow==13.0.0`
  (pystray sabit). Uygulama ve testler yeni sürümlerle doğrulandı (PIL çizimleri
  dahil). `build` işi, sessiz kurulum duman testinde sabit `StockWidget 0.0.0`
  beklediği için düşüyordu; artık derlenen `dist\StockWidget\StockWidget.exe`
  sürümüyle karşılaştırılıyor.
- Bağımlılık PR'ları kapalı: Dependabot `open-pull-requests-limit: 0`.

## Tüm paketler turu (main'e birleşti)

Geri dönüş etiketi: `checkpoint/pre-all-packages-2026-11-22` (f99e523).
`feature/all-packages` fast-forward ile `main`e alındı ve yerel/uzak dal
silindi; tek dal `main`.

1. **Portföy geçmişi.** `portfolio-history.json` günlük/para birimi başına
   toplam tutar; `record_history` aynı gün aynı toplamda yazmaz. Portföy
   penceresinde son 30 kayıt mini grafiği (`history_series` / `history_change`).
2. **Disk grafik önbelleği.** `series-cache.json`; `load_series_disk` TTL içinde
   belleğe alır, `save_series_disk` atomik yazar. Yeniden açılışta 1H/1A/1Y
   isteği gerekmeyebilir.
3. **Temettü/bölünme.** Aynı chart isteğinde `events=div,splits`; quote ve
   series verisine `dividends` / `splits` eklenir. Grafikte T/B işaretleri,
   detay alt satırında özet. Yeni istek yok.
4. **Alarm genişletmesi.** `profit` / `loss` (pozisyon maliyetine göre), sessiz
   saat (`quiet_*`), 1 saat susturma, `alarm-history.json`, hedef fiyata tek
   tıkla alarm. Detay grafiğinde sağ tıkla üst/alt alarm seviyesi; hedef,
   maliyet ve alarm çizgileri.
5. **Kart/UX.** Satırda pozisyon K/Z; odak modu ve Ctrl+←/→; sembol grupları
   (`symbol_groups`, `group_filter`) + menü filtresi; `Gruplar…` editörü.
6. **Piyasa profilleri.** `market_calendar.py`: ABD/BIST/kripto profilleri,
   BIST 10:00–18:00 TR (arife 13:00), 2024–2030 dini bayram tablosu, ₺ biçimi,
   çoklu piyasa özeti ve fareyle ayrıntı. `_market_active` duraklatmayı profillere
   göre yönetir; PÖ/PS yalnızca ABD'de.
7. **Tanılama.** `diagnostics_info` + `redact_config` (portföy/maliyet/alarm
   eşikleri gizlenir); Ayarlar → Tanılama paketi ZIP.
8. **TR/EN arayüz.** `i18n.py` Tk Label/Button/Menu/Canvas metinlerini çevirir;
   Ayarlar → Dil. Varsayılan `tr`. Log/CLI çevrilmez.
9. **Kalite/dağıtım.** CI: mypy (kademeli), coverage ≥40 (ölçülen ~56;
   unittest + UI matrisi),
   Inno 0.0.1→0.0.2 yükseltme testi, Sigstore `attest-build-provenance`
   (3 artifact). Testler 133; UI matrisi coverage'a dahil (~56%);
   5 ölçek × 4 tema × 2 yoğunluk + alarm/grup/portföy/ayarlar pencereleri.
10. **Regresyon düzeltmesi.** Row menüye Ayarlar/Semboller/Portföy/Gruplar
    eklendi; `is_us_exchange` artık `NGM`/`NCM`/Nasdaq katmanlarını ve
    `America/New_York` saat dilimini tanır. ONDS (NCM) ve BRUN (NGM) yeniden
    PÖ/PS alır; `exchange_profile` ile tek kaynak kural kullanılır.

Bilinçli sınırlar: BIST dini bayram tablosu yıllık güncellenir; generic borsa
profili ilk veriden sonra `marketState` kullanır; İngilizce arayüz kullanıcı
metinlerini kapsar (log/CLI hariç); SignPath/WinGet/Scoop yayını dış onay ister.
