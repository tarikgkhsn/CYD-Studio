# ILI9341 driver for ESP32-2432S028R (CYD) - MicroPython
import framebuf
import _thread
from time import sleep_ms


def color565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


BLACK = 0x0000
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

# MADCTL without the BGR bit - panels differ on whether they need it, so
# it is applied separately and can be flipped at runtime.
_MADCTL_BGR = 0x08
# This board's panel sits landscape natively: with MV clear you address it
# as 320x240, and setting MV turns it portrait - the opposite of a stock
# ILI9341 module. Measured on the hardware, not assumed.
_ROT = {
    0: (0x40, 320, 240),   # MX            - yatay
    1: (0x20, 240, 320),   # MV            - dikey
    2: (0x80, 320, 240),   # MY            - yatay ters
    3: (0xE0, 240, 320),   # MX | MY | MV  - dikey ters
}

_INIT = (
    (0xEF, b'\x03\x80\x02', 0),
    (0xCF, b'\x00\xC1\x30', 0),
    (0xED, b'\x64\x03\x12\x81', 0),
    (0xE8, b'\x85\x00\x78', 0),
    (0xCB, b'\x39\x2C\x00\x34\x02', 0),
    (0xF7, b'\x20', 0),
    (0xEA, b'\x00\x00', 0),
    (0xC0, b'\x23', 0),
    (0xC1, b'\x10', 0),
    (0xC5, b'\x3E\x28', 0),
    (0xC7, b'\x86', 0),
    (0x3A, b'\x55', 0),
    (0xB1, b'\x00\x18', 0),
    (0xB6, b'\x08\x82\x27', 0),
    (0xF2, b'\x00', 0),
    (0x26, b'\x01', 0),
    (0xE0, b'\x0F\x31\x2B\x0C\x0E\x08\x4E\xF1\x37\x07\x10\x03\x0E\x09\x00', 0),
    (0xE1, b'\x00\x0E\x14\x03\x11\x07\x31\xC1\x48\x08\x0F\x0C\x31\x36\x0F', 0),
    (0x11, None, 120),
    (0x29, None, 20),
)


