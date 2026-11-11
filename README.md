# StockWidget (Borsa Widget)

Windows için şık, her zaman üstte duran hisse takip widget'ı. Yahoo Finance'ten
ücretsiz veri çeker, sistem tepsisinde yaşar, PC açılışında kendini başlatabilir.

## Özellikler

- **Modern kart arayüzü** — yuvarlak köşeli, yarı saydam koyu kart
- **Mini grafik (sparkline)** — anti-aliased, gradyan dolgulu gün içi fiyat eğrisi
- **Fiyat + gün değişimi** — hizalı (monospace) fiyat, **▲/▼** trend oklu renkli yüzde rozetleri
- **Detay paneli** — satıra tıkla: gün aralığı, açılış, önceki kapanış, hacim,
  52 hafta aralığı ve **1G / 1H / 1A / 1Y** sekmeleriyle günlük, haftalık, aylık,
  yıllık grafik
- **Fareyle grafik inceleme** — detay grafiğinde imleci gezdirince o noktanın zamanı,
  fiyatı ve gün içi / dönem değişimi (% olarak) görünür
- **Zengin grafik** — hacim çubukları, sağ fiyat ekseni ve **mum / çizgi** geçişi
- **Portföy** — sembol başına adet + ortalama maliyet; alt şeritte toplam değer ve günlük değişim
- **Kişiselleştirme** — **Gece / Slate / Grafit / Açık** tema, opaklık (%80–100) ve
  **Normal / Kompakt** yoğunluk
- **Satır bilgisi** — sembolün altında şirket adı, alt satırda göreli güncelleme zamanı ("2 dk önce")
- **System tray** — `$`/mum ikonu: göster/gizle, yenile, semboller, çıkış
- **Global kısayol** — **Ctrl+Alt+S** ile her yerden göster/gizle
- **Tek tıkla aç/kapa** — masaüstündeki **Borsa Widget** kısayolu
- **Sürükle-bırak** — konum otomatik kaydedilir
- **Sembol yönetimi** — ekle (arka planda doğrulamalı, UI donmaz) / çıkar, dialog ile
- **Akıllı güncelleme** — piyasa açıkken 15 dk, kapalıyken 1 saat (ABD borsa tatilleri dahil)
- **Offline mod** — bağlantı koparsa son fiyatlar kalır, otomatik dener
- **Tek örnek koruması** — çift tıklasanız bile ikinci kopya açılmaz

## Kurulum

```powershell
pip install -r requirements.txt   # requests, pystray, pillow
```

Masaüstü kısayolu `Borsa Widget` bu klasördeki `toggle.vbs` dosyasını çalıştırır.

## Aç / Kapa (manuel kontrol)

| Yol | Nasıl |
|---|---|
| Masaüstü kısayolu | **Borsa Widget** ikonuna çift tık → açıksa kapatır, kapalıysa açar |
| Tray menüsü | Tepsideki simge → **Göster / Gizle** (kapatmaz, gizler) |
| Global kısayol | **Ctrl+Alt+S** — hangi uygulamada olursan ol gösterir / gizler |
| Tray menüsü | Tepsideki simge → **Çıkış** (tamamen kapatır) |
| Widget sağ tık | **Gizle** / **Çıkış** |
| Konsol | `wscript toggle.vbs` |

`toggle.vbs` sadece bu klasördeki `stock_widget.py` sürecini bulur ve kapatır;
başka Python uygulamalarına dokunmaz.

## Kullanım

| Eylem | Nasıl |
|---|---|
| Taşıma | Kartın herhangi bir yerinden sürükle |
| Sembol ekle / çıkar | Sağ tık → **Sembol ekle / çıkar…** (veya başlığa/alt satıra çift tık) |
| Hızlı çıkarma | Sağ tık → **Hızlı çıkar** → sembol |
| Detay | Bir satıra **tek tıkla** → detay paneli açılır; aynı satıra tekrar tıkla ya da paneldeki **✕** ile kapat |
| Grafik aralığı | Detay panelinde **1G / 1H / 1A / 1Y** sekmeleri (gün, hafta, ay, yıl) |
| Grafikte okuma | Detay grafiğinde fareyi gezdir → kesikli çizgi + fiyat ve yüzde değişimi |
| Grafik modu | Detay panelinde sekme satırının sağındaki **mum / çizgi** yazısına tıkla |
| Portföy | Sağ tık → **Portföy…** → adet + ortalama maliyet gir → **Kaydet** |
| Yenile | Sağ tık → **Yenile** veya tray menüsü |
| Tema | Sağ tık → **Tema** → Gece / Slate / Grafit / Açık |
| Opaklık | Sağ tık → **Opaklık** → %80 / %85 / %90 / %95 / %100 |
| Yoğunluk | Sağ tık → **Yoğunluk** → Normal / Kompakt |
| Tray'e al (gizle) | Sağ üstteki **✕** — kapatmaz, pencereyi tepsiye gizler |
| Çıkış | Sağ tık → **Çıkış** (veya tray menüsü → **Çıkış**) |
| Otomatik başlatma | Sağ tık → **Windows'ta otomatik başlat** (işaretli = açık) |

