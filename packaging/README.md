# Winget / Scoop manifestleri

Bu klasördeki `.in` dosyaları sürüm, URL ve SHA256 yer tutucuları içerir.
Release iş akışı her sürümde gerçek manifestleri üretir ve release asset'i
olarak ekler; depolara otomatik PR **gönderilmez**.

```powershell
python tools/render_manifests.py `
  --version 1.2.3 `
  --setup-url https://github.com/ArifKemal/StockWidget/releases/download/v1.2.3/StockWidget-1.2.3-setup.exe `
  --setup-sha256 <64-karakter> `
  --portable-url https://github.com/ArifKemal/StockWidget/releases/download/v1.2.3/StockWidget-1.2.3-portable.zip `
  --portable-sha256 <64-karakter> `
  --output-dir packaging-out
```

Çıktılar:

- `packaging-out/winget/ArifKemal.StockWidget.yaml` — kullanıcı bazlı Inno
  kurulumu (`inno`, `Scope: user`).
- `packaging-out/scoop/stockwidget.json` — portatif ZIP, `checkver` + `autoupdate`.

## Yayınlama (dış onay gerekir)

- **Winget:** `microsoft/winget-pkgs` deposuna manifest PR'ı; topluluk
  moderatörleri onaylar. Ücretsizdir ancak tamamen bu reponun kontrolünde değildir.
- **Scoop:** uygun bir bucket deposuna (veya kendi bucket'ınıza) PR/commit.
- **SmartScreen:** Authenticode kod imzalama sertifikası ücretlidir; bu repo
  yalnızca SHA256 + Sigstore yapı kanıtı üretir. Sertifika alınmadan Windows
  uyarısı kalkmaz.
