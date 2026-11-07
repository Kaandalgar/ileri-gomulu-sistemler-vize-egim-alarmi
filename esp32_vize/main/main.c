/*
 * İleri Gömülü Sistemler - Vize şablonu, ESP32-S3 tarafı
 *
 * MPU-6050'den belirli bir hızda ölçüm alır, UART1 üzerinden metin satırı
 * olarak Raspberry Pi'ye gönderir ve Pi'den gelen komutları işler.
 * Sensör bulunamazsa sentetik veri gönderir; böylece haberleşme sensörsüz
 * de denenebilir.
 *
 *   ESP32 -> Pi : $IMU,<zaman_ms>,<ax>,<ay>,<az>,<gx>,<gy>,<gz>*HH
 *   Pi -> ESP32 : $LED,<0|1>*HH      $HIZ,<1..100>*HH
 *   ESP32 -> Pi : $ACK,<komut>,<deger>*HH   veya   $ERR,<neden>*HH
 *
 *   HH: '$' ile '*' arasındaki karakterlerin XOR'u (onaltılık, 2 hane)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <inttypes.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/i2c_master.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"

/* ---- Bağlantılar -------------------------------------------------- */
#define UART_NO        UART_NUM_1
#define PIN_TX         17          /* -> Raspberry Pi GPIO15 (RXD, pin 10) */
#define PIN_RX         18          /* <- Raspberry Pi GPIO14 (TXD, pin 8)  */
#define BAUD           115200
#define PIN_SDA        8
#define PIN_SCL        9
#define PIN_LED        4
#define MPU_ADR        0x68

/* ---- MPU-6050 registerları --------------------------------------- */
#define MPU_PWR_MGMT_1   0x6B
#define MPU_CONFIG       0x1A
#define MPU_GYRO_CONFIG  0x1B
#define MPU_ACCEL_CONFIG 0x1C
#define MPU_ACCEL_XOUT_H 0x3B
#define MPU_WHO_AM_I     0x75

static const char *TAG = "vize";
static i2c_master_dev_handle_t mpu;
static bool sensor_var = false;
static volatile uint32_t periyot_ms = 20;          /* 50 Hz */

/* '$' ile '*' arasındaki karakterlerin XOR'u */
static uint8_t checksum(const char *s)
{
    uint8_t c = 0;
    while (*s) {
        c ^= (uint8_t)*s++;
    }
    return c;
}

/* govde -> "$govde*HH\r\n" */
static void satir_gonder(const char *govde)
{
    char buf[128];
    int n = snprintf(buf, sizeof(buf), "$%s*%02X\r\n", govde, checksum(govde));
    uart_write_bytes(UART_NO, buf, n);
}

static esp_err_t mpu_yaz(uint8_t reg, uint8_t deger)
{
    uint8_t b[2] = { reg, deger };
    return i2c_master_transmit(mpu, b, 2, 100);
}

static esp_err_t mpu_baslat(void)
{
    uint8_t reg = MPU_WHO_AM_I, kimlik = 0;
    esp_err_t e = i2c_master_transmit_receive(mpu, &reg, 1, &kimlik, 1, 100);
    if (e != ESP_OK) return e;
    ESP_LOGI(TAG, "WHO_AM_I = 0x%02X", kimlik);
    mpu_yaz(MPU_PWR_MGMT_1, 0x01);     /* uykudan çık, saat: X ekseni PLL */
    mpu_yaz(MPU_CONFIG, 0x03);         /* sayısal alçak geçiren süzgeç ~44 Hz */
    mpu_yaz(MPU_GYRO_CONFIG, 0x00);    /* ±250 °/s  -> 131 LSB/(°/s) */
    return mpu_yaz(MPU_ACCEL_CONFIG, 0x00);   /* ±2 g -> 16384 LSB/g */
}

/* v: ax, ay, az, gx, gy, gz (ham değerler) */
static esp_err_t mpu_oku(int16_t v[6])
{
    uint8_t reg = MPU_ACCEL_XOUT_H, d[14];
    esp_err_t e = i2c_master_transmit_receive(mpu, &reg, 1, d, sizeof(d), 100);
    if (e != ESP_OK) return e;
    for (int i = 0; i < 3; i++) {
        v[i]     = (int16_t)((d[2 * i] << 8) | d[2 * i + 1]);       /* ivme */
        v[i + 3] = (int16_t)((d[8 + 2 * i] << 8) | d[9 + 2 * i]);   /* dönü */
    }
    return ESP_OK;                     /* d[6], d[7]: sıcaklık, kullanılmıyor */
}

