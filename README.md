# StockWidget

Windows'ta köşede duran, her zaman üstte kalan küçük bir hisse takip widget'ı.
Python + Tkinter; veri Yahoo Finance'in ücretsiz chart endpoint'inden gelir —
API anahtarı, hesap, abonelik gerekmez. Arayüz Türkçe.

![StockWidget kartı — piyasa sonrası (PS) fiyatları](docs/ekran-ana.png)

![Kart ve detay paneli — PS rozeti ve son kapanış satırı](docs/ekran-detay.png)

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

## Özellikler

- **Kart:** sembol, fiyat, günlük değişim, şirket adı ve mini grafik; sabit
  genişlikli rakamlar, "son güncelleme" zamanı, piyasa durumu noktası.
- **Seans dışı:** piyasa öncesi/sonrası fiyat ve değişim, satırda ve detay
  panelinde **PÖ** / **PS** rozetiyle gösterilir. Değer, grafiği besleyen son
  5 dk barından okunur; bu yüzden kart, detay ve grafik her zaman aynı fiyatı
  gösterir, ek istek yapılmaz. 1G grafiği 04:00–20:05 ET barlarını içerir ve
  eksenin sağ ucu son verinin saatini ("şimdi" ya da saat) gösterir.
- **Portföy:** toplam değer, günlük değişim ve pozisyon başına K/Z.
- **Detay paneli:** satıra tıklayınca açılır; **1G / 1H / 1A / 1Y** aralıkları,
  mum/çizgi geçişi, fareyle zaman-fiyat-yüzde okuması, gün aralığı ve 52 hafta
  çubuğu. **Esc** (ya da sağ üstteki **✕**) paneli kapatır.
- **Görünüm:** Gece / Slate / Grafit / Açık tema, %60–100 opaklık, normal/kompakt,
  her zaman üstte.
- **Hareket:** panel açılışı/kapanışı, sekme vurgusu, satır vurgusu ve kart
  göster/gizle kısa (90–130 ms) yumuşak geçişlerle yapılır; Windows'ta
  "animasyonları göster" kapalıysa hareketler otomatik devre dışı kalır.
- **Tepsi:** göster/gizle, yenile, ayarlar, semboller, otomatik başlatma, çıkış.
- **Dayanıklılık:** varsayılan açıkken 15 dk, kapalıyken 60 dk yenileme (Ayarlar'dan
  değiştirilebilir); hata sonrası 90 s, HTTP 429'da 5 dk bekleme; NYSE tatilleri
  kapalı sayılır; tek kopya çalışır. "Piyasa kapalıyken durdur" seçilirse kapalıyken
  hiç istek gönderilmez.

## Veri kaynağı

`query1.finance.yahoo.com/v8/finance/chart` kullanılır. Resmî olmayan endpoint
olduğu için istek sayısı bilinçli olarak düşük tutulur:

- Fiyat + gün istatistikleri + 1G grafiği: **tek istek**.
- Seans dışı fiyat (`includePrePost=true`): aynı yanıttaki son 5 dk barından,
  `prev_close`e göre hesaplanır; ayrı istek yok. 1G penceresi `range=1d` yerine
  açık `period1`/`period2` ile istenir — piyasa öncesi saatlerde Yahoo'nun
  önceki seansa düşmesini engeller.
- 1H / 1A / 1Y: sekmeye ilk tıklamada birer istek, sonra önbellekten.
- Semboller arasında 0,4 s bekleme; varsayılan aralıklarda 5 sembol ≈ günde
  ~300 istek.

**Gecikme:** Yahoo verisi gecikmeli olabilir; seans dışı fiyatlar düşük
likidite nedeniyle normal seanstan sapabilir. Yatırım kararı için kullanmayın.

## Ayarlar

Sağ tık → **Ayarlar…**: görünüm (tema, opaklık, yoğunluk, her zaman üstte,
konumu sıfırla), veri (yenileme aralıkları, piyasa öncesi/sonrası, kapalıyken
durdur, elle yenile), davranış (otomatik başlat, ✕ davranışı) ve gelişmiş
(ayar klasörü). Değişiklikler anında uygulanır; **Sıfırla** yalnızca ayarları
varsayılana döndürür (semboller, portföy ve otomatik başlatma korunur).

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
| `pause_when_closed` | `true` ise hiçbir seans açık değilken istek gönderilmez. |
| `extended_hours` | `true` ise piyasa öncesi/sonrası (**PÖ**/**PS**) verisi gösterilir. |
| `close_to_tray` | `true` ise **✕** tepsiye gizler; `false` ise çıkar. |
| `positions` | `{ "AAPL": { "qty": 12, "avg": 185.4 } }` |

## Lisans

MIT — ayrıntılar için [LICENSE](LICENSE). Copyright (c) 2026 Arif Kemal.
