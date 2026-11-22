# StockWidget — Ajan Kalıcı Hafızası

Bu dosya oturumlar arasında unutulmaması gerekenleri tutar. Proje sözleşmesi
`docs/agent/AGENT-FEATURES.md`, genel mimari `AGENT.md`, kullanıcı dokümanı `README.md`'dir.
Çelişki olursa sıra: kullanıcının son talebi → bu dosya → AGENT-FEATURES → AGENT.

## Kullanıcı tercihleri / değişmezler

- Arayüz **Türkçe**; İngilizce opsiyonel, varsayılan `tr`.
- Windows 10/11, Python + Tkinter, **tek küçük widget**; ağır finans uygulamasına
  dönüşmemeli.
- Yalnızca **ücretsiz** araçlar/API'ler. Ücretli API, kod imzalama sertifikası,
  zorunlu abonelik yok.
- Yahoo istek disiplini: **sembol başına 1 chart isteği**; yeni özellik ek istek
  üretmemeli. Aynı yanıtın alanları (`events=div,splits`, `marketState` vb.)
  kullanılmalı.
- PÖ/PS fiyatları kart, detay ve grafikte **tutarlı** olmalı. Rozet yalnızca
  ABD borsalarında anlamlı; BIST/kripto için gösterilmez.
- README'de **"Kullanım", "Geliştirme", "Sorun çıkarsa", "Sınırlar" bölümleri
  olmayacak**. Görseller küçük: kart 360 px, detay 720 px, ayarlar 430 px.
  Özellikler bölümü kısa (8 madde civarı) tutulacak.
- Her değişiklikte yeni sürüm/tag/release **yok**; commit birikir. Sürüm şu an
  **1.1.0**. Release yalnızca kullanıcı isterse/etiketle.
- Büyük turdan önce **checkpoint tag**; kullanıcı beğenmezse geri alınabilir
  olmalı. Tek dal düzeni korunur; gerekiyorsa geçici dal açılıp iş sonunda
  silinir. `main` kullanıcı onayı olmadan değiştirilmez.
- Kısayollar **sürümden bağımsız kurulu yolu** göstermeli:
  `%LOCALAPPDATA%\Programs\StockWidget\StockWidget.exe` (`--toggle`).
  Sürümlü exe yoluna veya `dist/` içine bağlanmamalı.
- Kullanıcının gerçek ayarları `%APPDATA%\StockWidget\config.json`; testler
  `SW_DATA_DIR` ile geçici dizin kullanmalı, gerçek config ezilmemeli.
- Kullanıcı çalışan kurulu widget'ı gereksiz yere kapatılmamalı; kapatmak
  gerekirse önce `--quit`, sonra gerekirse yeniden başlat.

## Mevcut durum (2026-11-22)

- Tek dal: **main**; kod birleşmesi `0c983b6` (tüm paketler + düzeltmeler
  fast-forward), üzerine doküman/düzen commit'leri gelebilir. Tüm eski
  feature dalları yerel ve uzakta silindi.
- `main` önceki hali: `f99e523` (checkpoint).
- Checkpoint'ler:
  - `checkpoint/pre-reorg-2026-11-22` → 0c07b84 (klasör düzeni öncesi)
  - `checkpoint/pre-all-packages-2026-11-22` → f99e523
  - `checkpoint/pre-free-pack-2026-11-20` → b91eb95
- Son doğrulanan CI:
  - Run **#50** (`7f6f2f7`): success — test 3.11/3.12/3.13, audit, build,
    GUI/UI matrisi, Inno yükseltme testi.
  - Run #49 (`43151c3`): success.
- CI `feature/**` push'larında da çalışır.
- Kurulu exe güncellendi: `%LOCALAPPDATA%\Programs\StockWidget\StockWidget.exe`
  - SHA256 `93BBB848AE26EA1C03B7336AE50D9966597522DE41C4514E3F878466BD7A105E`
  - 27.479.275 bayt, 2026-11-22 17:03
  - Eski sürüm yedeği: `build\installed-backup-20261122-170417.exe`
- Masaüstü `StockWidget.lnk` ve Başlat menüsü `Borsa Widget.lnk` aynı kurulu
  exe'yi `--toggle` ile açar. HKCU Run girdisi aynı exe'yi gösterir.
- Kullanıcının sembolleri: **ONDS, BRUN**; tema **grafit**, opaklık **0.95**,
  konum x=1474 y=441. Bunlar gerçek config'de; testlerde kullanılmamalı.

## Klasör düzeni (2026-11-22'den itibaren)

- Kök: `stock_widget.py`, `market_calendar.py`, `i18n.py`, `README.md`,
  `LICENSE`, `AGENT.md`, `mypy.ini`, `requirements*.txt`.