static void sentetik_veri(int16_t v[6], uint32_t sayac)
{
    float t = sayac * (periyot_ms / 1000.0f);
    v[0] = (int16_t)(4000.0f * sinf(2.0f * (float)M_PI * 1.0f * t));
    v[1] = (int16_t)(2000.0f * cosf(2.0f * (float)M_PI * 0.5f * t));
    v[2] = 16384;                      /* 1 g */
    v[3] = v[4] = v[5] = 0;
}

static void olcum_gorevi(void *arg)
{
    TickType_t son = xTaskGetTickCount();
    uint32_t sayac = 0;
    int16_t v[6];
    char govde[96];

    while (1) {
        bool gecerli = true;
        if (sensor_var) {
            if (mpu_oku(v) != ESP_OK) {
                satir_gonder("ERR,I2C");
                gecerli = false;
            }
        } else {
            sentetik_veri(v, sayac);
        }
        if (gecerli) {
            snprintf(govde, sizeof(govde), "IMU,%" PRIu32 ",%d,%d,%d,%d,%d,%d",
                     (uint32_t)(esp_timer_get_time() / 1000),
                     v[0], v[1], v[2], v[3], v[4], v[5]);
            satir_gonder(govde);
        }
        sayac++;
        xTaskDelayUntil(&son, pdMS_TO_TICKS(periyot_ms));
    }
}

/* satir: "$KOMUT,DEGER*HH" (satır sonu karakterleri olmadan) */
static void komut_isle(char *satir)
{
    char *yildiz = strrchr(satir, '*');
    if (satir[0] != '$' || yildiz == NULL) {
        satir_gonder("ERR,BICIM");
        return;
    }
    *yildiz = '\0';
    char *govde = satir + 1;
    if (checksum(govde) != (uint8_t)strtoul(yildiz + 1, NULL, 16)) {
        satir_gonder("ERR,CHECKSUM");
        return;
    }
    char *virgul = strchr(govde, ',');
    if (virgul == NULL) {
        satir_gonder("ERR,BICIM");
        return;
    }
    *virgul = '\0';
    const char *komut = govde;
    int deger = atoi(virgul + 1);

    char yanit[48];
    if (strcmp(komut, "LED") == 0 && (deger == 0 || deger == 1)) {
        gpio_set_level(PIN_LED, deger);
        snprintf(yanit, sizeof(yanit), "ACK,LED,%d", deger);
    } else if (strcmp(komut, "HIZ") == 0 && deger >= 1 && deger <= 100) {
        periyot_ms = 1000 / deger;
        snprintf(yanit, sizeof(yanit), "ACK,HIZ,%d", deger);
    } else {
        snprintf(yanit, sizeof(yanit), "ERR,KOMUT");
    }
    satir_gonder(yanit);
}

static void alma_gorevi(void *arg)
{
    char satir[64];
    size_t n = 0;
    uint8_t c;

    while (1) {
        if (uart_read_bytes(UART_NO, &c, 1, portMAX_DELAY) != 1) continue;
        if (c == '\r') continue;
        if (c == '\n') {
            satir[n] = '\0';
            if (n > 0) komut_isle(satir);
            n = 0;
        } else if (n < sizeof(satir) - 1) {
            satir[n++] = (char)c;
        } else {
            n = 0;                     /* çok uzun satır: at */
        }
    }
}

void app_main(void)
{
    /* LED */
    gpio_config_t led = { .pin_bit_mask = 1ULL << PIN_LED, .mode = GPIO_MODE_OUTPUT };
    ESP_ERROR_CHECK(gpio_config(&led));

    /* UART1: 115200 8N1 */
    uart_config_t ucfg = {
        .baud_rate  = BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(UART_NO, 1024, 1024, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_NO, &ucfg));
    ESP_ERROR_CHECK(uart_set_pin(UART_NO, PIN_TX, PIN_RX,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    /* I2C ve MPU-6050 */
    i2c_master_bus_config_t bcfg = {
        .i2c_port = -1,
        .sda_io_num = PIN_SDA,
        .scl_io_num = PIN_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
    };
    i2c_master_bus_handle_t bus;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bcfg, &bus));
    if (i2c_master_probe(bus, MPU_ADR, 50) == ESP_OK) {
        i2c_device_config_t dcfg = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address  = MPU_ADR,
            .scl_speed_hz    = 400000,
        };
        ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &dcfg, &mpu));
        sensor_var = (mpu_baslat() == ESP_OK);
    }
    ESP_LOGI(TAG, "%s", sensor_var ? "MPU-6050 bulundu" : "Sensör yok: sentetik veri gönderilecek");

    xTaskCreate(alma_gorevi, "alma", 4096, NULL, 6, NULL);
    xTaskCreate(olcum_gorevi, "olcum", 4096, NULL, 5, NULL);
}
