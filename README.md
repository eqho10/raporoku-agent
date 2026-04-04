# RaporOku Agent

Yazarkasa Z raporlarını otomatik yakalayan masaüstü uygulaması.

## Kurulum (Windows)

1. `raporoku-agent.exe` dosyasını indirin
2. Çift tıklayarak çalıştırın
3. İlk seferde `--setup` ile cihaz anahtarınızı girin:
   ```
   raporoku-agent.exe --setup
   ```
4. Yazarkasanızın USB kablosunu bilgisayara takın
5. Tekrar çalıştırın:
   ```
   raporoku-agent.exe
   ```

## Komutlar

```
raporoku-agent --setup          # İlk kurulum (cihaz anahtarı gir)
raporoku-agent                  # Otomatik port tespit ile çalıştır
raporoku-agent --port COM3      # Belirli port ile çalıştır
raporoku-agent --list-ports     # Mevcut portları listele
raporoku-agent --file rapor.txt # Test: dosyadan parse et
```

## Nasıl Çalışır

1. Yazarkasanın seri/USB portunu dinler
2. Z raporu kesildiğinde otomatik yakalar
3. ESC/POS formatını temizler, parse eder
4. RaporOku API'ye gönderir
5. Lokal yedek de kaydeder (`~/.raporoku/logs/`)

## Desteklenen Markalar

Ingenico, Inpos, Hugin, Beko, Profilo, Olivetti, Verifone

## Build (Geliştirici)

```bash
pip install -r requirements.txt
pyinstaller --onefile --name raporoku-agent --console agent.py
```