class ILI9341:
    def __init__(self, spi, cs, dc, rst=None, bl=None, rotation=0, bgr=True):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.bl = bl
        cs.init(cs.OUT, value=1)
        dc.init(dc.OUT, value=0)
        if rst:
            rst.init(rst.OUT, value=1)
        if bl:
            bl.init(bl.OUT, value=1)
        self.bgr = bool(bgr)
        self._chunk = bytearray(1024)
        # Projects run concurrently; a window-then-data pair must not be
        # interleaved with another thread's drawing or the bus desyncs.
        self._lock = _thread.allocate_lock()
        self.reset()
        for cmd, data, delay in _INIT:
            self._cmd(cmd, data)
            if delay:
                sleep_ms(delay)
        self.rotation(rotation)

    # ---------------- low level ----------------
    def _cmd(self, c, data=None):
        self.dc(0)
        self.cs(0)
        self.spi.write(bytes([c]))
        if data is not None:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def _data(self, data):
        self.dc(1)
        self.cs(0)
        self.spi.write(data)
        self.cs(1)

    def reset(self):
        if self.rst:
            self.rst(0)
            sleep_ms(50)
            self.rst(1)
            sleep_ms(120)
        else:
            self._cmd(0x01)
            sleep_ms(120)

    def rotation(self, rot, bgr=None):
        if bgr is not None:
            self.bgr = bool(bgr)
        madctl, w, h = _ROT[rot & 3]
        if self.bgr:
            madctl |= _MADCTL_BGR
        self._rot = rot & 3
        self.width = w
        self.height = h
        self._cmd(0x36, bytes([madctl]))
        return madctl

    def backlight(self, on):
        if self.bl:
            self.bl(1 if on else 0)

    def _window(self, x, y, w, h):
        x2 = x + w - 1
        y2 = y + h - 1
        self._cmd(0x2A, bytes((x >> 8, x & 0xFF, x2 >> 8, x2 & 0xFF)))
        self._cmd(0x2B, bytes((y >> 8, y & 0xFF, y2 >> 8, y2 & 0xFF)))
        self._cmd(0x2C)

    # ---------------- drawing ----------------
    def fill_rect(self, x, y, w, h, color):
        x = int(x)
        y = int(y)
        w = int(w)
        h = int(h)
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        w = min(w, self.width - x)
        h = min(h, self.height - y)
        if w <= 0 or h <= 0:
            return
        hi = color >> 8
        lo = color & 0xFF
        with self._lock:
            self._window(x, y, w, h)
            buf = self._chunk
            for i in range(0, len(buf), 2):
                buf[i] = hi
                buf[i + 1] = lo
            total = w * h * 2
            full = len(buf)
            self.dc(1)
            self.cs(0)
            while total >= full:
                self.spi.write(buf)
                total -= full
            if total:
                self.spi.write(memoryview(buf)[:total])
            self.cs(1)

    def fill(self, color=BLACK):
        self.fill_rect(0, 0, self.width, self.height, color)

    clear = fill

    def pixel(self, x, y, color):
        x = int(x)
        y = int(y)
        if 0 <= x < self.width and 0 <= y < self.height:
            with self._lock:
                self._window(x, y, 1, 1)
                self._data(bytes((color >> 8, color & 0xFF)))

    def hline(self, x, y, w, color):
        self.fill_rect(x, y, w, 1, color)

    def vline(self, x, y, h, color):
        self.fill_rect(x, y, 1, h, color)

    def rect(self, x, y, w, h, color, fill=False):
        if fill:
            self.fill_rect(x, y, w, h, color)
            return
        self.hline(x, y, w, color)
        self.hline(x, y + h - 1, w, color)
        self.vline(x, y, h, color)
        self.vline(x + w - 1, y, h, color)

    def line(self, x0, y0, x1, y1, color):
        x0 = int(x0)
        y0 = int(y0)
        x1 = int(x1)
        y1 = int(y1)
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(self, cx, cy, r, color, fill=False):
        cx = int(cx)
        cy = int(cy)
        x = int(r)
        y = 0
        err = 0
        while x >= y:
            if fill:
                self.hline(cx - x, cy + y, 2 * x + 1, color)
                self.hline(cx - x, cy - y, 2 * x + 1, color)
                self.hline(cx - y, cy + x, 2 * y + 1, color)
                self.hline(cx - y, cy - x, 2 * y + 1, color)
            else:
                for px, py in ((x, y), (y, x), (-y, x), (-x, y),
                               (-x, -y), (-y, -x), (y, -x), (x, -y)):
                    self.pixel(cx + px, cy + py, color)
            y += 1
            if err <= 0:
                err += 2 * y + 1
            else:
                x -= 1
                err += 2 * (y - x) + 1

    def text(self, s, x, y, color=WHITE, bg=BLACK, scale=1):
        """Built-in 8x8 font with integer scaling. Returns the next free x."""
        s = str(s)
        scale = max(1, int(scale))
        cw = 8 * scale
        glyph = bytearray(8)
        fb = framebuf.FrameBuffer(glyph, 8, 8, framebuf.MONO_HLSB)
        out = bytearray(cw * cw * 2)
        chi, clo = color >> 8, color & 0xFF
        bhi, blo = bg >> 8, bg & 0xFF
        cx = int(x)
        y = int(y)
        for ch in s:
            if cx + cw > self.width:
                break
            fb.fill(0)
            fb.text(ch, 0, 0, 1)
            i = 0
            for row in range(8):
                bits = glyph[row]
                start = i
                for col in range(8):
                    if bits & (0x80 >> col):
                        hi, lo = chi, clo
                    else:
                        hi, lo = bhi, blo
                    for _ in range(scale):
                        out[i] = hi
                        out[i + 1] = lo
                        i += 2
                span = i - start
                for _ in range(scale - 1):
                    out[i:i + span] = out[start:start + span]
                    i += span
            with self._lock:
                self._window(cx, y, cw, cw)
                self._data(out)
            cx += cw
        return cx

    def blit(self, buf, x, y, w, h):
        with self._lock:
            self._window(int(x), int(y), int(w), int(h))
            self._data(buf)
