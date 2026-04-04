#!/usr/bin/env python3
"""
RaporOku — Yazarkasa Simülatörü

Gerçek bir yazarkasa gibi seri port üzerinden Z raporu gönderir.
Agent veya ESP32'yi test etmek için kullanılır.

Kullanım:
    python simulator.py                    # Sanal seri port oluştur (macOS/Linux)
    python simulator.py --port COM5        # Windows: belirli porta gönder
    python simulator.py --direct           # Seri port yerine doğrudan API'ye gönder
    python simulator.py --brand hugin      # Belirli marka formatı
    python simulator.py --loop 30          # Her 30 saniyede bir Z raporu gönder
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime

# ─── Z Raporu Şablonları (Gerçekçi) ──────────────

BRANDS = {
    "hugin": {
        "header": [
            "================================",
            "    {firma_adi}",
            "    {adres}",
            "    {sehir}",
            "    VKN: {vkn}",
            "    {vergi_dairesi} V.D.",
            "================================",
            "         Z RAPORU",
            "Z NO         : {z_no}",
            "TARİH        : {tarih}",
            "SAAT         : {saat}",
            "KASA NO      : 01",
            "KASİYER      : KASİYER 1",
            "--------------------------------",
        ],
        "dept_header": "DEPARTMAN SATIŞLARI",
        "dept_format": "  DEPT {no} {isim:<12s}  *{tutar}",
        "separator": "--------------------------------",
        "footer": [
            "EKÜ NO: 0001",
            "================================",
            "MF: {mali_hafiza}",
            "CİHAZ SERİ: {cihaz_seri}",
            "================================",
        ],
    },
    "ingenico": {
        "header": [
            "****************************************",
            "*    {firma_adi}",
            "*    {adres}",
            "*    {sehir}",
            "*    VKN: {vkn}",
            "*    {vergi_dairesi} V.D.",
            "****************************************",
            "        MALİ RAPOR",
            "        Z RAPOR NO: {z_no}",
            "        TARİH: {tarih}",
            "        SAAT: {saat}",
            "        TERMİNAL NO: {cihaz_seri}",
            "----------------------------------------",
        ],
        "dept_header": "SATIŞ BİLGİLERİ",
        "dept_format": "  DEPT {no} {isim:<16s}  *{tutar}",
        "separator": "----------------------------------------",
        "footer": [
            "EKU NO: 0001",
            "MH: {mali_hafiza}",
            "****************************************",
        ],
    },
    "beko": {
        "header": [
            "------------------------------",
            "{firma_adi}",
            "{adres}",
            "{sehir}",
            "VKN: {vkn}",
            "{vergi_dairesi} V.D.",
            "------------------------------",
            "GÜN SONU RAPORU",
            "Z RAPORU NO: {z_no}",
            "TARİH : {tarih}",
            "SAAT  : {saat}",
            "KASA SERİ NO: {cihaz_seri}",
            "------------------------------",
        ],
        "dept_header": "SATIŞ TOPLAMI",
        "dept_format": " DP{no} {isim:<12s}  *{tutar}",
        "separator": "------------------------------",
        "footer": [
            "MALİ HAFIZA: {mali_hafiza}",
            "------------------------------",
        ],
    },
}

FIRMA_ADLARI = [
    ("Yıldız Market", "Cumhuriyet Mah. 123. Sok. No:5", "Çankaya/ANKARA", "Çankaya"),
    ("Güneş Kafe", "İstiklal Cad. No:42", "Beyoğlu/İSTANBUL", "Beyoğlu"),
    ("Deniz Restaurant", "Sahil Yolu No:15", "Kadıköy/İSTANBUL", "Kadıköy"),
    ("Anadolu Eczane", "Atatürk Bulvarı No:88", "Çankaya/ANKARA", "Çankaya"),
    ("Moda Giyim", "Bağdat Cad. No:221", "Kadıköy/İSTANBUL", "Kadıköy"),
    ("Lezzet Lokantası", "Konya Cad. No:7", "Fatih/İSTANBUL", "Fatih"),
]

DEPARTMANLAR = {
    "market": [("GIDA", 8), ("İÇECEK", 10), ("TEMİZLİK", 20), ("KIRTASİYE", 20), ("DİĞER", 20)],
    "kafe": [("SICAK İÇECEK", 10), ("SOĞUK İÇECEK", 10), ("YEMEK", 8), ("TATLI", 8), ("DİĞER", 20)],
    "restaurant": [("YEMEK", 8), ("İÇECEK", 10), ("TATLI", 8), ("ALKOL", 20), ("SERVİS", 20)],
    "eczane": [("İLAÇ", 8), ("KOZMETİK", 20), ("BAKIM", 20), ("DİĞER", 20)],
    "giyim": [("KADIN", 20), ("ERKEK", 20), ("ÇOCUK", 20), ("AKSESUAR", 20)],
}


def format_tutar(val):
    """1234.56 → 1.234,56"""
    s = f"{val:,.2f}"
    # 1,234.56 → 1.234,56
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def generate_z_rapor(brand="hugin", z_no=None):
    """Rastgele ama gerçekçi Z raporu üret."""
    template = BRANDS.get(brand, BRANDS["hugin"])

    # Firma seç
    firma = random.choice(FIRMA_ADLARI)
    firma_adi, adres, sehir, vergi_dairesi = firma
    vkn = "".join([str(random.randint(0, 9)) for _ in range(10)])

    # Sektör belirle
    if "Market" in firma_adi:
        sektor = "market"
    elif "Kafe" in firma_adi:
        sektor = "kafe"
    elif "Restaurant" in firma_adi or "Lokanta" in firma_adi:
        sektor = "restaurant"
    elif "Eczane" in firma_adi:
        sektor = "eczane"
    elif "Giyim" in firma_adi:
        sektor = "giyim"
    else:
        sektor = "market"

    # Z raporu verileri
    if z_no is None:
        z_no = f"{random.randint(1, 999):04d}"
    tarih = datetime.now().strftime("%d/%m/%Y")
    saat = f"{random.randint(20, 23):02d}:{random.randint(0, 59):02d}"
    cihaz_seri = f"{'HG' if brand == 'hugin' else 'IG' if brand == 'ingenico' else 'BK'}-{random.randint(10000, 99999)}"
    mali_hafiza = "".join([random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(11)])

    # Departman satışları
    depts = DEPARTMANLAR[sektor]
    dept_satislar = []
    for isim, kdv_oran in depts:
        tutar = round(random.uniform(80, 6000), 2)
        dept_satislar.append({"isim": isim, "tutar": tutar, "kdv_oran": kdv_oran})

    brut_satis = sum(d["tutar"] for d in dept_satislar)
    indirim = round(random.uniform(0, brut_satis * 0.05), 2)
    iade = round(random.uniform(0, brut_satis * 0.02), 2) if random.random() > 0.5 else 0
    net_satis = round(brut_satis - indirim - iade, 2)

    # KDV hesapla
    kdv_gruplari = {}
    for d in dept_satislar:
        oran = d["kdv_oran"]
        matrah = round(d["tutar"] / (1 + oran / 100), 2)
        kdv = round(d["tutar"] - matrah, 2)
        if oran not in kdv_gruplari:
            kdv_gruplari[oran] = {"matrah": 0, "kdv": 0}
        kdv_gruplari[oran]["matrah"] += matrah
        kdv_gruplari[oran]["kdv"] += kdv

    toplam_kdv = round(sum(g["kdv"] for g in kdv_gruplari.values()), 2)

    # Ödeme ayrımı
    kart_oran = random.uniform(0.3, 0.7)
    kart = round(net_satis * kart_oran, 2)
    nakit = round(net_satis - kart, 2)

    fis_sayisi = random.randint(15, 200)
    gt = round(random.uniform(50000, 500000), 2)

    # ─── Rapor Oluştur ───
    lines = []
    ctx = {
        "firma_adi": firma_adi, "adres": adres, "sehir": sehir,
        "vkn": vkn, "vergi_dairesi": vergi_dairesi,
        "z_no": z_no, "tarih": tarih, "saat": saat,
        "cihaz_seri": cihaz_seri, "mali_hafiza": mali_hafiza,
    }

    # Header
    for line in template["header"]:
        lines.append(line.format(**ctx))

    # Departmanlar
    lines.append(template["dept_header"])
    for i, d in enumerate(dept_satislar, 1):
        lines.append(template["dept_format"].format(no=i, isim=d["isim"], tutar=format_tutar(d["tutar"])))

    lines.append(template["separator"])

    # Toplamlar
    lines.append(f"BRÜT SATIŞ            *{format_tutar(brut_satis)}")
    if indirim > 0:
        lines.append(f"İNDİRİM                *{format_tutar(indirim)}")
    if iade > 0:
        lines.append(f"İADE TOPLAM            *{format_tutar(iade)}")
        lines.append(f"İADE ADET                    {random.randint(1, 5)}")
    lines.append(f"İPTAL TOPLAM             *0,00")
    lines.append(f"NET SATIŞ             *{format_tutar(net_satis)}")
    lines.append(template["separator"])

    # KDV
    for oran in sorted(kdv_gruplari.keys()):
        g = kdv_gruplari[oran]
        lines.append(f"KDV %{oran:<2d} MATRAH: {format_tutar(round(g['matrah'], 2))}  KDV: {format_tutar(round(g['kdv'], 2))}")
    lines.append(f"KDV TOPLAM             *{format_tutar(toplam_kdv)}")
    lines.append(template["separator"])

    # Ödeme
    lines.append(f"NAKİT               *{format_tutar(nakit)}")
    lines.append(f"KREDİ KARTI           *{format_tutar(kart)}")
    lines.append(f"TOPLAM              *{format_tutar(net_satis)}")
    lines.append(template["separator"])

    # Fiş & GT
    lines.append(f"FİŞ SAYISI               {fis_sayisi}")
    lines.append(f"GT:              *{format_tutar(gt)}")

    # Footer
    for line in template["footer"]:
        lines.append(line.format(**ctx))

    return "\n".join(lines)


# ─── Seri Port Simülatörü ────────────────────────

def create_virtual_serial():
    """macOS/Linux: socat ile sanal seri port çifti oluştur."""
    print("Sanal seri port oluşturuluyor (socat gerekli)...")
    print("  brew install socat  (macOS)")
    print("  apt install socat   (Linux)\n")

    proc = subprocess.Popen(
        ["socat", "-d", "-d", "pty,raw,echo=0", "pty,raw,echo=0"],
        stderr=subprocess.PIPE,
        text=True,
    )

    ports = []
    for line in proc.stderr:
        if "/dev/" in line:
            port = line.strip().split()[-1]
            ports.append(port)
            print(f"  Port: {port}")
        if len(ports) >= 2:
            break

    if len(ports) < 2:
        print("HATA: socat port oluşturamadı")
        sys.exit(1)

    print(f"\nSimülatör portu:  {ports[0]}  (yazarkasa gibi davranır)")
    print(f"Agent portu:      {ports[1]}  (agent bu portu dinler)")
    print(f"\nAgent'ı şu şekilde başlatın:")
    print(f"  python agent.py --port {ports[1]}\n")

    return ports[0], proc


def send_via_serial(port, text, baud=9600):
    """Seri porta Z raporu gönder (ESC/POS benzeri)."""
    try:
        import serial
    except ImportError:
        print("HATA: pyserial kurun → pip install pyserial")
        return False

    try:
        ser = serial.Serial(port, baud, timeout=1)
        # ESC/POS init
        ser.write(b'\x1b\x40')  # ESC @ (initialize)
        time.sleep(0.1)

        for line in text.split("\n"):
            ser.write(line.encode("cp857", errors="replace"))
            ser.write(b'\x0a')  # Line feed
            time.sleep(0.02)  # Gerçekçi yazıcı hızı

        # ESC/POS cut
        ser.write(b'\x1d\x56\x00')  # GS V (cut paper)
        ser.close()
        return True
    except Exception as e:
        print(f"Seri port hatası: {e}")
        return False


def send_via_api(text, device_key, api_url="https://raporoku.com"):
    """Seri port yerine doğrudan API'ye gönder."""
    try:
        import requests
    except ImportError:
        print("HATA: requests kurun → pip install requests")
        return False

    try:
        resp = requests.post(
            f"{api_url}/v1/firms/device/report",
            headers={"X-Device-Key": device_key, "Content-Type": "application/json"},
            json={"raw_text": text},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"  ✓ API: Z#{data.get('z_no', '?')} → {data.get('toplam', 0):,.2f} ₺")
            return True
        else:
            print(f"  ✗ API hatası: {resp.status_code} — {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"  ✗ API bağlantı hatası: {e}")
        return False


# ─── CLI ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="RaporOku Yazarkasa Simülatörü — Test için sahte Z raporu gönderir",
    )
    parser.add_argument("--brand", "-b", choices=list(BRANDS.keys()), default="hugin", help="Yazarkasa markası")
    parser.add_argument("--port", "-p", help="Seri port (COM5, /dev/ttyS0)")
    parser.add_argument("--virtual", "-v", action="store_true", help="Sanal seri port oluştur (socat)")
    parser.add_argument("--direct", "-d", action="store_true", help="Seri port yerine doğrudan API'ye gönder")
    parser.add_argument("--device-key", help="API cihaz anahtarı (--direct için)")
    parser.add_argument("--api-url", default="https://raporoku.com", help="API URL")
    parser.add_argument("--loop", "-l", type=int, help="Sürekli gönder (saniye aralığı)")
    parser.add_argument("--count", "-c", type=int, default=1, help="Kaç rapor gönderilsin")
    parser.add_argument("--print", action="store_true", help="Raporu terminale yazdır")

    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════╗")
    print("║  RaporOku Yazarkasa Simülatörü v1.0      ║")
    print("╚══════════════════════════════════════════╝")
    print()

    z_count = 0

    def send_one():
        nonlocal z_count
        z_count += 1
        brand = random.choice(list(BRANDS.keys())) if args.brand == "random" else args.brand
        z_no = f"{random.randint(1, 999):04d}"
        text = generate_z_rapor(brand=brand, z_no=z_no)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Z Raporu #{z_count} ({brand.upper()}, Z-{z_no})")

        if args.print:
            print()
            print(text)
            print()

        if args.direct:
            if not args.device_key:
                print("HATA: --device-key gerekli (--direct modunda)")
                sys.exit(1)
            send_via_api(text, args.device_key, args.api_url)
        elif args.port:
            ok = send_via_serial(args.port, text)
            if ok:
                print(f"  ✓ Seri porta gönderildi: {args.port}")
        else:
            # Sadece yazdır
            if not args.print:
                print(text)
            print(f"\n  Kullanım: --direct --device-key KEY  (API'ye gönder)")
            print(f"            --port COM5               (seri porta gönder)")
            print(f"            --virtual                 (sanal port oluştur)")

    if args.virtual:
        port, proc = create_virtual_serial()
        args.port = port
        try:
            while True:
                send_one()
                wait = args.loop or 30
                print(f"  Sonraki rapor {wait}s sonra...\n")
                time.sleep(wait)
        except KeyboardInterrupt:
            proc.terminate()
            print("\nSimülatör durduruluyor...")
        return

    if args.loop:
        try:
            while True:
                send_one()
                print(f"  Sonraki rapor {args.loop}s sonra...\n")
                time.sleep(args.loop)
        except KeyboardInterrupt:
            print("\nSimülatör durduruluyor...")
        return

    for _ in range(args.count):
        send_one()
        if args.count > 1:
            time.sleep(1)


if __name__ == "__main__":
    main()
