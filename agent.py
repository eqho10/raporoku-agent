#!/usr/bin/env python3
"""
RaporOku Agent — Yazarkasa Z Raporu Otomatik Yakalayıcı

Yazarkasanın termal yazıcı portunu (seri/USB) dinler,
Z raporu kesildiğinde otomatik yakalar, parse eder,
RaporOku API'ye gönderir → muhasebe fişi otomatik oluşur.

Tüm markalar: Ingenico, Inpos, Hugin, Beko, Profilo, Olivetti

Kullanım:
    raporoku-agent                      # Otomatik port tespit
    raporoku-agent --port COM3          # Windows
    raporoku-agent --port /dev/ttyUSB0  # Linux
    raporoku-agent --list-ports         # Portları listele
    raporoku-agent --setup              # İlk kurulum (API key gir)
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("HATA: pyserial kurun → pip install pyserial")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("HATA: requests kurun → pip install requests")
    sys.exit(1)

# ─── Config ────────────────────────────────────────

VERSION = "2.0.0"
APP_NAME = "RaporOku Agent"
DEFAULT_BAUD = 9600
ENCODING = "cp857"
FALLBACK_ENCODING = "iso-8859-9"

CONFIG_DIR = Path.home() / ".raporoku"
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_DIR = CONFIG_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

DEFAULT_API_URL = "https://raporoku.com"


def load_config() -> dict:
    """Config dosyasını oku."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(config: dict):
    """Config dosyasını kaydet."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


config = load_config()
API_URL = config.get("api_url", DEFAULT_API_URL)
DEVICE_KEY = config.get("device_key", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "agent.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("raporoku-agent")


# ─── İlk Kurulum ────────────────────────────────────

def setup_wizard():
    """İlk kurulum sihirbazı — cihaz anahtarını kaydet."""
    print()
    print("=" * 50)
    print(f"  {APP_NAME} — İlk Kurulum")
    print("=" * 50)
    print()
    print("RaporOku panelinden cihaz eklediğinizde size bir")
    print("cihaz anahtarı verildi. O anahtarı buraya girin.")
    print()

    device_key = input("Cihaz Anahtarı: ").strip()
    if not device_key:
        print("HATA: Cihaz anahtarı gerekli!")
        return

    api_url = input(f"API URL [{DEFAULT_API_URL}]: ").strip() or DEFAULT_API_URL

    # Test bağlantısı
    print("\nBağlantı test ediliyor...")
    try:
        resp = requests.get(
            f"{api_url}/v1/firms/device/status",
            headers={"X-Device-Key": device_key},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ Bağlantı başarılı!")
            print(f"  Firma: {data.get('firm_name', '?')}")
            print(f"  Cihaz: {data.get('device_name', '?')}")
        else:
            print(f"! Uyarı: API yanıt kodu {resp.status_code}")
            print("  Cihaz anahtarını kontrol edin veya devam edin.")
    except Exception as e:
        print(f"! Bağlantı testi başarısız: {e}")
        print("  Internet bağlantınızı kontrol edin veya devam edin.")

    # Kaydet
    cfg = {"device_key": device_key, "api_url": api_url, "setup_date": datetime.now().isoformat()}
    save_config(cfg)

    global API_URL, DEVICE_KEY
    API_URL = api_url
    DEVICE_KEY = device_key

    print(f"\n✓ Ayarlar kaydedildi: {CONFIG_FILE}")
    print("  Artık 'raporoku-agent' komutu ile çalıştırabilirsiniz.\n")


# ─── ESC/POS Temizleyici ──────────────────────────

def strip_escpos(data: bytes) -> str:
    """ESC/POS kontrol kodlarını temizle, saf text döndür."""
    cleaned = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x1B:  # ESC
            i += 2
            continue
        elif b == 0x1D:  # GS
            i += 2
            continue
        elif b in (0x0A, 0x0D):  # LF, CR
            cleaned.append(0x0A)
        elif b == 0x1C:  # FS
            i += 1
            continue
        elif 0x20 <= b <= 0x7E or b >= 0x80:
            cleaned.append(b)
        i += 1

    text = ""
    for enc in (ENCODING, FALLBACK_ENCODING, "utf-8", "latin-1"):
        try:
            text = bytes(cleaned).decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    return text


# ─── Z Raporu Tespit ──────────────────────────────

Z_START_PATTERNS = [
    r"Z\s*RAPOR", r"Z\s*-\s*RAPOR", r"Z\s*NO\s*:",
    r"MAL[İI]\s*RAPOR", r"G[ÜU]N\s*SONU\s*RAPOR",
    r"DAILY\s*REPORT", r"KAPANI[ŞS]\s*RAPOR", r"END\s*OF\s*DAY",
]

Z_END_PATTERNS = [
    r"GENEL\s*TOPLAM\s*GT", r"GT\s*[-:]\s*\d",
    r"MAL[İI]\s*HAFIZA", r"EKU\s*NO", r"\*{5,}", r"-{10,}",
]


def is_z_rapor_start(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in Z_START_PATTERNS)


def is_z_rapor_end(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in Z_END_PATTERNS)


# ─── Z Raporu Parser ──────────────────────────────

def parse_amount(text: str) -> float:
    """Türkçe tutar: 1.234,56 → 1234.56"""
    text = text.strip().replace("*", "").replace("TL", "").replace("₺", "").strip()
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return abs(float(text))
    except ValueError:
        return 0.0


def find_value(text: str, patterns: list, is_int: bool = False):
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE | re.MULTILINE)
        if m:
            val = m.group(1).strip()
            if is_int:
                try:
                    return int(re.sub(r"[^\d]", "", val))
                except ValueError:
                    return 0
            return val
    return 0 if is_int else ""


def parse_z_rapor_text(text: str) -> dict:
    """Z raporu raw text → yapılandırılmış JSON."""
    result = {
        "z_no": "", "tarih": "", "saat": "", "cihaz_no": "", "marka": "",
        "brut_satis": 0.0, "net_satis": 0.0, "toplam_tutar": 0.0,
        "nakit_tutar": 0.0, "kredi_karti_tutar": 0.0, "diger_odeme": 0.0,
        "toplam_kdv": 0.0, "kdv_gruplari": [],
        "fis_sayisi": 0, "iade_tutar": 0.0, "iade_sayisi": 0,
        "iptal_tutar": 0.0, "iptal_sayisi": 0, "indirim_tutar": 0.0,
        "genel_toplam_gt": 0.0, "kaynak": "agent-serial", "confidence": 1.0,
    }

    # Z No
    result["z_no"] = find_value(text, [
        r"Z\s*(?:NO|RAPOR\s*NO|RAPORU\s*NO)\s*[:\-]?\s*(\d+)",
        r"Z\s*RAPOR\s*NO\s*[:\-]?\s*(\d+)",
        r"Z\s*[-]?\s*(\d{4,})",
        r"RAPOR\s*NO\s*[:\-]?\s*(\d+)",
    ])

    # Tarih
    tarih = find_value(text, [
        r"TAR[İI]H\s*[:\-]?\s*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})",
        r"(\d{2}[./]\d{2}[./]\d{4})",
        r"(\d{2}[./]\d{2}[./]\d{2})\b",
    ])
    if tarih:
        for fmt_in, fmt_out in [
            (r"(\d{2})[./](\d{2})[./](\d{4})", r"\3-\2-\1"),
            (r"(\d{2})[./](\d{2})[./](\d{2})", lambda m: f"20{m.group(3)}-{m.group(2)}-{m.group(1)}"),
        ]:
            m = re.match(fmt_in, tarih)
            if m:
                result["tarih"] = fmt_out(m) if callable(fmt_out) else re.sub(fmt_in, fmt_out, tarih)
                break
        if not result["tarih"]:
            result["tarih"] = tarih

    # Saat
    result["saat"] = find_value(text, [r"SAAT\s*[:\-]?\s*(\d{1,2}[.:]\d{2})", r"(\d{2}:\d{2})\s*$"])

    # Cihaz No
    result["cihaz_no"] = find_value(text, [
        r"C[İI]HAZ\s*(?:NO|SER[İI])\s*[:\-]?\s*([A-Z0-9\-]+)",
        r"SER[İI]\s*NO\s*[:\-]?\s*([A-Z0-9\-]+)",
        r"TERM[İI]NAL\s*(?:NO|ID)\s*[:\-]?\s*([A-Z0-9\-]+)",
    ])

    # Toplam — NET SATIŞ öncelikli, sonra TOPLAM SATIŞ, sonra genel TOPLAM
    result["toplam_tutar"] = parse_amount(find_value(text, [
        r"NET\s*(?:SATI[ŞS]|TOPLAM)\s*[:\-]?\s*\*?([\d.,]+)",
        r"SATI[ŞS]\s*TOPLAM[ıI]?\s*[:\-]?\s*\*?([\d.,]+)",
        r"TOPLAM\s*SATI[ŞS]\s*[:\-]?\s*\*?([\d.,]+)",
        r"G[ÜU]NL[ÜU]K\s*TOPLAM\s*[:\-]?\s*\*?([\d.,]+)",
        r"NET\s*TOPLAM\s*[:\-]?\s*\*?([\d.,]+)",
    ]))

    result["brut_satis"] = parse_amount(find_value(text, [
        r"BR[ÜU]T\s*(?:SATI[ŞS])?\s*[:\-]?\s*\*?([\d.,]+)",
    ]))

    result["net_satis"] = parse_amount(find_value(text, [
        r"NET\s*SATI[ŞS]\s*[:\-]?\s*\*?([\d.,]+)",
    ])) or result["toplam_tutar"]

    # Nakit / Kart
    result["nakit_tutar"] = parse_amount(find_value(text, [
        r"NAK[İI]T\s*[:\-]?\s*\*?([\d.,]+)", r"CASH\s*[:\-]?\s*\*?([\d.,]+)",
    ]))
    result["kredi_karti_tutar"] = parse_amount(find_value(text, [
        r"(?:KRED[İI]\s*KART[ıI]?|K\.?\s*KART|CARD|POS)\s*[:\-]?\s*\*?([\d.,]+)",
        r"BANKA\s*KART\s*[:\-]?\s*\*?([\d.,]+)",
        r"KRED[İI]\s*[:\-]?\s*\*?([\d.,]+)",
    ]))

    # KDV Toplam
    result["toplam_kdv"] = parse_amount(find_value(text, [
        r"(?:TOPLAM\s*KDV|KDV\s*TOPLAM)\s*[:\-]?\s*\*?([\d.,]+)",
        r"VERG[İI]\s*TOPLAM\s*[:\-]?\s*\*?([\d.,]+)",
    ]))

    # KDV Grupları
    for oran in [1, 8, 10, 20]:
        patterns = [
            rf"(?:KDV|VERG[İI])\s*%?\s*{oran}\s*(?:MATRAH)?\s*[:\-]?\s*([\d.,]+)\s+(?:KDV\s*[:\-]?\s*)?([\d.,]+)",
            rf"%\s*{oran}\s*[:\-]?\s*(?:MATRAH\s*)?[:\-]?\s*([\d.,]+)\s+(?:KDV\s*)?[:\-]?\s*([\d.,]+)",
            rf"(?:KDV|VERG[İI])\s*%\s*{oran}\s+MT\s*[:\-]?\s*([\d.,]+)\s+VR\s*[:\-]?\s*([\d.,]+)",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                matrah = parse_amount(m.group(1))
                kdv = parse_amount(m.group(2))
                if matrah > 0 or kdv > 0:
                    result["kdv_gruplari"].append({"oran": oran, "matrah": matrah, "kdv": kdv})
                break

    # Fiş sayısı
    result["fis_sayisi"] = find_value(text, [
        r"F[İIi][ŞŞSs]\s*SAYI\w*\s*[:\-]?\s*(\d+)",
        r"FİŞ\s*SAYISI\s*[:\-]?\s*(\d+)",
        r"FIS\s*SAYISI\s*[:\-]?\s*(\d+)",
        r"F[İI][ŞS]\s*ADET\s*[:\-]?\s*(\d+)",
        r"SATI[ŞS]\s*ADET\s*[:\-]?\s*(\d+)",
    ], is_int=True)

    # İade / İptal / İndirim
    result["iade_tutar"] = parse_amount(find_value(text, [r"[İI]ADE\s*(?:TOPLAM)?\s*[:\-]?\s*\*?([\d.,]+)"]))
    result["iptal_tutar"] = parse_amount(find_value(text, [r"[İI]PTAL\s*(?:TOPLAM)?\s*[:\-]?\s*\*?([\d.,]+)"]))
    result["indirim_tutar"] = parse_amount(find_value(text, [r"[İI]ND[İI]R[İI]M\s*(?:TOPLAM)?\s*[:\-]?\s*\*?([\d.,]+)"]))

    # GT
    result["genel_toplam_gt"] = parse_amount(find_value(text, [
        r"G\.?\s*T\.?\s*[:\-]?\s*\*?([\d.,]+)", r"GENEL\s*TOPLAM\s*[:\-]?\s*\*?([\d.,]+)",
    ]))

    if result["toplam_tutar"] == 0 and (result["nakit_tutar"] + result["kredi_karti_tutar"]) > 0:
        result["toplam_tutar"] = result["nakit_tutar"] + result["kredi_karti_tutar"]

    return result


# ─── API Gönderimi ────────────────────────────────

def send_to_api(raw_text: str, z_data: dict) -> dict:
    """Raw Z raporu metnini RaporOku API'ye gönder."""
    if not DEVICE_KEY:
        log.warning("Cihaz anahtarı yok! --setup ile kurulum yapın.")
        return {"status": "skipped", "reason": "no_device_key"}

    url = f"{API_URL}/v1/firms/device/report"
    headers = {"X-Device-Key": DEVICE_KEY, "Content-Type": "application/json"}

    try:
        resp = requests.post(url, json={"raw_text": raw_text}, headers=headers, timeout=15)
        if resp.status_code == 200:
            result = resp.json()
            log.info(f"✓ API'ye gönderildi: Z#{z_data.get('z_no', '?')}")
            return result
        else:
            log.error(f"✗ API hatası: {resp.status_code} — {resp.text[:200]}")
            return {"status": "error", "code": resp.status_code}
    except Exception as e:
        log.error(f"✗ API bağlantı hatası: {e}")
        return {"status": "error", "message": str(e)}


