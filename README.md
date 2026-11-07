# V1 – Eğim Alarmı: ESP32 ve Raspberry Pi

**İbrahim Kaan Dalğar · İleri Gömülü Sistemler · Vize Projesi**

ESP32, I²C ivme sensöründen yaklaşık 50 Hz hızında ölçüm alır ve UART üzerinden Raspberry Pi 4'e gönderir. Pi, mesajların checksum değerini doğrular, X-Z düzlemindeki eğimi hesaplar ve LED komutunu ESP32'ye geri gönderir. Açı 30°'yi aşınca alarm açılır; 25°'nin altına düşünce kapanır. Aradaki bölgede önceki durum korunur.

Telefonun erişim noktası, bilgisayardan Pi'ye SSH erişimi içindir. ESP32–Pi arasındaki ölçüm ve komut iletişimi kablolu UART üzerinden yapılır.

## Donanım ve bağlantılar

Kullanılan kart **klasik ESP32**'dir. Dersin ESP32-S3 şablonu bu karta uyarlanmıştır.

| İşlev | ESP32 | Karşı uç |
|---|---|---|
| Sensör beslemesi | 3V3 / GND | Modül VCC / GND |
| I²C veri | GPIO21 | Modül SDA |
| I²C saat | GPIO22 | Modül SCL |
| UART gönderim | GPIO17 / TX2 | Pi GPIO15 / RXD, fiziksel pin 10 |
| UART alım | GPIO18 | Pi GPIO14 / TXD, fiziksel pin 8 |
| Ortak toprak | GND | Pi fiziksel pin 6 |
| Alarm LED'i | GPIO4 | 330 Ω direnç → LED uzun bacağı; kısa bacak → GND |

UART: **115200 baud, 8 veri biti, parite yok, 1 dur biti**. Pi'de `/dev/serial0` kullanılır. ESP32 ve Pi ayrı USB kaynaklarından beslenir; ortak GND bağlanır, kartların 3V3/5V besleme hatları birbirine bağlanmaz. Bağlantı değişiklikleri güç kapalıyken yapılır.

### Sensör kimliği ve gerçek veri

Modül üzerinde MPU-6050/SY-104 yazmasına rağmen `WHO_AM_I` değeri **0x72** okunmuştur. MPU-6050 için beklenen değer 0x68'dir. Kesin sensör modeli doğrulanmamıştır. I²C cihaz adresinin 0x68 olması ile WHO_AM_I register değerinin aynı olması gerekmez.

Son firmware beklenmeyen kimliği konsolda uyarır. Başlatma başarılı olduğunda `GERCEK OLCUM` mesajı görülür. Orijinal şablondaki sensör bulunamayınca sentetik veri üretme davranışı kaldırılmıştır: başlangıçta sensör hazır değilse `ERR,SENSOR_YOK` gönderilir, IMU verisi üretilmez. Bağlantı düzeltildikten sonra kart yeniden başlatılır.

## Dosyalar

| Konum | İçerik |
|---|---|
| `esp32_vize/main/main.c` | Sensör okuma, UART protokolü, LED/HIZ komutları ve hata kontrolü |
| `esp32_vize/sdkconfig` | Kullanılan ESP-IDF yapılandırması |
| `pi/protokol.py` | Checksum, mesaj kodlama/çözme ve birim dönüşümleri |
| `pi/alici.py` | UART alıcısı ve elle komut testi |
| `pi/egim_alarmi.py` | Filtre, histerezis, LED/ACK takibi ve CSV kaydı |
| `pi/canli_grafik.py` | Şablonun grafik aracı |
| `pi/sim_esp32.py` | Şablonun ayrı yazılım simülatörü; fiziksel ölçüm kanıtı değildir |
| `olcum/` | Ölçüm/olay CSV'leri, fotoğraflar ve terminal ekran görüntüleri |
| `rapor/` | Vize raporu |
| `BENIOKU.md` | Dersin orijinal şablon açıklaması; S3'e ait eski pin/hedef bilgileri içerir |

Bu donanım için kurulumda aşağıdaki **ESP32** hedefi ve GPIO21/22 bağlantıları kullanılmalıdır.

## ESP32'yi derleme ve yükleme

Test ortamı: Windows, ESP-IDF v6.1, kart portu COM7. ESP-IDF ortamı etkin terminalde proje kökünden:

```powershell
cd esp32_vize
idf.py build
idf.py -p COM7 flash monitor
```

