# Kod imzalama (SmartScreen) — durum ve yol haritası

StockWidget'ın `setup.exe` ve `StockWidget.exe` dosyaları **imzasız**. Bu yüzden
ilk indirmede Windows SmartScreen "Windows korumalı bilgisayarınızı korudu"
uyarısını gösterebilir. README'de kullanıcıya **Ek bilgi → Yine de çalıştır**
denmesi gerektiği yazılı.

İmza, uyarıyı tamamen kaldırmaz ama itibar kazandıkça azaltır; asıl faydası
kurumsal makinelerde "bilinmeyen yayıncı" politikalarına takılmayı önlemesidir.

## Seçenekler (2026)

| Yol | Ücret | Not |
|---|---|---|
| **SignPath Foundation** | Ücretsiz (açık kaynak) | OSS projelere ücretsiz Authenticode imzalama; başvuru ve onay gerekir. En gerçekçi ücretsiz yol. |
| Azure Trusted Signing | ~10 USD/ay | 3 yıllık geçmiş ve organizasyon doğrulaması ister; bireysel projede uygun değil. |
| Kendinden imzalı sertifika | Ücretsiz | SmartScreen'i **çözmez**; yalnızca kurumsal dağıtımda IT tarafından güvenilen sertifika olarak işe yarar. |
| Sertifika satın alma (OV/EV) | 200–500 USD/yıl | Donanım token zorunlu; bu proje için gereksiz. |

Karar: **şimdilik imzasız devam**, SignPath Foundation başvurusu yapılırsa CI'a
imzalama adımı eklenir. Kod tarafında değişiklik gerekmez; yalnızca derleme
sonrası `signtool` adımı eklenir.

## SignPath başvurusu (yapılacaklar)

1. <https://signpath.org/> üzerinden "Apply" formunu doldur:
   - Proje: `ArifKemal/StockWidget`
   - Lisans: MIT
   - Artefakt: `StockWidget-*-setup.exe`, `StockWidget.exe` (PyInstaller çıktısı)
2. Onaydan sonra SignPath organizasyonu ve proje ayarlarında:
   - **Artifact configuration**: `application/zip` (portatif ZIP) ve
     `application/octet-stream` (setup.exe) kabul eden kurallar
   - **Signing policy**: `release` (yalnızca `v*` etiketli derlemeler)
3. GitHub tarafında:
   - SignPath GitHub App'i repoya kur
   - Repo secrets: `SIGNPATH_API_TOKEN`, `SIGNPATH_ORGANIZATION_ID`
4. `.github/workflows/release.yml` içine imzalama adımı ekle (aşağıdaki örnek).

## Örnek imzalama adımı (onay sonrası açılacak)

`release.yml` içinde "Portatif derleme" adımından **sonra**, ZIP/ISCC
adımlarından **önce** çalışmalı; böylece hem exe hem kurulum paketi imzalı
girdilerden üretilir.

```yaml
      - name: SignPath ile imzala (yalnızca onaydan sonra)
        if: vars.SIGNPATH_ENABLED == 'true'
        uses: signpath/github-action-submit-signing-request@v1
        with:
          api-token: ${{ secrets.SIGNPATH_API_TOKEN }}
          organization-id: ${{ secrets.SIGNPATH_ORGANIZATION_ID }}
          project-slug: stockwidget
          signing-policy-slug: release
          artifact-configuration-slug: exe
          github-artifact-id: ${{ steps.upload-unsigned.outputs.artifact-id }}
          wait-for-completion: true
          output-artifact-directory: dist/StockWidget
```

Notlar:

- SignPath exe'yi tek tek imzalar; PyInstaller `onedir` çıktısında DLL'ler
  imzalanmaz (gerekmez, SmartScreen exe'ye bakar).
- Inno Setup **kurulum paketini** de imzalamak için `SignTool` direktifi
  kullanılır:
  ```ini
  [Setup]
  SignTool=signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 $f
  ```
  Bu satır yalnızca imzalama aktifken eklenmeli; imzasız derlemede ISCC hata
  verir. Alternatif: imzalama sonrası `signtool` ile setup.exe'yi ayrıca imzala.
- Zaman damgası (timestamp) olmadan sertifika süresi dolunca eski sürümlerin
  imzası geçersiz görünür; yukarıdaki `/tr` satırı bunu önler.

## Kullanıcıya söylenecekler (imza yokken)

README'deki mevcut metin yeterli:

> Dosyalar kod imzalı değil. "Windows korumalı bilgisayarınızı korudu"
> penceresinde **Ek bilgi → Yine de çalıştır** deyin. Kaynak koddan kendiniz
> derlerseniz uyarı çıkmaz.

İmza eklendiğinde bu not "dosyalar SignPath ile imzalıdır" şeklinde
güncellenmeli ve sürüm notlarına yazılmalı.