def save_local(z_data: dict, raw_text: str):
    """Z raporu verisini lokal dosyaya kaydet."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    z_no = z_data.get("z_no", "unknown")

    json_path = LOG_DIR / f"z_{z_no}_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(z_data, f, ensure_ascii=False, indent=2)

    txt_path = LOG_DIR / f"z_{z_no}_{ts}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(raw_text)

    log.info(f"Lokal kayıt: {json_path}")


# ─── Port İşlemleri ───────────────────────────────

def list_ports():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("\nHiç seri port bulunamadı!")
        print("Yazarkasanızın USB kablosunu takın ve tekrar deneyin.\n")
        return
    print(f"\n{'Port':<20} {'Açıklama':<40} {'Donanım ID':<30}")
    print("-" * 90)
    for p in ports:
        print(f"{p.device:<20} {p.description:<40} {p.hwid:<30}")
    print()


def auto_detect_port() -> str:
    ports = serial.tools.list_ports.comports()
    keywords = ["serial", "usb", "uart", "ch340", "cp210", "ftdi", "prolific", "pos", "printer"]
    for p in ports:
        desc = (p.description + " " + p.hwid).lower()
        for kw in keywords:
            if kw in desc:
                log.info(f"Otomatik port tespit: {p.device} ({p.description})")
                return p.device
    if ports:
        log.info(f"Varsayılan port: {ports[0].device}")
        return ports[0].device
    return ""


def monitor_port(port: str, baud: int = DEFAULT_BAUD):
    """Seri portu dinle, Z raporu yakala."""
    log.info(f"Port: {port} @ {baud} baud")
    log.info(f"API: {API_URL}")
    log.info(f"Log: {LOG_DIR}")
    log.info("Z raporu bekleniyor... (Ctrl+C ile çıkış)\n")

    try:
        ser = serial.Serial(port, baud, timeout=1)
    except serial.SerialException as e:
        log.error(f"Port açılamadı: {e}")
        log.error("Yazarkasanın USB kablosunu kontrol edin.")
        sys.exit(1)

    buffer = ""
    collecting = False
    last_data_time = 0
    idle_timeout = 5

    try:
        while True:
            raw = ser.read(ser.in_waiting or 1)
            if raw:
                text = strip_escpos(raw)
                last_data_time = time.time()

                if collecting:
                    buffer += text
                elif is_z_rapor_start(text):
                    log.info(">>> Z RAPORU BAŞLADI <<<")
                    collecting = True
                    buffer = text

            if collecting and buffer and (time.time() - last_data_time) > idle_timeout:
                _process_z_report(buffer)
                buffer = ""
                collecting = False

            if collecting and is_z_rapor_end(buffer[-200:] if len(buffer) > 200 else buffer):
                time.sleep(2)
                remaining = ser.read(ser.in_waiting or 0)
                if remaining:
                    buffer += strip_escpos(remaining)
                _process_z_report(buffer)
                buffer = ""
                collecting = False

    except KeyboardInterrupt:
        log.info("\nAgent durduruluyor...")
    finally:
        ser.close()


def _process_z_report(buffer: str):
    """Z raporunu parse et, kaydet, API'ye gönder."""
    log.info(f">>> Z RAPORU TAMAMLANDI ({len(buffer)} karakter) <<<")
    z_data = parse_z_rapor_text(buffer)
    log.info(f"Parse: Z#{z_data['z_no']}, Toplam: {z_data['toplam_tutar']}, "
             f"Nakit: {z_data['nakit_tutar']}, Kart: {z_data['kredi_karti_tutar']}")
    save_local(z_data, buffer)
    api_result = send_to_api(buffer, z_data)
    log.info(f"API: {api_result.get('status', 'unknown')}")
    log.info("Z raporu bekleniyor...\n")