Sembol eklerken ticker önce Yahoo'dan doğrulanır; bulunamazsa hata mesajı
dialog içinde gösterilir.

## Windows Başlangıcı

Menüden işaretlenebilir. Konsoldan:

```powershell
.\install_startup.ps1    # ekle
.\uninstall_startup.ps1  # kaldır
```

Kayıt: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\StockWidget`

## Veri Kaynağı ve API Disiplini

- **Yahoo Finance** `query1.finance.yahoo.com/v8/finance/chart` (anahtar gerekmez)
- `interval=5m&range=1d` — fiyat, gün değişimi, sparkline ve detay paneli
  (gün yüksek/düşük, hacim, 52 hafta aralığı, önceki kapanış) **aynı istekten** gelir
- Detay paneli **1G / 1H / 1A / 1Y** sekmeleri: 1G ek istek yapmaz; diğerleri ilk
  tıklamada tek istek (`5d/15m`, `1mo/1d`, `1y/1d`) ve 15 dk / 1 saat / 1 saat cache'lenir
- Sembol başına 1 istek; semboller arası 0,4 sn bekleme
- Piyasa açık: 15 dk · kapalı: 60 dk · hata: 90 sn · **429**: 5 dk bekleme
- Piyasa saatleri ABD Doğu saati (9:30–16:00); hafta sonu ve **NYSE resmi tatilleri**
  (Yılbaşı, MLK, Presidents, Good Friday, Memorial, Juneteenth, Independence, Labor,
  Thanksgiving, Noel) kapalı sayılır
- Sembol eklerken doğrulama isteği arka plan thread'inde yapılır — arayüz donmaz
- 5 sembol ≈ günde ~300 istek — ücretsiz limitlerin çok altında

## Yapılandırma

`config.json` otomatik yönetilir:

```json
{
  "symbols": ["ONDS", "BRUN"],
  "x": 1506,
  "y": 385,
  "theme": "grafit",
  "opacity": 0.97,
  "density": "normal",
  "positions": {
    "ONDS": {"qty": 100, "avg": 12.5}
  }
}
```

`theme`: `gece` / `slate` / `grafit` / `acik` · `opacity`: 0.6–1.0 ·
`density`: `normal` / `compact` · `positions`: isteğe bağlı (adet + ortalama maliyet).
Menüden değiştirilince otomatik kaydedilir.

## Dosyalar

```
StockWidget/
├── stock_widget.py        # uygulama
├── config.json            # semboller, konum, tema, portföy
├── sw.log                 # çalışma günlüğü (otomatik, döndürülür)
├── test_stock_widget.py   # birim testler
├── toggle.vbs             # tek tıkla aç / kapa
├── stock.ico              # uygulama / kısayol ikonu
├── requirements.txt       # requests, pystray, pillow
├── install_startup.ps1    # başlangıca ekle
├── uninstall_startup.ps1  # başlangıçtan kaldır
├── README.md              # kullanıcı dokümanı
└── AGENT.md               # geliştirici notları (mimari + changelog)
```

## Test

```powershell
python -m py_compile stock_widget.py
python -m unittest test_stock_widget.py      # birim testler
$env:SW_SMOKE="1"; python stock_widget.py    # 12 sn sonra kendini kapatır
```

## Sık Sorunlar

| Sorun | Çözüm |
|---|---|
| Widget görünmüyor | Tray simgesine tıkla → **Göster / Gizle** |
| Tray ikonu yok | `pip install pystray pillow` |
| Veri gelmiyor | İnternet / Yahoo erişimi; 429 ise 5 dk bekle |
| Ctrl+Alt+S çalışmıyor | Başka bir uygulama bu kısayolu kapmış olabilir; sağ tık menüsünde "kaydedilemedi" yazar |
| Kısayol çalışmıyor | `pythonw.exe` PATH'te olmalı (`where pythonw`) |

## Lisans

MIT
