# AGENTS.md — Borsa Widget (StockWidget)

Windows masaüstü hisse widget'ı. Tek dosya Python/Tkinter uygulaması; sembol listesi
`config.json`'dan gelir (varsayılan AAPL, MSFT, NVDA, GOOGL, AMZN), Yahoo Finance'in
ücretsiz chart endpoint'ini kullanır. UI metinleri Türkçe, UTF-8.

## Dosyalar
- `stock_widget.py` — uygulamanın tamamı (UI, veri çevrimi, tray, kısayol, portföy, otomatik başlatma)
- `README.md` — kullanıcı dokümanı (indirme, kurulum, kullanım, derleme, sorun giderme)
- `AGENT.md` — bu dosya: mimari kurallar + değişiklik günlüğü
- `test_stock_widget.py` — stdlib `unittest` birim testleri (ağa çıkmaz)
- `LICENSE` — MIT (2026 Arif Kemal)
- `StockWidget-onefile.spec` — PyInstaller **onefile** derleme tanımı (ana indirme)
- `StockWidget.spec` — PyInstaller onedir derleme tanımı (ZIP yedeği)
- `installer.iss` — Inno Setup 6 kullanıcı bazlı kurulum betiği (isteğe bağlı)
- `version_info.txt` — exe sürüm bilgisi (PyInstaller)
- `tools/bump_version.py` — sürümü kaynak + version_info + installer.iss'e yazar
- `tools/screenshot.py` — README görsellerini gerçek uygulamadan üretir
- `.github/workflows/ci.yml` / `release.yml` — test+derleme / etiketli sürüm
- `toggle.vbs` — kaynak modunda masaüstü kısayolu (kurulu sürümde `StockWidget.exe --toggle`)
- `install_startup.ps1` / `uninstall_startup.ps1` — eski kaynak modu otostart betikleri
- `requirements.txt` — requests, pystray, pillow (pystray/pillow opsiyonel)
- `docs/ekran-ana.png`, `docs/ekran-detay.png` — README ekran görüntüleri
- `docs/imzalama.md` — kod imzalama (SmartScreen / SignPath) durumu ve adımları
- `config.json` / `sw.log` — kaynak modunda çalışma zamanı dosyaları, `.gitignore`'da
- `%APPDATA%\StockWidget\` — kurulu/portatif sürümde ayar + log (SW_DATA_DIR ile değiştirilebilir)
- `build/`, `dist/`, `dist-onefile/`, `Output/` — derleme çıktıları, `.gitignore`'da

## Mimari kuralları (bozmadan değişiklik yap)
- **Tk tek thread.** Ağ işi `fetch_loop` thread'inde döner; sonuçlar `self.queue`'ya yazılır,
  `poll_queue` (root.after ~150–200 ms) ana thread'de tüketir. **Thread'den Tk widget'ına asla dokunma.**
- **Tray (pystray) callback'leri kendi thread'inde çalışır.** Tk'ye dokunanlar (`toggle_visibility`,
  `open_symbol_editor`, `exit_app`, `_tray_toggle_startup`) `root.after(0, ...)` ile ana thread'e taşınır
  (`_create_tray_icon`); sadece `refresh_now` (`threading.Event.set`) thread-safe olup doğrudan çağrılabilir.
- Her dış olay kuyruk üzerinden gelir: `self.queue` (fiyat verisi + offline bayrağı),
  `self.hotkey_queue` (kısayol olayları: `registered` / `unavailable` / `toggle`).
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
  doğrudan çağırma — açık detay paneli ekranda asılı kalır.
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

## Veri ve API disiplini (ücretsiz endpoint, 429 riski)
- Sembol başına döngüde **1 istek**; semboller arasında 0.4 s bekleme.
- Aralıklar: piyasa açık 15 dk, kapalı 60 dk; hata sonrası 90 s; HTTP 429 → 5 dk bekleme.
- Endpoint: `query1.finance.yahoo.com/v8/finance/chart/{sembol}?range=1d&interval=5m`.
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
   Kayıt başarısızsa sağ tık menüsündeki ipucu satırı "kaydedilemedi" olur (`_set_hotkey_hint`).
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
7. **toggle.vbs** — `taskkill /F` davranışı açıklandı (WM_CLOSE gizler, sonlandırmaz).
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
    `test_stock_widget.py` stdlib `unittest` (tatiller, fmt, palet, config, render,
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
    - Paketleme: `StockWidget.spec` (PyInstaller onedir, `--noconsole`, ikon, sürüm),
      `installer.iss` (Inno Setup 6, kullanıcı bazlı `%LOCALAPPDATA%\Programs\StockWidget`,
      kısayollar, isteğe bağlı otostart, yükseltmede `--quit`, kaldırmada ayarları korur),
      `version_info.txt`, `tools/bump_version.py`.
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
    - `installer.iss`: `PrepareToInstall` artık `{app}` ve HKCU yazılabilirliğini
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
    - `StockWidget-onefile.spec` eklendi (`EXE(...)` içine `a.binaries` /
      `a.datas`, `COLLECT` yok, `runtime_tmpdir=None`, `console=False`). Yerel
      derleme ~26 MB; `--version`, `--paths`, `--toggle`, `--quit` uçtan uca
      denendi. Onefile her açılışta `%TEMP%`'e açıldığı için ilk pencere birkaç
      saniye gecikir; README bunu açıkça yazıyor ve ZIP'i yedek gösteriyor.
    - `ci.yml`: onedir + onefile derlemesi ve iki exe için `--version` duman
      testi. `release.yml`: onefile derleme, `StockWidget-$V.exe` üretimi +
      sürüm doğrulaması, 3 asset yükleme.
    - `tools/bump_version.py` artık `installer.iss` içindeki `MyAppVersion`
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
      `StockWidget-1.1.0-portable.zip` `sha256:d631e71c…`,
      `StockWidget-1.1.0-setup.exe` `sha256:f0241530…`. İndirilen tek dosya
      exe'nin `FileVersion`/`ProductVersion` = 1.1.0 ve `--version` çıktısı
      doğrulandı.
    - Release ZIP'i `docs/` içermiyordu (workflow yalnızca README/LICENSE
      kopyalıyordu). `release.yml` artık `docs/` klasörünü de kopyalıyor;
      `v1.1.0` ZIP'i README + LICENSE + `docs/` ile yeniden üretilip asset
      değiştirildi. GitHub indirme CDN'i eski dosyayı önbelleğe aldığı için
      doğrulamada URL'ye `?t=<unix>` eklenmeli.

## Doğrulama (kod değişince çalıştır)
```bat
cd "C:\Users\<kullanıcı>\Desktop\StockWidget"
python -m py_compile stock_widget.py
python -m unittest test_stock_widget.py
set SW_SMOKE=1 && python stock_widget.py   :: 12 sn sonra kendini kapatır (duman testi)
python stock_widget.py --version
python stock_widget.py --toggle            :: çalışan kopyayı göster/gizle
python stock_widget.py --quit              :: temiz çıkış

:: paketleme (yerel)
python -m PyInstaller --noconfirm --clean --distpath dist-onefile StockWidget-onefile.spec
dist-onefile\StockWidget.exe --version
dist-onefile\StockWidget.exe --paths

python -m PyInstaller --noconfirm --clean StockWidget.spec
dist\StockWidget\StockWidget.exe --version
dist\StockWidget\StockWidget.exe --paths

:: kurulum paketi (Inno Setup 6 kuruluysa)
& "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
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