# cyd.py - ESP32-2432S028R ("Cheap Yellow Display") donanim katmani.
#
# Karttan bagimsiz olan her sey (durdurma, DRAM, wifi, ekran sahipligi)
# runtime.py icinde; burada sadece bu kartin donanimi var. Her sey tembel
# olusturulur: ekrana hic dokunmayan bir proje SPI veri yolunu acmaz.
from machine import Pin, SPI, SoftSPI, ADC, PWM
import time

import ili9341
from ili9341 import (color565, BLACK, WHITE, RED, GREEN, BLUE, CYAN,
                     MAGENTA, YELLOW, ORANGE, PURPLE, GREY, NAVY)
from xpt2046 import XPT2046
from runtime import (rota, rota_sil, rotalar, should_stop, sleep, job_name, claim_display,
                     release_display, display_owner, warn_shared_display,
                     dram, wifi, buton, Buton, _register_stop, _unregister_stop)

# Bu kartin sundugu ozellikler. Sistem her kartta AYNI sistem; farklar
# veri olarak burada duruyor. Panel bu haritaya bakip desteklenmeyen
# dugmeleri gizler, cekirdek de davranisini buna gore ayarlar.
OZELLIKLER = {
    'display': True,
    'touch': True,
    'sd': True,
    'rgb_led': True,
    'light': True,
    'speaker': True,
    'ble': True,           # solo modda
    'tls': True,           # solo modda
    'wifi_config': True,
    'docs': True,
    'lite_ui': False,
}

# ---------------------------------------------------------------- pin map
TFT_SCK = 14
TFT_MOSI = 13
TFT_MISO = 12
TFT_CS = 15
TFT_DC = 2
TFT_BL = 21

TOUCH_SCK = 25
TOUCH_MOSI = 32
TOUCH_MISO = 39
TOUCH_CS = 33
TOUCH_IRQ = 36

SD_SCK = 18
SD_MOSI = 23
SD_MISO = 19
SD_CS = 5

LED_R = 4
LED_G = 16
LED_B = 17
LDR = 34
SPEAKER = 26

_display = None
_touch = None
_led = {}
_ldr = None
_spk = None


# ---------------------------------------------------------------- display
def display(rotation=None, bgr=None):
    """ILI9341'i tembel olusturur. Varsayilanlar kayitli ayarlardan gelir,
    boylece arayuzden sectigin yon yeniden baslatmada da kalir."""
    global _display
    warn_shared_display()
    if _display is None:
        if rotation is None or bgr is None:
            try:
                import settings
                if rotation is None:
                    rotation = settings.get('rotation', 0)
                if bgr is None:
                    bgr = settings.get('bgr', False)
            except Exception:
                rotation = 0 if rotation is None else rotation
                bgr = False if bgr is None else bgr
        spi = SPI(1, baudrate=40000000, polarity=0, phase=0,
                  sck=Pin(TFT_SCK), mosi=Pin(TFT_MOSI), miso=Pin(TFT_MISO))
        _display = ili9341.ILI9341(spi, cs=Pin(TFT_CS), dc=Pin(TFT_DC),
                                   bl=Pin(TFT_BL), rotation=rotation, bgr=bgr)
        _display.fill(BLACK)
    return _display


def set_display(rotation, bgr):
    """Yonu/renk duzenini aninda uygular, yeniden baslatma gerekmez."""
    d = display()
    d.rotation(int(rotation), bool(bgr))
    return d


def test_pattern(label=''):
    """Dort kenara degen cerceve + KIRMIZI kare. Cerceve kesiliyorsa yon,
    kare mavi gorunuyorsa BGR biti yanlis."""
    d = display()
    w, h = d.width, d.height
    d.fill(BLACK)
    for i in range(3):
        d.rect(i, i, w - 2 * i, h - 2 * i, WHITE)
    d.fill_rect(w - 74, h - 74, 60, 60, RED)
    d.text('KARE KIRMIZI MI?', 10, 16, WHITE, BLACK, 2)
    d.text('cerceve 4 kenarda mi?', 10, 42, GREY, BLACK, 1)
    if label:
        d.text(label, 10, 62, YELLOW, BLACK, 2)
    return d


