"""V1: Pi'de egim alarmi. Hocanin protokol.py dosyasi ile ayni klasore koyun.

Ornek: python3 egim_alarmi.py --ac 30 --kapat 25
Pozitif X-Z egimi izlenir; iki yon icin --mutlak kullanilabilir.
Son 10 acinin dairesel ortalamasi, +/-180 derece gecisinde hatayi onler.
Olcumler ve komut/ACK olaylari ayri CSV dosyalarina yazilir.
Ctrl+C ile kapanir. Cikista LED'i sondurme denenir ve ACK sonucu kaydedilir.
Sensorden veri kesilirse veya ACK gelmezse hata ile durur.
Bu program, ESP32'nin gercek/sentetik veri ayrimini protokolden bilemez.
Deneyden once ESP32 konsolunda sensorun kullanildigini dogrulayin.
"""

import argparse
from collections import deque
import csv
from datetime import datetime
import math
from pathlib import Path
import sys
import time

import serial
from protokol import coz, imu_coz, kodla


class EgimKarari:
    """Pencere dolunca karar verir; esikler arasinda mevcut durumu korur."""

    def __init__(self, ac, kapat, pencere=10, mutlak=False):
        self.ac, self.kapat = ac, kapat
        self.acilar = deque(maxlen=pencere)
        self.mutlak = mutlak
        self.durum = 0

    def guncelle(self, ax, az):
        ham = math.atan2(ax, az)
        self.acilar.append(ham)
        filtre = math.degrees(math.atan2(
            sum(math.sin(x) for x in self.acilar),
            sum(math.cos(x) for x in self.acilar)))
        karar_acisi = abs(filtre) if self.mutlak else filtre
        if len(self.acilar) == self.acilar.maxlen:
            if self.durum == 0 and karar_acisi > self.ac:
                self.durum = 1
            elif self.durum == 1 and karar_acisi < self.kapat:
                self.durum = 0
        return math.degrees(ham), filtre, self.durum


