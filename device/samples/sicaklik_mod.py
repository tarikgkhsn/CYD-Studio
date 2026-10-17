# SICAKLIK ESIGI -> LED  --  ASIL KOD (.mpy olarak karta gider)
#
# NEDEN AYRI MODUL
#
# jobs.py bir projeyi calistirirken kaynagi RAM'e okuyup compile() ediyor.
# ESP8266'nin derleyicisi kaynak boyutunun birkac katini istiyor ve bu
# kartta bos RAM 2,5-5 KB civarinda; 3 KB'lik bir proje bile
# MemoryError veriyordu (olculdu, iki kez).
#
# Cozum: derlemeyi karttan almak. Bu modul PC'de mpy-cross ile bytecode'a
# ceviriliyor, karta sicaklik_mod.mpy olarak gidiyor ve import edilirken
# HIC DERLENMIYOR. Projenin kendisi (sicaklik_led.py) sadece iki satir
# kaliyor - onu derlemek bedava.
#
# Yorumlar bytecode'a girmiyor, yani bu dosyayi istedigimiz kadar
# belgeleyebiliriz; karta tek bayt olarak gitmiyor.
#
#
# yaz PARAMETRESI NEDEN VAR
#
# jobs.py, projenin globallerine kendi log fonksiyonunu 'print' adiyla
# enjekte ediyor. Ayri bir modul o globalleri gormez - burada duz print
# kullansaydik cikti panele/kalici loga degil seri porta giderdi.
# Bu yuzden loader, kendi print'ini parametre olarak geciyor.
#
#
# KABLOLAMA
#     BME280 VCC ---- 3V3      (5V DEGIL)
#     BME280 GND ---- GND
#     BME280 SCL ---- D5  (GPIO14)
#     BME280 SDA ---- D6  (GPIO12)
#     LED        ---- D1  (GPIO5) + seri direnc
#
# LED DILI
#     3 kisa flas (200 ms) -> program basladi
#     3 uzun flas (600 ms) -> sensor bulunamadi
#     sabit yanik          -> sicaklik esigin ustunde
import cyd
import time
from machine import Pin

LED_PIN = 5            # D1
SCL_PIN = 14           # D5
SDA_PIN = 12           # D6

ESIK = 33.0            # bu sicakligin USTUNDE LED yanar
HISTEREZIS = 0.5       # bu kadar dusmeden sonmez - titremeyi keser
ARALIK = 1.0           # olcum araligi, saniye
RAPOR_SN = 1           # rutin olcum logu, saniye
                       # 1 sn ile 8 KB'lik kalici log ~3 dakika
                       # gecmis tutar; dolunca en eskiler duser,
                       # kayit durmaz.


def calistir(yaz=print):
    """Butun is burada. Modul seviyesinde durum tutmuyoruz ki proje
    ikinci kez calistirildiginda (modul sys.modules'te onbellekli kalir)
    temiz baslasin."""
    led = Pin(LED_PIN, Pin.OUT, value=0)

    def led_yak(ac):
        led.value(1 if ac else 0)

    def flas(kez, acik, kapali):
        for _ in range(kez):
            led_yak(True)
            if not cyd.sleep(acik):
                return False
            led_yak(False)
            if not cyd.sleep(kapali):
                return False
        return True

    yaz('acilis isareti - LED 3 kez yanip sonuyor')
    flas(3, 0.2, 0.2)

    # ---------------------------------------------------------- sensor
    yaz('BME280 araniyor - SCL=D5(GPIO%d) SDA=D6(GPIO%d)' % (SCL_PIN, SDA_PIN))
    try:
        i2c = cyd.i2c(sda=SDA_PIN, scl=SCL_PIN)
        bulunan = i2c.scan()
        yaz('I2C taramasi: %s' % [hex(a) for a in bulunan])
        import bme280
        sensor = bme280.BME280(i2c)
        yaz('BME280 hazir - adres 0x%02X, cip 0x%02X'
            % (sensor.adres, sensor.chip_id))
    except Exception as e:
        yaz('SENSOR BULUNAMADI: %s' % e)
        yaz('  - VCC 3V3 mi (5V degil)')
        yaz('  - SCL D5, SDA D6 mi')
        yaz('  - tarama bos donduyse kablo kopuk ya da ters')
        flas(3, 0.6, 0.3)
        led_yak(False)
        return

    yaz('esik %.1f C ustunde yanar, %.1f C altinda soner (histerezis %.1f)'
        % (ESIK, ESIK - HISTEREZIS, HISTEREZIS))
    yaz('olcum %.1f sn, rapor %d sn' % (ARALIK, RAPOR_SN))

    # ----------------------------------------------------------- dongu
    yanik = False
    son_rapor = time.ticks_ms()
    olcum = 0
    hata = 0

    try:
        while not cyd.should_stop():
            try:
                t, b, n = sensor.oku()
                hata = 0
            except Exception as e:
                hata += 1
                yaz('okuma hatasi (%d): %s' % (hata, e))
                if hata >= 5:
                    yaz('sensor cevap vermiyor - cikiliyor')
                    break
                if not cyd.sleep(ARALIK):
                    break
                continue

            olcum += 1

            # Histerezis: acilma ve kapanma esikleri AYRI. Tek esik olsaydi
            # sinirdaki sicaklik LED'i saniyede birkac kez yakip sondururdu.
            if not yanik and t >= ESIK:
                yanik = True
                led_yak(True)
                yaz('[%.2f C] ESIK ASILDI -> LED YANDI' % t)
            elif yanik and t <= ESIK - HISTEREZIS:
                yanik = False
                led_yak(False)
                yaz('[%.2f C] esik altina dusuldu -> LED sondu' % t)

            simdi = time.ticks_ms()
            if time.ticks_diff(simdi, son_rapor) >= RAPOR_SN * 1000:
                son_rapor = simdi
                durum = 'yanik' if yanik else 'sonuk'
                if n is None:
                    yaz('%.2f C   %.1f hPa   LED %s' % (t, b / 100, durum))
                else:
                    yaz('%.2f C   %%%.1f nem   %.1f hPa   LED %s'
                        % (t, n, b / 100, durum))

            if not cyd.sleep(ARALIK):
                break
    finally:
        led_yak(False)
        yaz('LED KAPATILDI - %d olcum yapildi' % olcum)
