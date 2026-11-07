"""
ESP32 benzetici: donanım olmadan alici.py ve final betiklerini denemek için.

Sanal bir seri port (pty) açar, adını yazar ve ESP32 şablonuyla aynı
protokolle IMU satırları gönderir; LED ve HIZ komutlarını yanıtlar.
Yalnızca Linux / macOS / Raspberry Pi OS'ta çalışır.

Kullanım:
    python3 sim_esp32.py --hareket yuruyus
    (başka terminalde)  python3 alici.py --port /dev/pts/N
"""
import argparse
import math
import os
import random
import select
import time
import tty

from protokol import coz, kodla

HAREKETLER = ("durgun", "yuruyus", "sallama")


def ornek(hareket, t):
    """Basit sentetik hareket modeli; ham MPU-6050 değerleri döndürür."""
    g = 16384
    if hareket == "durgun":
        a = [0.0, 0.0, 1.0]
        w = [0.0, 0.0, 0.0]
    elif hareket == "yuruyus":
        a = [0.15 * math.sin(2 * math.pi * 2 * t), 0.05, 1.0 + 0.25 * math.sin(2 * math.pi * 2 * t)]
        w = [20 * math.sin(2 * math.pi * 1 * t), 5.0, 10 * math.cos(2 * math.pi * 1 * t)]
    else:  # sallama
        a = [1.2 * math.sin(2 * math.pi * 5 * t), 0.3 * math.cos(2 * math.pi * 5 * t), 1.0]
        w = [5.0, 150 * math.sin(2 * math.pi * 5 * t), 20.0]
    a = [int((v + random.gauss(0, 0.02)) * g) for v in a]
    w = [int((v + random.gauss(0, 1.0)) * 131) for v in w]
    return a + w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hareket", choices=HAREKETLER, default="durgun")
    ap.add_argument("--hz", type=int, default=50)
    a = ap.parse_args()

    ana, ikincil = os.openpty()
    tty.setraw(ikincil)               # yankı ve satır işleme kapalı
    print("Sanal port:", os.ttyname(ikincil), flush=True)
    hz, led, t0, tampon = a.hz, 0, time.monotonic(), b""
    sonraki = t0
    while True:
        bekle = max(0.0, sonraki - time.monotonic())
        hazir, _, _ = select.select([ana], [], [], bekle)
        if hazir:
            tampon += os.read(ana, 256)
            while b"\n" in tampon:
                satir, tampon = tampon.split(b"\n", 1)
                alanlar = coz(satir.decode("ascii", errors="replace"))
                if alanlar is None:
                    os.write(ana, kodla("ERR", "CHECKSUM"))
                elif alanlar[0] == "LED" and alanlar[1] in ("0", "1"):
                    led = int(alanlar[1])
                    os.write(ana, kodla("ACK", "LED", led))
                elif alanlar[0] == "HIZ" and alanlar[1].isdigit() and 1 <= int(alanlar[1]) <= 100:
                    hz = int(alanlar[1])
                    os.write(ana, kodla("ACK", "HIZ", hz))
                else:
                    os.write(ana, kodla("ERR", "KOMUT"))
        if time.monotonic() >= sonraki:
            t = time.monotonic() - t0
            os.write(ana, kodla("IMU", int(t * 1000), *ornek(a.hareket, t)))
            sonraki += 1.0 / hz


if __name__ == "__main__":
    main()