def touch(rotation=None):
    """XPT2046'yi ekran yonuyle eslesecek sekilde olusturur."""
    global _touch
    if _touch is None:
        d = display()
        if rotation is None:
            rotation = d._rot
        spi = SoftSPI(baudrate=1000000, polarity=0, phase=0,
                      sck=Pin(TOUCH_SCK), mosi=Pin(TOUCH_MOSI),
                      miso=Pin(TOUCH_MISO))
        _touch = XPT2046(spi, cs=Pin(TOUCH_CS), irq=Pin(TOUCH_IRQ, Pin.IN),
                         width=d.width, height=d.height, rotation=rotation)
    return _touch


def backlight(on=True):
    display().backlight(on)


# ---------------------------------------------------------------- rgb led
def led(r=False, g=False, b=False):
    """Kart uzerindeki RGB LED (ortak anot - dusukte yanar)."""
    for name, pin, state in (('r', LED_R, r), ('g', LED_G, g), ('b', LED_B, b)):
        p = _led.get(name)
        if p is None:
            p = _led[name] = Pin(pin, Pin.OUT)
        p.value(0 if state else 1)


def led_off():
    led(False, False, False)


# ---------------------------------------------------------------- sensors
def light():
    """LDR ile ortam isigi, 0..4095 (buyudukce karanlik)."""
    global _ldr
    if _ldr is None:
        _ldr = ADC(Pin(LDR))
        _ldr.atten(ADC.ATTN_11DB)
    return _ldr.read()


def beep(freq=1000, ms=100, volume=512):
    global _spk
    if _spk is None:
        _spk = PWM(Pin(SPEAKER))
    _spk.freq(int(freq))
    _spk.duty(int(volume))
    time.sleep_ms(int(ms))
    _spk.duty(0)


def tone_off():
    if _spk:
        _spk.duty(0)


# ---------------------------------------------------------------- sd card
def mount_sd(path='/sd'):
    """SD karti baglar. Yolu ya da None doner."""
    import os
    try:
        os.listdir(path)
        return path
    except OSError:
        pass

    # Kart okuyucu VSPI'ye (slot 3) bagli. Slot 2'yi ASLA deneme - o HSPI,
    # yani ekranin hatti; basarisiz bir deneme host'u kilitli birakir ve
    # ekran bir daha acilmaz.
    sd = None
    try:
        from machine import SDCard
        sd = SDCard(slot=3, sck=Pin(SD_SCK), mosi=Pin(SD_MOSI),
                    miso=Pin(SD_MISO), cs=Pin(SD_CS))
        os.mount(sd, path)
        return path
    except Exception:
        if sd is not None:
            try:
                sd.deinit()
            except Exception:
                pass

    spi = None
    try:
        import sdcard
        spi = SPI(2, baudrate=1000000, polarity=0, phase=0,
                  sck=Pin(SD_SCK), mosi=Pin(SD_MOSI), miso=Pin(SD_MISO))
        card = sdcard.SDCard(spi, Pin(SD_CS))
        os.mount(card, path)
        spi.init(baudrate=20000000)
        return path
    except Exception:
        if spi is not None:
            try:
                spi.deinit()
            except Exception:
                pass
        return None


def i2c(sda=22, scl=27, freq=100000):
    """Harici sensorler icin I2C. CYD'de kullanilabilir tek cift 22/27."""
    from machine import SoftI2C
    return SoftI2C(sda=Pin(sda), scl=Pin(scl), freq=freq)


def splash(lines, rotation=None, color=WHITE, bg=NAVY, scale=2):
    d = display()
    d.fill(bg)
    y = 10
    for ln in lines:
        d.text(str(ln), 8, y, color, bg, scale)
        y += 10 * scale
    return d
