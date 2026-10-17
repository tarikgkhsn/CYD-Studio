# cyd.py - NodeMCU v3 (ESP8266) donanim katmani.
#
# Modul adi tarihsel olarak `cyd` kaldi: projeler `import cyd` yaziyor ve
# ayni proje kodu her kartta calissin istiyoruz.
#
# Bu kartta ekran, dokunmatik, SD, BLE YOK. Olmayan seyler sessizce
# yanlis calismak yerine ACIK HATA firlatir - hangi kartta oldugunu
# bilmeden yazilmis bir proje boylece nerede takildigini soyler.
#
# ESP8266'da _thread yok: cekirdek bunu kendisi gorup solo moda duser
# (bkz. runtime.HAS_THREADS ve jobs.Manager.start).
from machine import Pin, ADC, PWM, SoftI2C, SoftSPI
import time

from runtime import (rota, rota_sil, rotalar, should_stop, sleep, job_name, claim_display,
                     release_display, display_owner, warn_shared_display,
                     dram, wifi, buton, Buton, yetenekler, _register_stop, _unregister_stop)

# Bu kartin sundugu ozellikler - panel ve cekirdek buna bakar.
# ESP8266: TEK CEKIRDEK, thread yok, ekran yok. Sade panel kullanilir.
OZELLIKLER = {
    'display': False,
    'touch': False,
    'sd': False,
    'rgb_led': True,       # GPIO2 dahili mavi LED (tek renk)
    # Kartta YERLESIK isik sensoru yok. A0 pini var ama uzerine LDR
    # baglaman gerekiyor; o yuzden burada kapali. Baglarsan True yap,
    # cyd.light() zaten A0'i okuyor.
    'light': False,
    'speaker': False,      # buzzer baglarsan cyd.beep() calisir
    'ble': False,          # ESP8266'da BLE donanimi yok
    'tls': False,          # yigin yetmez
    'wifi_config': True,   # frozen sonrasi RAM var: /api/wifi + /api/scan
    'docs': True,          # /api/docs -> /docs.md akitilir
    'lite_ui': True,
}

# ---------------------------------------------------------------- renkler
# Ekran yok ama projeler cyd.RED gibi sabitleri kullanabiliyor; import
# hatasi almasinlar diye tanimli birakiyoruz.
BLACK = 0
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
CYAN = 0x07FF
MAGENTA = 0xF81F
YELLOW = 0xFFE0
ORANGE = 0xFD20
PURPLE = 0x8010
GREY = 0x8410
NAVY = 0x000F


def color565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


# ------------------------------------------------------------- pin haritasi
# NodeMCU v3'te silkscreen "D" numaralari GPIO ile ayni DEGIL. Projelerde
# karisiklik olmasin diye ceviri tablosu:
D0 = 16
D1 = 5
D2 = 4
D3 = 0        # ayni zamanda BOOT/FLASH tusu
D4 = 2        # ayni zamanda dahili mavi LED (ters mantik)
D5 = 14
D6 = 12
D7 = 13
D8 = 15
RX = 3
TX = 1
A0 = 0        # tek analog giris, 0-1V (kartta bolucu ile 0-3.3V)

LED_PIN = 2   # dahili LED - dusukte yanar

_led = None
_adc = None
_pwm = {}


def pin(d):
    """D numarasini GPIO'ya cevirir: cyd.pin('D5') -> Pin(14)."""
    if isinstance(d, int):
        return Pin(d)
    ad = str(d).upper()
    esle = {'D0': D0, 'D1': D1, 'D2': D2, 'D3': D3, 'D4': D4,
            'D5': D5, 'D6': D6, 'D7': D7, 'D8': D8, 'RX': RX, 'TX': TX}
    if ad not in esle:
        raise ValueError('bilinmeyen pin: %s (D0..D8, RX, TX)' % d)
    return Pin(esle[ad])


# ------------------------------------------------------------------- led
def led(r=False, g=False, b=False):
    """Kartta tek renkli dahili LED var; herhangi bir renk istegi onu yakar.
    Ters mantik: 0 = yanik."""
    global _led
    if _led is None:
        _led = Pin(LED_PIN, Pin.OUT)
    _led.value(0 if (r or g or b) else 1)


def led_off():
    led(False, False, False)


# --------------------------------------------------------------- sensorler
def light():
    """A0'daki analog giris, 0..1023. Kartta bolucu oldugu icin 0-3.3V."""
    global _adc
    if _adc is None:
        _adc = ADC(A0)
    return _adc.read()


def beep(freq=1000, ms=100, volume=512, pin_no=D5):
    """Hoparlor yok ama D5'e buzzer baglarsan calisir."""
    p = _pwm.get(pin_no)
    if p is None:
        p = _pwm[pin_no] = PWM(Pin(pin_no))
    p.freq(int(freq))
    p.duty(int(volume))
    time.sleep_ms(int(ms))
    p.duty(0)


def tone_off(pin_no=D5):
    p = _pwm.get(pin_no)
    if p:
        p.duty(0)


# -------------------------------------------------------------- veri yollari
def i2c(sda=D2, scl=D1, freq=100000):
    """Harici I2C. Varsayilan D2/D1 - bu kartta yaygin kullanim."""
    return SoftI2C(sda=Pin(sda), scl=Pin(scl), freq=freq)


def spi(sck=D5, mosi=D7, miso=D6, baudrate=1000000):
    return SoftSPI(baudrate=baudrate, sck=Pin(sck), mosi=Pin(mosi),
                   miso=Pin(miso))


# ------------------------------------------- bu kartta olmayan donanimlar
def display(rotation=None, bgr=None):
    raise OSError('bu kartta ekran yok (NodeMCU v3). I2C OLED baglarsan '
                  'cyd.i2c() ile kendin surebilirsin.')


def touch(rotation=None):
    raise OSError('bu kartta dokunmatik ekran yok')


def set_display(rotation, bgr):
    raise OSError('bu kartta ekran yok')


def test_pattern(label=''):
    raise OSError('bu kartta ekran yok')


def backlight(on=True):
    pass


def mount_sd(path='/sd'):
    """SD yuvasi yok - projeler dahili flash'ta kalir."""
    return None


def splash(lines, rotation=None, color=None, bg=None, scale=1):
    """Ekran olmadigi icin acilis bilgisi seri porta ve loga gider."""
    for ln in lines:
        print('  ' + str(ln))
    return None
