"""
Vize şablonu: ESP32 ile Raspberry Pi arasındaki metin satırı protokolü.

Satır biçimi:  $GOVDE*HH\r\n
  GOVDE : virgülle ayrılmış alanlar, ilk alan mesaj türü (IMU, ACK, ERR, LED, HIZ)
  HH    : GOVDE karakterlerinin XOR'u, onaltılık iki hane
"""


def checksum(govde: str) -> int:
    c = 0
    for b in govde.encode("ascii"):
        c ^= b
    return c


def kodla(*alanlar) -> bytes:
    """kodla('LED', 1) -> b'$LED,1*50\\r\\n'"""
    govde = ",".join(str(a) for a in alanlar)
    return f"${govde}*{checksum(govde):02X}\r\n".encode("ascii")


def coz(satir: str):
    """'$IMU,...*HH' -> ['IMU', ...]. Biçim veya checksum hatalıysa None."""
    satir = satir.strip()
    if not satir.startswith("$") or "*" not in satir:
        return None
    govde, _, cs = satir[1:].rpartition("*")
    try:
        if int(cs, 16) != checksum(govde):
            return None
    except ValueError:
        return None
    return govde.split(",")


# MPU-6050 ham değerlerini fiziksel birime çevirme (±2 g, ±250 °/s)
IVME_LSB = 16384.0      # LSB / g
DONU_LSB = 131.0        # LSB / (°/s)


def imu_coz(alanlar):
    """['IMU', t, ax, ay, az, gx, gy, gz] -> (t_ms, [ax, ay, az] g, [gx, gy, gz] °/s)"""
    t = int(alanlar[1])
    ham = [int(x) for x in alanlar[2:8]]
    ivme = [v / IVME_LSB for v in ham[0:3]]
    donu = [v / DONU_LSB for v in ham[3:6]]
    return t, ivme, donu
