"""
Vize şablonu: ivme verisinin canlı grafiği (Raspberry Pi masaüstünde).

Kullanım:  python3 canli_grafik.py --port /dev/serial0
"""
import argparse
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import serial

from protokol import coz, imu_coz

N = 250   # 50 Hz'te 5 saniye


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    a = ap.parse_args()
    ser = serial.Serial(a.port, a.baud, timeout=0)

    veri = [deque([0.0] * N, maxlen=N) for _ in range(3)]
    fig, ax = plt.subplots()
    cizgiler = [ax.plot(range(N), list(v), label=e)[0] for v, e in zip(veri, ("ax", "ay", "az"))]
    ax.set_ylim(-2.2, 2.2)
    ax.set_xlabel("örnek")
    ax.set_ylabel("ivme (g)")
    ax.legend(loc="upper right")
    tampon = b""

    def guncelle(_):
        nonlocal tampon
        tampon += ser.read(4096)
        *satirlar, tampon = tampon.split(b"\n")
        for s in satirlar:
            alanlar = coz(s.decode("ascii", errors="replace"))
            if alanlar and alanlar[0] == "IMU" and len(alanlar) == 8:
                _, ivme, _ = imu_coz(alanlar)
                for d, v in zip(veri, ivme):
                    d.append(v)
        for c, d in zip(cizgiler, veri):
            c.set_ydata(list(d))
        return cizgiler

    FuncAnimation(fig, guncelle, interval=50, blit=True, cache_frame_data=False)
    plt.show()


if __name__ == "__main__":
    main()