Port farklıysa COM7 değiştirilir. Depodaki `sdkconfig` ESP32 hedefini içerir. Temiz bir yapılandırma oluşturuluyorsa önce `idf.py set-target esp32` kullanılır; bu komut mevcut yapılandırmayı yeniden oluşturabileceğinden rutin derlemede gerekli değildir.

Konsolda sensör kimliği, gerçek ölçüm mesajı ve hareketle değişen HAM değerleri kontrol edilir. Monitörden çıkış: **Ctrl+]**. Derleme çıktıları `build/` altında üretilir ve Git'e dahil edilmez.

## Raspberry Pi kurulumu

Pi üzerinde bir kez:

```bash
sudo raspi-config
```

Serial Port ayarında **seri giriş kabuğu: No**, **seri donanım: Yes** seçilir. Ardından:

```bash
sudo reboot
```

Tekrar SSH ile bağlanıp:

```bash
sudo apt update
sudo apt install python3-serial
ls -l /dev/serial0
python3 -c "import serial; print(serial.__version__)"
mkdir -p ~/vize_egim_alarmi/pi ~/vize_egim_alarmi/olcum
```

Testte `/dev/serial0 -> ttyS0` ve pyserial 3.5 görülmüştür. Grafik aracı kullanılacaksa ayrıca `python3-matplotlib` gerekir. Seri porta erişim izni hatasında kullanıcının `dialout` grubu üyeliği kontrol edilir.

### Dosyaları bilgisayardan Pi'ye gönderme

Aşağıdaki komut **Windows PowerShell'de**, proje kökünden çalıştırılır:

```powershell
scp ".\pi\*.py" kaan@kaan-rpi.local:/home/kaan/vize_egim_alarmi/pi/
```

Kullanıcı adı, hostname ve yol kendi Pi kurulumuna göre değiştirilir. `.local` çözümlenmiyorsa Pi'nin güncel yerel IP adresi kullanılır.

## Alarmı çalıştırma

**Pi'nin SSH terminalinde:**

```bash
cd ~/vize_egim_alarmi/pi
python3 egim_alarmi.py --sure 30 --csv ../olcum/demo01.csv --olay ../olcum/demo_olay01.csv
```

Başlangıçta sensör sabit tutulur. Pozitif açı yönünde yavaşça eğilerek 30° üzeri, ardından 25–30° aralığı ve 25° altı gözlenir. `--sure` verilmezse program **Ctrl+C** ile durdurulur. Çıkışta LED=0 gönderilir ve kapanış ACK'si beklenir.

Her denemede yeni dosya adı seçilir; program mevcut CSV'nin üzerine yazmaz. Aynı seri portu kullanan `alici.py`, alarm programı veya grafik aracı eşzamanlı çalıştırılmaz.

| Seçenek | Varsayılan / anlamı |
|---|---|
| `--port` | `/dev/serial0` |
| `--baud` | `115200` |
| `--ac` | `30`, açılma eşiği |
| `--kapat` | `25`, kapanma eşiği |
| `--pencere` | `10`, filtre örnek sayısı |
| `--mutlak` | Verilirse pozitif ve negatif eğim izlenir |
| `--sure` | Saniye; 0 veya verilmemesi Ctrl+C'ye kadar çalışma |
| `--csv` | Ölçüm CSV yolu |
| `--olay` | Komut, alarm, ACK ve hata günlüğü yolu |

Varsayılan mod **pozitif X-Z eğimidir**; yalnızca negatif yönde eğmek alarmı açmaz.

### Algoritma ve hata davranışı

Her geçerli örnek için `atan2(ax, az)` hesaplanır. Son 10 açının dairesel ortalaması kullanılır; ilk karar pencere dolunca verilir. 50 Hz'de pencere yaklaşık 0,2 saniyelik veriyi kapsar.

- Alarm kapalıyken filtrelenmiş açı **>30°** ise açılır.
- Alarm açıkken açı **<25°** ise kapanır.
- 25–30° aralığında önceki durum korunur.
- Başlangıç/kapanış dışında LED komutu durum değişiminde gönderilir.
- 3 saniye geçerli IMU gelmezse, 2 saniye içinde beklenen ACK alınmazsa veya ESP32 `ERR` gönderirse program hata ile durur ve LED'i söndürmeyi dener.

İletişim kesilirse LED'in sönmesi garanti edilemez; kapanış ACK'si yoksa durum doğrulanamadığı yazdırılır. Eğimin ivmeden hesaplanması sabit/yavaş hareket için uygundur; doğrusal ivme sonucu etkiler.

## UART protokolü

Satır biçimi: `$GOVDE*HH\r\n`. `HH`, `$` ile `*` arasındaki ASCII karakterlerin XOR değerinin iki haneli onaltılık gösterimidir.

