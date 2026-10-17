# XPT2046 resistive touch controller - ESP32-2432S028R (CYD)
#
# Detection is driven by the PENIRQ line rather than a pressure threshold:
# the panels vary a lot in resistance, so a fixed z-threshold either misses
# light touches or fires on noise. PENIRQ is a hardware answer to the same
# question. Pressure is still read and returned, just not used as the gate.
from time import sleep_ms

_CMD_X = 0xD0    # X position, 12-bit, power-down between conversions
_CMD_Y = 0x90    # Y position
_CMD_Z1 = 0xB0
_CMD_Z2 = 0xC0


class XPT2046:
    """Raw readings run roughly 200..3900 on both axes."""

    def __init__(self, spi, cs, irq=None, width=240, height=320, rotation=0,
                 x_min=300, x_max=3800, y_min=300, y_max=3800,
                 swap_xy=False, invert_x=False, invert_y=False):
        self.spi = spi
        self.cs = cs
        cs.init(cs.OUT, value=1)
        self.irq = irq
        self.width = width
        self.height = height
        self.rotation = rotation
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        self.swap_xy = swap_xy
        self.invert_x = invert_x
        self.invert_y = invert_y
        self._tx = bytearray(3)
        self._rx = bytearray(3)

    # ------------------------------------------------------------ low level
    def _read(self, cmd):
        self._tx[0] = cmd
        self._tx[1] = 0
        self._tx[2] = 0
        self.cs(0)
        self.spi.write_readinto(self._tx, self._rx)
        self.cs(1)
        return ((self._rx[1] << 8) | self._rx[2]) >> 3      # 12-bit

    def pressed(self):
        """Hardware pen-down line. Falls back to pressure if IRQ is absent."""
        if self.irq is not None:
            return self.irq.value() == 0
        z1 = self._read(_CMD_Z1)
        z2 = self._read(_CMD_Z2)
        return (z1 + 4095 - z2) > 400

    def pressure(self):
        z1 = self._read(_CMD_Z1)
        z2 = self._read(_CMD_Z2)
        return z1 + 4095 - z2

    def raw(self, samples=5):
        """Median of several samples, or None when nothing is touching."""
        if not self.pressed():
            return None
        xs = []
        ys = []
        for _ in range(samples):
            xs.append(self._read(_CMD_X))
            ys.append(self._read(_CMD_Y))
        xs.sort()
        ys.sort()
        x = xs[len(xs) // 2]
        y = ys[len(ys) // 2]
        # a real contact never sits at the rails
        if x < 60 or y < 60 or x > 4030 or y > 4030:
            return None
        return (x, y, self.pressure())

    # -------------------------------------------------------- screen coords
    def touch(self):
        """Screen coordinates (x, y), or None. Honours rotation."""
        r = self.raw()
        if r is None:
            return None
        rx, ry, _ = r
        nx = (rx - self.x_min) / (self.x_max - self.x_min)
        ny = (ry - self.y_min) / (self.y_max - self.y_min)
        nx = min(1.0, max(0.0, nx))
        ny = min(1.0, max(0.0, ny))

        if self.swap_xy:
            nx, ny = ny, nx
        if self.invert_x:
            nx = 1.0 - nx
        if self.invert_y:
            ny = 1.0 - ny

        rot = self.rotation
        if rot == 0:
            x, y = nx, ny
        elif rot == 1:
            x, y = ny, 1.0 - nx
        elif rot == 2:
            x, y = 1.0 - nx, 1.0 - ny
        else:
            x, y = 1.0 - ny, nx
        return (int(x * (self.width - 1)), int(y * (self.height - 1)))

    def wait_touch(self, timeout_ms=None, poll_ms=20, stop=None):
        """Block until touched. `stop` is an optional callable to abort."""
        waited = 0
        while True:
            p = self.touch()
            if p:
                return p
            if stop and stop():
                return None
            if timeout_ms is not None and waited >= timeout_ms:
                return None
            sleep_ms(poll_ms)
            waited += poll_ms
