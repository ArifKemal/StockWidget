# StockWidget

Windows'ta köşede duran, her zaman üstte kalan küçük bir hisse takip widget'ı.
Python + Tkinter; veri Yahoo Finance'in ücretsiz chart endpoint'inden gelir —
API anahtarı, hesap, abonelik gerekmez. Arayüz Türkçe.

<p align="center">
  <img src="docs/ekran-ana.png" width="360" alt="StockWidget kartı — piyasa sonrası (PS) fiyatları">
</p>

<p align="center">
  <img src="docs/ekran-detay.png" width="720" alt="Kart ve detay paneli — PS rozeti ve son kapanış satırı">
</p>

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
3. Sağ tık menüsünden sembol, portföy, alarm, sıralama, ayarlar ve çıkış işlemleri yapılır.

Ayarlar ve log `%APPDATA%\StockWidget` altında tutulur. Ayarların exe'nin yanında
kalmasını istersen:

```powershell
$env:SW_DATA_DIR = "$PWD\veri"
.\StockWidget-1.1.1.exe
```

## Özellikler

- **Kart:** fiyat, günlük değişim, şirket adı ve mini grafik. PÖ/PS rozeti
  grafikle aynı fiyatı gösterir ve değişimi son normal seans kapanışına göre
  hesaplar; açılışta son fiyatlar önbellekten anında gelir.
- **Detay paneli:** **1G / 1H / 1A / 1Y**, çizgi/mum, hacim ve sağ fiyat ekseni,
  temettü/bölünme işaretleri, hedef/maliyet çizgileri; **Esc** ya da **✕** kapatır.
- **Portföy:** değer, günlük değişim ve pozisyon K/Z; hedef fiyat, not, maliyet,
  para birimi başına toplam, **CSV** ve yerel portföy geçmişi grafiği. PÖ/PS
  açıkken değer, günlük değişim ve K/Z seans dışı fiyatı izler. Karttaki
  göz düğmesi portföy tutarını gizler; yüzdeler görünür kalır.
- **Alarm ve düzen:** fiyat, günlük değişim ve maliyete göre kâr/zarar alarmı;
  detay grafiğinde sağ tıkla seviyeden veya **fiyat girerek** alarm (grafik
  aralığı dışındaki seviyeler okla gösterilir); sessiz saat, erteleme, alarm
  geçmişi; sıralama, gruplar ve odak modu. Sağ tıkta taşıma, kopyalama ve
  Yahoo Finance.
- **Piyasalar:** ABD, BIST ve 7/24 kripto profilleri; BIST tatilleri, ₺ biçimi ve
  çoklu piyasa durumu. PÖ/PS yalnızca ABD borsalarında gösterilir.
- **Görünüm ve tepsi:** Gece / Slate / Grafit / Açık, %60–100 opaklık,
  normal/kompakt, kısa geçişler; **Türkçe/English**, tepsi ve otomatik başlatma.
- **Dayanıklılık:** açıkken 15 dk, kapalıyken 60 dk yenileme; 429’da
  `Retry-After`; tek kopya; günde en fazla bir güncelleme denetimi.
- **Hız:** değişmeyen satır ve mini grafik yeniden çizilmez; disk grafik önbelleği,
  son fiyat önbelleği ve yeniden kullanılan Yahoo bağlantısı.

## Veri kaynağı

`query1.finance.yahoo.com/v8/finance/chart` kullanılır. Resmî olmayan endpoint
olduğu için istek sayısı bilinçli olarak düşük tutulur:

- Fiyat + gün istatistikleri + 1G grafiği + temettü/bölünme: **tek istek**
  (`events=div,splits`). Aynı yanıttaki `marketState`, borsa ve saat dilimi
  okunur. ABD, BIST ve kripto profilleri ayrı seans/tatil kuralları kullanır;
  PÖ/PS yalnızca ABD borsalarında gösterilir. BIST dini bayram tablosu
  `market_calendar.py` içinde tutulur ve yıllık güncellenir.
- Seans dışı fiyat (`includePrePost=true`): aynı yanıttaki son 5 dk barından,
  `prev_close`e göre hesaplanır; ayrı istek yok. 1G penceresi `range=1d` yerine
  açık `period1`/`period2` ile istenir — piyasa öncesi saatlerde Yahoo'nun
  önceki seansa düşmesini engeller.
- 1H / 1A / 1Y: sekmeye ilk tıklamada birer istek; sonra önbellekten (1H: 15 dk,
  1A/1Y: 60 dk). Süre dolunca sekme yeniden açıldığında tazelenir.
- Semboller arasında 0,4 s bekleme; varsayılan aralıklarda 5 sembol ≈ günde
  ~300 istek.

**Gecikme:** Yahoo verisi gecikmeli olabilir; seans dışı fiyatlar düşük
likidite nedeniyle normal seanstan sapabilir. Yatırım kararı için kullanmayın.

## Lisans

MIT — ayrıntılar için [LICENSE](LICENSE). Copyright (c) 2026 Arif Kemal.
