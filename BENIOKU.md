# Vize şablonu: ESP32-S3 ↔ Raspberry Pi

## Bağlantı
| ESP32-S3-DevKitC-1 | Raspberry Pi 4 |
|---|---|
| GPIO17 (TX) | GPIO15 / RXD (pin 10) |
| GPIO18 (RX) | GPIO14 / TXD (pin 8) |
| GND | GND (pin 6) |

MPU-6050: VCC → 3V3, GND → GND, SDA → GPIO8, SCL → GPIO9 (ESP32). LED: GPIO4 → 330 Ω → LED → GND.

## ESP32
    cd esp32_vize
    idf.py set-target esp32s3
    idf.py build
    idf.py -p COM5 flash monitor

## Raspberry Pi (bir kez)
    sudo raspi-config        # 3 Interface Options > I6 Serial Port: login shell = No, hardware = Yes
    sudo reboot
    sudo apt install python3-serial python3-matplotlib

## Raspberry Pi (çalıştırma)
    python3 alici.py                     # /dev/serial0
    python3 canli_grafik.py              # masaüstünde grafik
    python3 sim_esp32.py                 # donanımsız deneme; yazdığı portu alici.py --port ile verin

Protokol: `$IMU,t,ax,ay,az,gx,gy,gz*HH`, komutlar `$LED,0|1*HH`, `$HIZ,1..100*HH`.
