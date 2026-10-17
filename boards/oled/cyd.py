# cyd.py - ESP32 + yerlesik 0.96" SSD1306 OLED karti icin donanim katmani.
#
# Modul adi tarihsel olarak `cyd` kaldi: projeler `import cyd` yaziyor ve
# ayni kod iki kartta da calissin istiyoruz. Burada ekran 128x64 tek renk,
# dokunmatik ve SD yok.
#
# Ekran sinifi bilerek ILI9341 ile AYNI arayuzu sunuyor (fill, fill_rect,
# text(..., olcek), circle ...). Boylece CYD icin yazilmis projeler burada
# da calisir; renkler tek renk ekranda "yanik/sonuk"e dusuruluyor.
from machine import Pin, I2C, SoftI2C
import framebuf
import time

import ssd1306
from runtime import (rota, rota_sil, rotalar, should_stop, sleep, job_name, claim_display,
                     release_display, display_owner, warn_shared_display,
                     dram, wifi, buton, Buton, _register_stop, _unregister_stop)

# Bu kartin sundugu ozellikler - panel ve cekirdek buna bakar.
OZELLIKLER = {
    'display': True,       # 128x64 tek renk SSD1306
    'touch': False,
    'sd': False,
    'rgb_led': False,
    'light': False,
    'speaker': False,
    'ble': True,           # solo modda
    'tls': True,           # solo modda
    'wifi_config': True,
    'docs': True,
    'lite_ui': False,
}

# ---------------------------------------------------------------- renkler
# Tek renk ekran: 0 sonuk, sifirdan farkli her sey yanik.
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


# ------------------------------------------------------------- pin adaylari
# Bu kartlarda OLED'in I2C pinleri uretici modeline gore degisiyor, bu
# yuzden tahmin etmek yerine sirayla deneyip 0x3C/0x3D ariyoruz.
I2C_ADAYLAR = (
    (5, 4),      # yaygin generic ESP32-OLED
    (4, 15),     # Heltec WiFi Kit 32  (RST = 16)
    (21, 22),    # standart ESP32 I2C
    (16, 17),
    (13, 14),
)
OLED_RESET = 16          # cogu kartta OLED reset hatti
OLED_ADRESLER = (0x3C, 0x3D)

OLED_W = 128
OLED_H = 64

_display = None
_i2c = None
_pins = None


class Ekran:
    """SSD1306'yi ILI9341 arayuzuyle sarar."""

    def __init__(self, oled, width, height):
        self.oled = oled
        self.width = width
        self.height = height
        self._rot = 0
        self.auto = True          # her cizimden sonra ekrana bas
        self._glyph = bytearray(8)
        self._fb = framebuf.FrameBuffer(self._glyph, 8, 8, framebuf.MONO_HLSB)

    # -- tek renk ekranda renk sadece yanik/sonuk demek
    @staticmethod
    def _c(color):
        return 0 if not color else 1

    def show(self):
        self.oled.show()

    def _bas(self):
        if self.auto:
            self.oled.show()

    # ------------------------------------------------------------ cizim
    def fill(self, color=BLACK):
        self.oled.fill(self._c(color))
        self._bas()

    clear = fill

    def fill_rect(self, x, y, w, h, color):
        self.oled.fill_rect(int(x), int(y), int(w), int(h), self._c(color))
        self._bas()

    def rect(self, x, y, w, h, color, fill=False):
        c = self._c(color)
        if fill:
            self.oled.fill_rect(int(x), int(y), int(w), int(h), c)
        else:
            self.oled.rect(int(x), int(y), int(w), int(h), c)
        self._bas()

    def pixel(self, x, y, color):
        self.oled.pixel(int(x), int(y), self._c(color))
        self._bas()

    def hline(self, x, y, w, color):
        self.oled.hline(int(x), int(y), int(w), self._c(color))
        self._bas()

    def vline(self, x, y, h, color):
        self.oled.vline(int(x), int(y), int(h), self._c(color))
        self._bas()

    def line(self, x0, y0, x1, y1, color):
        self.oled.line(int(x0), int(y0), int(x1), int(y1), self._c(color))
        self._bas()

    def circle(self, cx, cy, r, color, fill=False):
        cx = int(cx)
        cy = int(cy)
        x = int(r)
        y = 0
        err = 0
        c = self._c(color)
        eski = self.auto
        self.auto = False
        while x >= y:
            if fill:
                self.oled.hline(cx - x, cy + y, 2 * x + 1, c)
                self.oled.hline(cx - x, cy - y, 2 * x + 1, c)
                self.oled.hline(cx - y, cy + x, 2 * y + 1, c)
                self.oled.hline(cx - y, cy - x, 2 * y + 1, c)
            else:
                for px, py in ((x, y), (y, x), (-y, x), (-x, y),
                               (-x, -y), (-y, -x), (y, -x), (x, -y)):
                    self.oled.pixel(cx + px, cy + py, c)
            y += 1
            if err <= 0:
                err += 2 * y + 1
            else:
                x -= 1
                err += 2 * (y - x) + 1
        self.auto = eski
        self._bas()

    def text(self, s, x, y, color=WHITE, bg=BLACK, scale=1):
        """Gomulu 8x8 font, tam sayi olcekleme. Bir sonraki bos x'i doner."""
        s = str(s)
        scale = max(1, int(scale))
        c = self._c(color)
        b = self._c(bg)
        cx = int(x)
        y = int(y)
        eski = self.auto
        self.auto = False

        if scale == 1:
            # olcek 1'de framebuf'un kendi text'i yeterli ve hizli
            if b != c:
                self.oled.fill_rect(cx, y, 8 * len(s), 8, b)
            self.oled.text(s, cx, y, c)
            cx += 8 * len(s)
        else:
            for ch in s:
                if cx >= self.width:
                    break
                self._fb.fill(0)
                self._fb.text(ch, 0, 0, 1)
                for row in range(8):
                    bits = self._glyph[row]
                    for col in range(8):
                        acik = bits & (0x80 >> col)
                        if acik or b != c:
                            self.oled.fill_rect(cx + col * scale,
                                                y + row * scale,
                                                scale, scale,
                                                c if acik else b)
                cx += 8 * scale

        self.auto = eski
        self._bas()
        return cx

    # ---------------------------------------------------------- uyumluluk
    def backlight(self, on=True):
        """OLED'in arka aydinlatmasi yok; paneli acip kapatiyoruz."""
        try:
            self.oled.poweron() if on else self.oled.poweroff()
        except Exception:
            pass

    def rotation(self, rot, bgr=None):
        """SSD1306 sadece 0/180 destekler; 1 ve 3 en yakin degere duser."""
        self._rot = rot & 3
        try:
            self.oled.rotate(self._rot in (2, 3))
        except Exception:
            pass
        return self._rot

    def blit(self, buf, x, y, w, h):
        fb = framebuf.FrameBuffer(bytearray(buf), w, h, framebuf.MONO_HLSB)
        self.oled.blit(fb, int(x), int(y))
        self._bas()


