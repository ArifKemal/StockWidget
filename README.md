# StockWidget

Windows'ta köşede duran, her zaman üstte kalan küçük bir hisse takip widget'ı.
Python + Tkinter; veri Yahoo Finance'in ücretsiz chart endpoint'inden gelir —
API anahtarı, hesap, abonelik gerekmez. Arayüz Türkçe.

![StockWidget kartı](docs/ekran-ana.png)

![StockWidget detay paneli](docs/ekran-detay.png)

## İndir

| Dosya | Ne zaman |
|---|---|
| **`StockWidget-<sürüm>.exe`** | **Önerilen.** İndir, çift tıkla, çalışır. Kurulum yok. |
| `StockWidget-<sürüm>-setup.exe` | Kısayol, otomatik başlatma ve kaldırma girişi istersen. |
| `StockWidget-<sürüm>-portable.zip` | Tek dosya antivirüs tarafından engellenirse (yedek). |

[Releases](https://github.com/ArifKemal/StockWidget/releases/latest) sayfasından
indir. 64-bit Windows 10/11 hedeflenir.

> **SmartScreen:** Dosyalar kod imzalı değil. "Windows korumalı bilgisayarınızı
> korudu" derse **Ek bilgi → Yine de çalıştır** deyin. Kendiniz derlerseniz uyarı
> çıkmaz; imzalama durumu: [docs/imzalama.md](docs/imzalama.md).

## Hızlı başlangıç

1. Exe'yi çalıştır. İlk açılış birkaç saniye sürebilir (tek dosya geçici klasöre açılır).
2. Widget sağ üstte belirir. **Ctrl+Alt+S** her yerden gösterir/gizler.
3. Sağ tık menüsünden sembol, portföy, tema ve çıkış işlemleri yapılır.

Ayarlar ve log `%APPDATA%\StockWidget` altında tutulur. Ayarların exe'nin yanında
kalmasını istersen:

```powershell
$env:SW_DATA_DIR = "$PWD\veri"
.\StockWidget-1.1.0.exe
```

## Kullanım

| Ne | Nasıl |
|---|---|
| Göster / gizle | **Ctrl+Alt+S**, tepsi menüsü veya karttaki **✕** (varsayılan: tepsiye gizler) |
| Yenile | Karttaki **⟳** ya da sağ tık → **Yenile** |
| Tamamen çık | Sağ tık → **Çıkış**, tepsi → **Çıkış** ya da Ayarlar'da "kapatınca tepsiye gizle" kapalıyken **✕** |
| Taşı | Kartı sürükle; konum hatırlanır |
| Sembol ekle / çıkar | Sağ tık → **Sembol ekle / çıkar…** |
| Portföy | Sağ tık → **Portföy…** → adet + ortalama maliyet |
| Ayarlar | Sağ tık → **Ayarlar…** (tema, opaklık, yoğunluk, yenileme, davranış) |
| Komutlar | `--toggle` göster/gizle, `--quit` kapat, `--version`, `--paths` |

Detay paneli satıra tıklayınca açılır: **1G / 1H / 1A / 1Y** aralıkları, mum/çizgi
geçişi, fareyle zaman-fiyat-yüzde okuması.

## Özellikler

- **Kart:** sembol, fiyat, günlük değişim, şirket adı ve mini grafik; sabit
  genişlikli rakamlar, "son güncelleme" zamanı, piyasa durumu noktası.
- **Portföy:** toplam değer, günlük değişim ve pozisyon başına K/Z.
- **Görünüm:** Gece / Slate / Grafit / Açık tema, %60–100 opaklık, normal/kompakt,
  her zaman üstte.
- **Tepsi:** göster/gizle, yenile, ayarlar, semboller, otomatik başlatma, çıkış.
- **Dayanıklılık:** varsayılan açıkken 15 dk, kapalıyken 60 dk yenileme (Ayarlar'dan
  değiştirilebilir); hata sonrası 90 s, HTTP 429'da 5 dk bekleme; NYSE tatilleri
  kapalı sayılır; tek kopya çalışır. "Piyasa kapalıyken durdur" seçilirse kapalıyken
  hiç istek gönderilmez.

## Veri kaynağı

`query1.finance.yahoo.com/v8/finance/chart` kullanılır. Resmî olmayan endpoint
olduğu için istek sayısı bilinçli olarak düşük tutulur:

- Fiyat + gün istatistikleri + 1G grafiği: **tek istek**.
- 1H / 1A / 1Y: sekmeye ilk tıklamada birer istek, sonra önbellekten.
- Semboller arasında 0,4 s bekleme; varsayılan aralıklarda 5 sembol ≈ günde
  ~300 istek.

**Gecikme:** Yahoo verisi gecikmeli olabilir; pre/post market yok. Yatırım kararı
için kullanmayın.

## Ayarlar

Sağ tık → **Ayarlar…**: görünüm (tema, opaklık, yoğunluk, her zaman üstte,
konumu sıfırla), veri (yenileme aralıkları, kapalıyken durdur, elle yenile),
davranış (otomatik başlat, ✕ davranışı) ve gelişmiş (ayar klasörü). Değişiklikler
anında uygulanır; **Sıfırla** yalnızca ayarları varsayılana döndürür
(semboller, portföy ve otomatik başlatma korunur).

`%APPDATA%\StockWidget\config.json` (portatif modda `SW_DATA_DIR` altında).
Bozuk alan uygulamayı kilitlemez, varsayılana döner.

| Anahtar | Değer |
|---|---|
| `symbols` | Ticker listesi; boşsa varsayılan 5 sembol. |
| `x`, `y` | Kartın konumu; sürükleyince kaydedilir. |
| `theme` | `gece`, `slate`, `grafit`, `acik`. |
| `opacity` | 0.6–1.0. |
| `density` | `normal` ya da `compact`. |
| `always_on_top` | `true` / `false`; varsayılan `true`. |
| `refresh_open`, `refresh_closed` | Yenileme aralığı (dakika, 1–1440). |
| `pause_when_closed` | `true` ise piyasa kapalıyken istek gönderilmez. |
| `close_to_tray` | `true` ise **✕** tepsiye gizler; `false` ise çıkar. |
| `positions` | `{ "AAPL": { "qty": 12, "avg": 185.4 } }` |

## Geliştirme

```powershell
git clone https://github.com/ArifKemal/StockWidget.git
cd StockWidget
pip install -r requirements.txt
pythonw stock_widget.py        # konsolsuz çalıştırma

python -m unittest test_stock_widget.py    # 13 test, ağa çıkmaz
python tools/bump_version.py 1.1.0
```

Paketleme:

```powershell
python -m PyInstaller --noconfirm --clean --distpath dist-onefile StockWidget-onefile.spec
python -m PyInstaller --noconfirm --clean StockWidget.spec        # ZIP yedeği
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss   # setup.exe
```

`v*` etiketi atınca CI test eder ve üç asseti Release'e yükler; sürüm numarası
etiketten alınır (`git tag v1.1.0 && git push --tags`).

## Sorun çıkarsa

- **Widget görünmüyor:** Ctrl+Alt+S ya da tepsi → Göster. ✕ sadece gizler.
- **Veri gelmiyor:** internet/Yahoo erişimini kontrol edin. 429 ise 5 dk bekleyin.
- **Tepsi ikonu yok / köşeler keskin:** `pystray` ve `pillow` eksik olabilir
  (kaynak modunda); uygulama yine çalışır.
- **Tepsi ikonu görünmüyor (Windows 11):** Simge gizli simgeler alanındadır —
  görev çubuğundaki **^** okuna bakın, oradaki simgeyi sağ tık → sabitleyin ya
  da **Ayarlar → Kişiselleştirme → Görev çubuğu → Diğer sistem tepsisindeki
  simgeler** listesinden StockWidget'ı açın.
- **Simge/Ayarlar kaydedilmiyor:** Malwarebytes gibi bir güvenlik yazılımı
  imzasız exe'yi engelliyor olabilir; StockWidget.exe için istisna ekleyin.
- **Kısayol çalışmıyor:** Ctrl+Alt+S başka uygulamada tanımlı olabilir.
- **Kurulum "Error 5" diyor:** makine kısıtlı olabilir (Başlat menüsü/kayıt
  defteri yazımı engelli). Kurulum bunu söyler; portatif sürümü kullanın.
- **Kurulum "%TEMP% ... Access is denied" diyor:** `TEMP`/`TMP` yazılamıyor.
  `set TEMP=C:\Temp&& set TMP=C:\Temp` sonrası kurulumu tekrar çalıştırın.
- **Ayrıntı:** `%APPDATA%\StockWidget\sw.log`.

## Sınırlar

- Piyasa saati ve tatiller ABD (NYSE) içindir; pre/post market yoktur.
- Portföy K/Z son fiyata göredir; komisyon, kur ve vergi hesaba katılmaz.
- Windows 10/11 x64; macOS/Linux desteklenmez.
- Yahoo endpoint'i resmî değildir; ileride veri kaynağı değişebilir.

## Lisans

MIT — ayrıntılar için [LICENSE](LICENSE). Copyright (c) 2026 Arif Kemal.