def process_file(filepath: str):
    """Test: text dosyasından Z raporu parse et."""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    z_data = parse_z_rapor_text(text)
    print(json.dumps(z_data, ensure_ascii=False, indent=2))
    save_local(z_data, text)
    if DEVICE_KEY:
        api_result = send_to_api(text, z_data)
        print(f"\nAPI: {json.dumps(api_result, ensure_ascii=False, indent=2)}")


# ─── CLI ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{VERSION} — Yazarkasa Z Raporu Otomatik Yakalayıcı",
        epilog="Örnek: raporoku-agent --port COM3",
    )
    parser.add_argument("--port", "-p", help="Seri port (COM3, /dev/ttyUSB0)")
    parser.add_argument("--baud", "-b", type=int, default=DEFAULT_BAUD, help=f"Baud rate (varsayılan: {DEFAULT_BAUD})")
    parser.add_argument("--list-ports", "-l", action="store_true", help="Mevcut portları listele")
    parser.add_argument("--file", "-f", help="Test: text dosyasından Z raporu parse et")
    parser.add_argument("--setup", "-s", action="store_true", help="İlk kurulum sihirbazı")
    parser.add_argument("--api-url", help="RaporOku API URL")
    parser.add_argument("--device-key", help="Cihaz anahtarı")

    args = parser.parse_args()

    global API_URL, DEVICE_KEY
    if args.api_url:
        API_URL = args.api_url
    if args.device_key:
        DEVICE_KEY = args.device_key

    print()
    print("╔══════════════════════════════════════════╗")
    print(f"║  {APP_NAME} v{VERSION:<25}  ║")
    print("║  Yazarkasa Z Raporu Otomatik Yakalayıcı  ║")
    print("╚══════════════════════════════════════════╝")
    print()

    if args.setup:
        setup_wizard()
        return

    if args.list_ports:
        list_ports()
        return

    if args.file:
        process_file(args.file)
        return

    # Config kontrolü
    if not DEVICE_KEY:
        print("Cihaz anahtarı bulunamadı!")
        print("İlk kurulum için: raporoku-agent --setup")
        print()
        sys.exit(1)

    port = args.port or auto_detect_port()
    if not port:
        log.error("Seri port bulunamadı! --port ile belirtin veya --list-ports ile kontrol edin.")
        sys.exit(1)

    monitor_port(port, args.baud)


if __name__ == "__main__":
    main()