# ------------------------------------------------------------------ ekran
def _oled_bul():
    """Aday pin ciftlerini deneyip OLED'i bulur. (i2c, adres, pinler)."""
    try:
        r = Pin(OLED_RESET, Pin.OUT)      # cogu kartta OLED reset hatti
        r.value(0)
        time.sleep_ms(20)
        r.value(1)
        time.sleep_ms(20)
    except Exception:
        pass

    for sda, scl in I2C_ADAYLAR:
        for yapici in (I2C, SoftI2C):
            try:
                if yapici is I2C:
                    i2c = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=400000)
                else:
                    i2c = SoftI2C(sda=Pin(sda), scl=Pin(scl), freq=400000)
                bulunan = i2c.scan()
            except Exception:
                continue
            for a in OLED_ADRESLER:
                if a in bulunan:
                    return i2c, a, (sda, scl)
    return None, None, None


def display(rotation=None, bgr=None):
    """OLED'i tembel olusturur. rotation/bgr parametreleri CYD ile uyum
    icin kabul edilir; SSD1306'da renk duzeni yoktur."""
    global _display, _i2c, _pins
    warn_shared_display()
    if _display is None:
        i2c, adres, pins = _oled_bul()
        if i2c is None:
            raise OSError('OLED bulunamadi. Denenen pinler: %s' %
                          (I2C_ADAYLAR,))
        _i2c = i2c
        _pins = pins
        oled = ssd1306.SSD1306_I2C(OLED_W, OLED_H, i2c, addr=adres)
        _display = Ekran(oled, OLED_W, OLED_H)
        _display.fill(BLACK)
        print('OLED hazir: 0x%02X, SDA=%d SCL=%d' % (adres, pins[0], pins[1]))
    return _display


def set_display(rotation, bgr):
    d = display()
    d.rotation(int(rotation))
    return d


def test_pattern(label=''):
    d = display()
    d.auto = False
    d.fill(BLACK)
    d.rect(0, 0, d.width, d.height, WHITE)
    d.rect(1, 1, d.width - 2, d.height - 2, WHITE)
    d.fill_rect(d.width - 26, d.height - 26, 18, 18, WHITE)
    d.text('CERCEVE', 6, 8, WHITE, BLACK, 1)
    d.text('4 KENARDA MI?', 6, 20, WHITE, BLACK, 1)
    if label:
        d.text(label, 6, 34, WHITE, BLACK, 1)
    d.auto = True
    d.show()
    return d


def i2c():
    """OLED'in kullandigi I2C veri yolu (baska sensor eklemek icin)."""
    display()
    return _i2c


def i2c_pins():
    display()
    return _pins


# ------------------------------------------- bu kartta olmayan donanimlar
def touch(rotation=None):
    raise OSError('bu kartta dokunmatik ekran yok')


def led(r=False, g=False, b=False):
    """Yerlesik RGB LED yok. Tek renkli bir LED varsa LED_PIN'i ayarla."""
    if LED_PIN is None:
        return
    global _led_pin
    if _led_pin is None:
        _led_pin = Pin(LED_PIN, Pin.OUT)
    _led_pin.value(1 if (r or g or b) else 0)


LED_PIN = None          # kartinda LED varsa GPIO numarasini yaz (orn. 2)
_led_pin = None


def led_off():
    led(False, False, False)


def light():
    raise OSError('bu kartta isik sensoru (LDR) yok')


def beep(freq=1000, ms=100, volume=512):
    raise OSError('bu kartta hoparlor yok')


def tone_off():
    pass


def mount_sd(path='/sd'):
    """Bu kartta SD yuvasi yok."""
    return None


def splash(lines, rotation=None, color=WHITE, bg=BLACK, scale=1):
    d = display()
    d.auto = False
    d.fill(bg)
    y = 0
    for ln in lines:
        d.text(str(ln), 0, y, color, bg, scale)
        y += 9 * scale
        if y >= d.height:
            break
    d.auto = True
    d.show()
    return d
