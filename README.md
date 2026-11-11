# StockWidget

Windows'ta masaüstünün köşesinde duran küçük bir hisse takip widget'ı. Kendi
takip listem için yazdım: tek dosya Python + Tkinter, her zaman üstte kalıyor,
veriyi Yahoo Finance'in ücretsiz chart endpoint'inden çekiyor.

## Neler var

Takip listesindeki her sembol için fiyat, günlük yüzde değişimi ve gün içi mini
grafik görünüyor. Fiyatlar sabit genişlikli yazı tipinde olduğu için rakam
değişince satır sağa sola zıplamıyor.

Satıra tıklayınca detay paneli açılıyor. Gün aralığı, açılış, önceki kapanış,
hacim ve 52 hafta aralığı burada; grafikte 1G / 1H / 1A / 1Y sekmeleri var.
Fareyle grafiğin üzerinde gezindiğinde o noktanın fiyatı ve değişimi çıkıyor.
Grafiği çizgi ya da mum olarak görebiliyorsun.

Sağ tık menüsünde tema (Gece, Slate, Grafit, Açık), opaklık ve satır yoğunluğu
ayarları var. Portföy penceresinden adet ve ortalama maliyet girersen alttaki
şeritte toplam değer ve günlük değişim görünüyor.

Widget tepside yaşıyor. Ctrl+Alt+S her yerden göster/gizle yapıyor. Sağ üstteki
✕ pencereyi kapatmıyor, tepsiye alıyor; tamamen kapatmak için menüden Çıkış.
İkinci bir kopya açılmıyor.

## Kurulum

```
pip install -r requirements.txt
pythonw stock_widget.py
```

Masaüstündeki "Borsa Widget" kısayolu `toggle.vbs` dosyasını çalıştırıyor:
widget açıksa kapatıyor, kapalıysa başlatıyor.

Windows açılışında başlaması için sağ tık menüsünden işaretleyebilirsin ya da:

```
.\install_startup.ps1
```

## Kullanma

- Taşımak için kartın herhangi bir yerinden sürükle; konum hatırlanıyor.
- Sembol eklemek/çıkarmak için sağ tık > Sembol ekle / çıkar... Ticker önce
  Yahoo'dan doğrulanıyor, bulunamazsa dialog içinde hata gösteriyor.
- Detay panelini aynı satıra tekrar tıklayarak ya da paneldeki ✕ ile kapat.
- Detay panelinde sekme satırının sağındaki "mum" yazısı çizgi/mum modunu
  değiştiriyor.

## Veri ve güncelleme

Yahoo'nun `query1.finance.yahoo.com/v8/finance/chart` endpoint'i kullanılıyor,
anahtar gerekmiyor. Sembol başına döngüde tek istek var, semboller arasında
0.4 saniye bekleniyor. Piyasa açıkken 15 dakikada bir, kapalıyken saatte bir
yenileniyor. Hata olursa 90 saniye sonra tekrar deniyor; 429 gelirse 5 dakika
bekliyor.

1G grafiği zaten gelen veriden çiziliyor, ek istek atmıyor. 1H / 1A / 1Y
sekmeleri ilk açıldığında birer istek atıyor ve 15 dk / 1 saat önbellekte
kalıyor.

Küçük bir uyarı: bu endpoint resmî değil. Yahoo tarafında bir şey değişirse
haber vermeden bozulabilir. Kod o yüzden tek dosyada ve olabildiğince sade.

## config.json

Widget kendi ayarlarını buraya yazıyor:

```json
{
  "symbols": ["ONDS", "BRUN"],
  "x": 1506,
  "y": 385,
  "theme": "gece",
  "opacity": 0.97,
  "density": "normal",
  "positions": {
    "ONDS": { "qty": 100, "avg": 12.5 }
  }
}
```

`theme`: gece / slate / grafit / acik  
`opacity`: 0.6 - 1.0  
`density`: normal / compact  
`positions`: opsiyonel, adet ve ortalama maliyet.

## Dosyalar

```
stock_widget.py        uygulamanın tamamı
config.json            ayarlar ve portföy
sw.log                 çalışma günlüğü (bir şey ters giderse buraya bak)
test_stock_widget.py   birkaç birim test
toggle.vbs             tek tıkla aç / kapa
stock.ico              ikon
install_startup.ps1    başlangıca ekle
uninstall_startup.ps1  başlangıçtan kaldır
```

## Test

```
python -m py_compile stock_widget.py
python -m unittest test_stock_widget.py
set SW_SMOKE=1 && python stock_widget.py
```

## Sorun çıkarsa

- Widget görünmüyorsa tepsi simgesine tıkla, Göster / Gizle.
- Tepsi ikonu yoksa pystray ve pillow kurulu mu bak.
- Veri gelmiyorsa interneti ve Yahoo erişimini kontrol et; 429 ise 5 dakika bekle.
- Ctrl+Alt+S çalışmıyorsa başka bir uygulama kısayolu kapmış olabilir. Sağ tık
  menüsünde "kaydedilemedi" yazıyorsa durum bu.
- Kısayol çalışmıyorsa pythonw.exe PATH'te olmalı (`where pythonw`).

## Notlar

Tkinter ile yazdım; Windows'ta ek kurulum derdi olmasın istedim. Bu yüzden
gerçek gölge, blur gibi efektler yok, eldeki çizimle idare ediyorum. Grafikler
Pillow ile çizildiği için kenarlar düzgün çıkıyor.

Kod bilerek tek dosyada. Küçük bir araç için paket yapısı kurmak istemedim.

## Lisans

MIT
