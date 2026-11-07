"""
Vize şablonu: Raspberry Pi tarafı alıcı.

ESP32'den gelen IMU satırlarını okur, doğrular, ekrana yazar ve CSV'ye kaydeder.
Klavyeden komut gönderilebilir:
    led 1 | led 0 | hiz 20 | q (çıkış)

Kullanım:
    python3 alici.py                         # /dev/serial0, 115200
    python3 alici.py --port /dev/ttyACM0     # ESP32 USB bağlantısı
    python3 alici.py --csv olcum.csv
"""
import argparse
import csv
import threading
import time

import serial

from protokol import coz, imu_coz, kodla


def komut_dongusu(ser, dur):
    while not dur.is_set():
        try:
            parca = input().strip().split()
        except EOFError:
            break
        if not parca:
            continue
        if parca[0] == "q":
            dur.set()
        elif parca[0] in ("led", "hiz") and len(parca) == 2 and parca[1].isdigit():
            ser.write(kodla(parca[0].upper(), parca[1]))
        else:
            print("komutlar: led 0|1, hiz <1..100>, q")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--csv", default="olcum.csv")
    ap.add_argument("--yazdir", type=int, default=25, help="her N örnekte bir ekrana yaz")
    a = ap.parse_args()

    ser = serial.Serial(a.port, a.baud, timeout=1)
    ser.reset_input_buffer()
    dur = threading.Event()
    threading.Thread(target=komut_dongusu, args=(ser, dur), daemon=True).start()

    sayac = {"imu": 0, "hata": 0, "diger": 0}
    t0 = time.monotonic()
    with open(a.csv, "w", newline="") as f:
        yaz = csv.writer(f)
        yaz.writerow(["pi_zaman_s", "esp_zaman_ms", "ax_g", "ay_g", "az_g",
                      "gx_dps", "gy_dps", "gz_dps"])
        print(f"{a.port} dinleniyor. Komutlar: led 0|1, hiz <Hz>, q")
        while not dur.is_set():
            satir = ser.readline().decode("ascii", errors="replace")
            if not satir:
                continue
            alanlar = coz(satir)
            if alanlar is None:
                sayac["hata"] += 1
                continue
            if alanlar[0] == "IMU" and len(alanlar) == 8:
                t, ivme, donu = imu_coz(alanlar)
                yaz.writerow([f"{time.monotonic() - t0:.3f}", t,
                              *[f"{v:.4f}" for v in ivme], *[f"{v:.2f}" for v in donu]])
                sayac["imu"] += 1
                if sayac["imu"] % a.yazdir == 0:
                    hiz = sayac["imu"] / (time.monotonic() - t0)
                    print(f"t={t:8d} ms  a=({ivme[0]:+.2f}, {ivme[1]:+.2f}, {ivme[2]:+.2f}) g"
                          f"  {hiz:5.1f} örnek/s  hatalı={sayac['hata']}")
            else:
                sayac["diger"] += 1
                print("ESP32:", ",".join(alanlar))
    ser.close()
    print("Özet:", sayac)


if __name__ == "__main__":
    main()