- `tests/` — unittest dosyası (`tests/test_stock_widget.py`).
- `assets/stock.ico` — kaynak ve PyInstaller ikonu.
- `packaging/` — `.spec`, `installer.iss`, `version_info.txt`, Winget/Scoop.
- `docs/agent/` — ajan haritası ve bu hafıza dosyası.
- `tools/legacy/` — eski kaynak modu kısayol/otostart betikleri.
- Komutlar kök dizinden çalışır; taşıma sonrası `python -m unittest discover
  -s tests -t .`, PyInstaller `packaging/...spec`, Inno `packaging\installer.iss`.

## Doğrulama komutları

```powershell
cd "C:\Users\Arif Kemal\Desktop\StockWidget"
python -m py_compile stock_widget.py market_calendar.py i18n.py
python -m unittest discover -s tests -t .          # 125 test
python -m ruff check . --exclude .git,dist,dist-onefile,build,Output
python -m mypy                                    # market_calendar.py
python tools\ui_matrix.py                         # 5 ölçek × 4 tema × 2 yoğunluk
python tools\smoke_frozen.py                      # A/B/C donmuş exe
```

Coverage (unit + UI matrisi): **%56**, CI eşiği **%40**:

```powershell
python -m coverage erase
python -m coverage run -m unittest discover -s tests -t .
python -m coverage run --append tools\ui_matrix.py
python -m coverage report --include="stock_widget.py"
```

## Bilinen tuzaklar / regresyonlar

1. **ABD borsa kodları:** Yahoo Nasdaq katmanlarını `NMS/NGM/NCM`, NYSE'yi
   `NYQ/NYE` ile döndürür. Yalnızca `NMS` bilmek ONDS (NCM) ve BRUN (NGM)
   PÖ/PS'sini bastırır. Tek kaynak: `market_calendar.exchange_profile`;
   `America/New_York` ve Nasdaq/NYSE/AMEX/Arca adları yedek.
2. **Satır sağ tık menüsü:** `row_menu` ana menüyü göstermez. Ayarlar/Semboller/
   Portföy/Gruplar satır menüsünde de bulunmalı; yeni ana menü komutu eklerken
   row menüyü unutma.
3. **README:** başka ajan bir kez onaylı README'yi eski metinle ezdi. README
   değişikliklerinde görselleri ve yasak bölümleri kontrol et.
4. **Ekran görüntüsü:** bu oturum türünde `ImageGrab` boş dönebilir.
   `tools/screenshot.py` boş yakalamada mevcut dosyayı **silmez** ve hata kodu
   verir; iyi görselleri elle ezme.
5. **Testler:** `sw._HTTP.get` patch'lenir (requests.get değil); config için
   `sw.CONFIG_FILE`, veri için `SW_DATA_DIR` kullanılır.
6. **Tek kopya:** kurulu kopya açıkken duman testi `SW_INSTANCE_SUFFIX` ile
   ayrılmalı; yoksa "ikinci kopya" deyip çıkar.
7. **Dil:** Tk metinleri `i18n.install_tk_translation()` ile çevrilir; yeni
   görünür metin `i18n._DIRECT`/`_PATTERNS`'e eklenmeli. Log/CLI çevrilmez.
8. **Manuel kurulu kopya güncelleme:** yeni derleme sonrası kısayolların son
   sürümü açması için kurulu exe değiştirilmelidir. İşlem: çalışan kopyayı
   `--quit` ile kapat → yeni onefile exe'yi kurulu yola kopyala → kısayolları
   aynı yola doğrula → uygulamayı yeniden başlat. Eski exe'yi yedekle.
9. **Dependabot** `open-pull-requests-limit: 0` (bilinçli); güvenlik `pip-audit`
   ile. Yeni bağımlılık pinlerini CI audit doğrular.
10. **Kaynak/yayın farkı:** Kod ve kurulu onefile aynı içerikte; yeni kod
    değişikliği yapılırsa kurulu exe tekrar güncellenmeden kısayol eski kodu
    açar. Branch kalmadı; geliştirme `main` üzerinde ilerler.

## Bilinçli sınırlar / yapılmayacaklar

- Otomatik indirme/kurulum yok (güvenlik); yalnızca güncelleme bildirimi.
- Authenticode/SmartScreen sertifikası ücretli; yalnızca SHA256 + Sigstore
  yapı kanıtı.
- UPX/Nuitka yok (AV riski/onefile maliyeti).
- WinGet/Scoop manifestleri üretilir; depolara PR dış onay gerektirir.
- BIST dini bayram tablosu 2024–2030 `market_calendar.py` içinde; yıllık
  güncellenmeli. Genel (generic) borsalarda seans `marketState`'e bağlı.
- Alarmlar yalnızca uygulama açıkken çalışır; arka plan servisi yok.

## Geri alma / merge

```powershell
# çalışma ağacı temizken klasör düzeni öncesine dön
git switch -c geri-al checkpoint/pre-reorg-2026-11-22
# veya mevcut main'i checkpoint'e çekmek için (force):
git switch main
git reset --hard checkpoint/pre-reorg-2026-11-22
```