def simdi():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--ac", type=float, default=30, help="LED acilma esigi, derece")
    ap.add_argument("--kapat", type=float, default=25, help="LED kapanma esigi, derece")
    ap.add_argument("--pencere", type=int, default=10)
    ap.add_argument("--mutlak", action="store_true", help="pozitif ve negatif egimi izle")
    ap.add_argument("--csv", default="../olcum/egim.csv")
    ap.add_argument("--olay", default="../olcum/alarm_olaylari.csv")
    ap.add_argument("--sure", type=float, default=0, help="saniye; 0: Ctrl+C'ye kadar")
    a = ap.parse_args()
    if not (math.isfinite(a.ac) and math.isfinite(a.kapat)
            and 0 <= a.kapat <= a.ac < 180):
        ap.error("0 <= kapat <= ac < 180 olmali; esit esikler histerezissiz deney icindir")
    if a.pencere < 1 or not math.isfinite(a.sure) or a.sure < 0:
        ap.error("pencere >= 1 ve sure >= 0 olmali")
    if Path(a.csv).resolve() == Path(a.olay).resolve():
        ap.error("olcum ve olay dosyalari farkli olmali")
    for isim in (a.csv, a.olay):
        Path(isim).parent.mkdir(parents=True, exist_ok=True)

    karar = EgimKarari(a.ac, a.kapat, a.pencere, a.mutlak)
    sayac = {"imu": 0, "hatali": 0, "ack": 0, "alarm_degisim": 0}
    kod = 0
    with serial.Serial(a.port, a.baud, timeout=0.1, write_timeout=1) as ser, \
            open(a.csv, "x", newline="", encoding="utf-8") as f, \
            open(a.olay, "x", newline="", encoding="utf-8") as olay_f:
        yaz, olay = csv.writer(f), csv.writer(olay_f)
        yaz.writerow(["zaman", "pi_zaman_s", "esp_zaman_ms", "ax_g", "ay_g", "az_g",
                      "ham_aci_deg", "filtre_aci_deg", "alarm_istenen", "led_onayli"])
        olay.writerow(["zaman", "olay", "led", "aci_deg", "ack_ms", "aciklama"])
        t0 = son_veri = time.monotonic()
        son_ekran = t0
        led = None
        bekleyen = None
        son_aci = None

        def kaydet(tur, deger, aciklama="", ack_ms=""):
            olay.writerow([simdi(), tur, deger,
                           "" if son_aci is None else f"{son_aci:.3f}", ack_ms, aciklama])
            olay_f.flush()

        def gonder(deger, neden):
            nonlocal bekleyen
            ser.write(kodla("LED", deger))
            bekleyen = (deger, time.monotonic())
            kaydet("KOMUT", deger, neden)
            print(f"KOMUT LED={deger} ({neden})", flush=True)

        ser.reset_input_buffer()
        gonder(0, "baslangic")
        print(f"Esikler: ac>{a.ac:g}, kapat<{a.kapat:g}; pencere={a.pencere}; "
              f"mod={'iki yon' if a.mutlak else 'pozitif X-Z'}. Ctrl+C: cikis.", flush=True)
        try:
            while a.sure == 0 or time.monotonic() - t0 < a.sure:
                now = time.monotonic()
                if now - son_veri > 3:
                    raise RuntimeError("3 saniyedir gecerli IMU verisi yok")
                if bekleyen and now - bekleyen[1] > 2:
                    raise RuntimeError(f"LED={bekleyen[0]} komutuna 2 saniyede ACK gelmedi")
                raw = ser.read_until(b"\n", size=256)
                if not raw:
                    continue
                alan = coz(raw.decode("ascii", errors="replace"))
                if alan is None:
                    sayac["hatali"] += 1
                    continue
                if alan[0] == "ACK" and len(alan) == 3 and alan[1] == "LED":
                    if bekleyen and alan[2] == str(bekleyen[0]):
                        led = bekleyen[0]
                        ms = (time.monotonic() - bekleyen[1]) * 1000
                        bekleyen = None
                        sayac["ack"] += 1
                        kaydet("ACK", led, ack_ms=f"{ms:.3f}")
                        print(f"ACK LED={led}, yanit={ms:.1f} ms", flush=True)
                    continue
                if alan[0] == "ERR":
                    raise RuntimeError("ESP32: " + ",".join(alan))
                if alan[0] != "IMU" or len(alan) != 8:
                    sayac["hatali"] += 1
                    continue
                try:
                    t, ivme, _ = imu_coz(alan)
                    if math.hypot(ivme[0], ivme[2]) < 0.05:
                        raise ValueError("X-Z egimi icin ivme yetersiz")
                except (ValueError, OverflowError):
                    sayac["hatali"] += 1
                    continue
                son_veri = time.monotonic()
                once = karar.durum
                ham, son_aci, istenen = karar.guncelle(ivme[0], ivme[2])
                sayac["imu"] += 1
                if once != istenen:
                    sayac["alarm_degisim"] += 1
                    kaydet("ALARM", istenen, "esik gecisi")
                if bekleyen is None and led != istenen:
                    gonder(istenen, "egim karari")
                yaz.writerow([simdi(), f"{son_veri-t0:.4f}", t,
                              *[f"{v:.5f}" for v in ivme], f"{ham:.3f}",
                              f"{son_aci:.3f}", istenen, "" if led is None else led])
                if son_veri - son_ekran >= 0.5:
                    print(f"aci={son_aci:+7.2f} derece  alarm={istenen}  "
                          f"LED={led}  {sayac['imu']/(son_veri-t0):.1f} ornek/s  "
                          f"hatali={sayac['hatali']}", flush=True)
                    son_ekran = son_veri
                    f.flush()
        except KeyboardInterrupt:
            print("\nKullanici kaydi durdurdu.", flush=True)
        except (RuntimeError, serial.SerialException) as e:
            kod = 1
            kaydet("HATA", "", str(e))
            print(f"HATA: {e}", file=sys.stderr, flush=True)
        finally:
            # Cikis sifirlama komutu, alarm degisim sayisina dahil edilmez.
            try:
                gonder(0, "kapanis")
                bitis = time.monotonic() + 2
                while time.monotonic() < bitis:
                    alan = coz(ser.read_until(b"\n", size=256).decode("ascii", errors="replace"))
                    if alan == ["ACK", "LED", "0"]:
                        kaydet("ACK", 0, "kapanis")
                        print("Kapanis ACK: LED=0", flush=True)
                        break
                else:
                    kod = 1
                    kaydet("HATA", "", "Kapanis ACK yok; LED durumu dogrulanamadi")
                    print("UYARI: Kapanis ACK yok; LED durumu dogrulanamadi", file=sys.stderr)
            except (serial.SerialException, OSError) as e:
                kod = 1
                kaydet("HATA", "", f"Kapanis: {e}")
            print("Ozet:", sayac, flush=True)
            print("Olcum:", a.csv, "Olaylar:", a.olay, flush=True)
    return kod


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, serial.SerialException) as hata:
        print(f"HATA: {hata}. Dosya varsa yeni --csv ve --olay adlari secin.", file=sys.stderr)
        sys.exit(1)