| Yön | Mesaj gövdesi | Anlam |
|---|---|---|
| ESP32 → Pi | `IMU,t,ax,ay,az,gx,gy,gz` | t: ms; diğerleri ham sensör değerleri |
| Pi → ESP32 | `LED,0` / `LED,1` | LED kapat / aç |
| Pi → ESP32 | `HIZ,n` | 1–100 Hz aralığında hız isteği |
| ESP32 → Pi | `ACK,LED,n` / `ACK,HIZ,n` | Komut onayı |
| ESP32 → Pi | `ERR,neden` | SENSOR_YOK, I2C, BICIM, CHECKSUM veya KOMUT |

Örnek tam komutlar: `$LED,1*50` ve `$LED,0*51` (sonlarına CR/LF eklenir). Ham ivme dönüşümünde 16384 LSB/g, jiroskopta 131 LSB/(°/s) kullanılır; bunlar yapılandırılan MPU-6050 ölçeklerine dayanır ve kesin modeli doğrulanmamış modül için varsayımdır. HIZ komutunda tam sayı milisaniye periyodu kullanıldığından her istek tam karşılık gelen frekansı üretmeyebilir; deneyler varsayılan 50 Hz'de yapılmıştır.

## Ölçümler ve sonuçlar

Raporda aşağıdaki sabit konum kayıtları kullanılmıştır:

| Yaklaşık referans | Dosya | Ortalama filtrelenmiş açı | Örnek std. sapma | Örnek |
|---|---|---:|---:|---:|
| 0° | `aci_0derece_02.csv` | -2,196° | 0,025° | 501 |
| 45° | `aci_45derece_05.csv` | 45,435° | 0,028° | 501 |
| 90° | `aci_90derece_02.csv` | 82,854° | 0,029° | 501 |

Dosyalar `olcum/` altındadır. Referanslar masa, katlanmış kare kâğıt/karton ve dik kitapla hazırlanmıştır; kalibre açı standartları değildir. Önceki denemeler de korunmuştur. Seçilen son yerleşimler bağımsız tekrarlı doğruluk deneyi olarak sunulmaz. Özellikle 90° referansındaki yaklaşık 7,15° farkın sensör ve yerleşim kaynakları bu deneyle ayrıştırılamaz. Küçük standart sapma, yüksek mutlak doğruluk anlamına gelmez.

### Histerezis karşılaştırması

`histerezis_test03.csv` ve `histerezis_olay03.csv`: 1615 geçerli örnek, 0 hatalı satır. Aynı filtrelenmiş kayıt üzerinde başlangıç durumu kapalı ve ilk 9 örnekte karar verilmeme koşulları korunarak:

| Kural | Alarm durum geçişi |
|---|---:|
| >30° aç / <25° kapat | 5; gerçek olay günlüğüyle uyumlu |
| >30° aç / <30° kapat | 20; kayıt üzerinde hesaplanan karşılaştırma |

Bu kayıt için geçiş sayısı %75 azalmıştır. Histerezissiz sonuç ikinci fiziksel LED deneyi değildir. Başlangıç ve program kapanışındaki LED=0 komutları alarm geçişine dahil değildir.

Son firmware ile `son_test01.csv` / `son_test_olay01.csv` kontrolünün terminal özetinde 30 saniyede 1501 örnek, 0 hatalı satır ve 2 alarm geçişi görülmüştür. Açma, kapatma ve kapanış komutları onaylanmıştır. Terminal kanıtı: `olcum/17_son_sistem_testi.png`.

## Rapor, gösterim ve sürüm geçmişi

- [Vize raporu (PDF)](rapor/Vize_Egim_Alarmi_Raporu.pdf)
- İlk commit dersin değiştirilmemiş şablonunu, sonraki commit'ler geliştirilen kodu ve deney kayıtlarını içerir. Git geçmişi deneylerin tamamlanmasından sonra oluşturulmuştur.
- Orijinal şablona göre başlıca ekler: klasik ESP32 pin/hedef uyarlaması, sensör başlatma kontrolleri ve kimlik uyarısı, otomatik sentetik verinin kaldırılması, Pi'de dairesel filtre ve histerezis, LED/ACK ve zaman aşımı takibi, ayrı ölçüm/olay kayıtları.

Kod geliştirme, hata ayıklama, ölçüm analizi ve dokümantasyonda ChatGPT'den yararlanılmıştır. Fiziksel kurulum ve ölçümler öğrenci tarafından gerçekleştirilmiştir.
