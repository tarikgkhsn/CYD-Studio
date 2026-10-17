# BME280 / BMP280 surucusu - MicroPython, I2C
#
# Sensorun ham ciktisi dogrudan kullanilamaz; her cipin fabrikada olculmus
# kendi kalibrasyon katsayilari var ve Bosch'un telafi formullerinden
# gecirmek zorunlu. Formuller BME280 veri sayfasindaki referans koddur.
#
# Kullanim:
#   from machine import Pin, I2C
#   import bme280
#   i2c = I2C(0, scl=Pin(27), sda=Pin(22), freq=100000)
#   s = bme280.BME280(i2c)
#   print(s.oku())        # (sicaklik, basinc_hPa, nem_yuzde)
import struct
import time

ADRESLER = (0x76, 0x77)

_REG_ID = 0xD0
_REG_RESET = 0xE0
_REG_CTRL_HUM = 0xF2
_REG_STATUS = 0xF3
_REG_CTRL_MEAS = 0xF4
_REG_CONFIG = 0xF5
_REG_DATA = 0xF7

CHIP_BME280 = 0x60      # sicaklik + basinc + NEM
CHIP_BMP280 = 0x58      # sicaklik + basinc (nem yok)


class BME280:
    def __init__(self, i2c, adres=None):
        self.i2c = i2c
        if adres is None:
            bulunan = i2c.scan()
            for a in ADRESLER:
                if a in bulunan:
                    adres = a
                    break
            if adres is None:
                raise OSError('BME280 bulunamadi. I2C taramasi: %s'
                              % [hex(x) for x in bulunan])
        self.adres = adres

        self.chip_id = self._u8(_REG_ID)
        if self.chip_id not in (CHIP_BME280, CHIP_BMP280):
            raise OSError('0x%02X adresinde beklenmeyen cip kimligi 0x%02X '
                          '(BME280 icin 0x60 bekleniyordu)'
                          % (self.adres, self.chip_id))
        self.nem_var = (self.chip_id == CHIP_BME280)

        self.i2c.writeto_mem(self.adres, _REG_RESET, b'\xB6')
        time.sleep_ms(10)

        self._kalibrasyon_oku()

        # Nem yazmaci ctrl_meas'tan ONCE yazilmali, yoksa etkisiz kalir.
        if self.nem_var:
            self.i2c.writeto_mem(self.adres, _REG_CTRL_HUM, b'\x01')   # x1
        self.i2c.writeto_mem(self.adres, _REG_CONFIG, b'\xA0')         # 1000ms
        # osrs_t x1 | osrs_p x1 | normal mod
        self.i2c.writeto_mem(self.adres, _REG_CTRL_MEAS, b'\x27')
        time.sleep_ms(50)
        self.t_fine = 0

    # ------------------------------------------------------------ yazmaclar
    def _oku(self, reg, n):
        return self.i2c.readfrom_mem(self.adres, reg, n)

    def _u8(self, reg):
        return self._oku(reg, 1)[0]

    def _kalibrasyon_oku(self):
        c = self._oku(0x88, 26)
        (self.T1, self.T2, self.T3,
         self.P1, self.P2, self.P3, self.P4, self.P5,
         self.P6, self.P7, self.P8, self.P9) = struct.unpack('<HhhHhhhhhhhh', c[:24])
        self.H1 = c[25]

        if not self.nem_var:
            return
        h = self._oku(0xE1, 7)
        self.H2 = struct.unpack('<h', h[0:2])[0]
        self.H3 = h[2]
        # H4 ve H5 12 bitlik ve isaretli, bir bayti paylasiyorlar
        self.H4 = (h[3] << 4) | (h[4] & 0x0F)
        if self.H4 > 2047:
            self.H4 -= 4096
        self.H5 = (h[5] << 4) | (h[4] >> 4)
        if self.H5 > 2047:
            self.H5 -= 4096
        self.H6 = h[6] - 256 if h[6] > 127 else h[6]

    # -------------------------------------------------------------- olcum
    def oku(self):
        """(sicaklik C, basinc hPa, bagil nem %) dondurur."""
        d = self._oku(_REG_DATA, 8)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        adc_h = (d[6] << 8) | d[7]

        # --- sicaklik (t_fine digerlerinde de kullaniliyor)
        v1 = (adc_t / 16384.0 - self.T1 / 1024.0) * self.T2
        v2 = ((adc_t / 131072.0 - self.T1 / 8192.0) ** 2) * self.T3
        self.t_fine = v1 + v2
        sicaklik = self.t_fine / 5120.0

        # --- basinc
        v1 = self.t_fine / 2.0 - 64000.0
        v2 = v1 * v1 * self.P6 / 32768.0
        v2 = v2 + v1 * self.P5 * 2.0
        v2 = v2 / 4.0 + self.P4 * 65536.0
        v1 = (self.P3 * v1 * v1 / 524288.0 + self.P2 * v1) / 524288.0
        v1 = (1.0 + v1 / 32768.0) * self.P1
        if v1 == 0:
            basinc = 0.0
        else:
            p = 1048576.0 - adc_p
            p = (p - v2 / 4096.0) * 6250.0 / v1
            v1 = self.P9 * p * p / 2147483648.0
            v2 = p * self.P8 / 32768.0
            basinc = (p + (v1 + v2 + self.P7) / 16.0) / 100.0   # Pa -> hPa

        # --- nem
        if not self.nem_var:
            return (sicaklik, basinc, None)
        h = self.t_fine - 76800.0
        h = (adc_h - (self.H4 * 64.0 + self.H5 / 16384.0 * h)) * (
            self.H2 / 65536.0 * (1.0 + self.H6 / 67108864.0 * h *
                                 (1.0 + self.H3 / 67108864.0 * h)))
        h = h * (1.0 - self.H1 * h / 524288.0)
        nem = min(100.0, max(0.0, h))
        return (sicaklik, basinc, nem)

    def yukseklik(self, deniz_seviyesi_hPa=1013.25):
        """Basinctan yaklasik rakim (metre)."""
        _, p, _ = self.oku()
        if not p:
            return None
        return 44330.0 * (1.0 - (p / deniz_seviyesi_hPa) ** 0.1903)

    def __str__(self):
        t, p, n = self.oku()
        if n is None:
            return '%.2f C  %.2f hPa' % (t, p)
        return '%.2f C  %.2f hPa  %%%.1f' % (t, p, n)


# Bu dosya bir SURUCU: normalde `import bme280` ile kullanilir. Panelden
# dogrudan calistirilirsa sessizce bitmesin diye tek seferlik olcum yapar.
if __name__ == '__main__':
    from machine import Pin, SoftI2C

    print('bme280.py bir surucudur - surekli olcum icin ornek_bme280.py calistir.')
    print('tek seferlik olcum deneniyor...')
    try:
        _i2c = SoftI2C(sda=Pin(22), scl=Pin(27), freq=100000)
        _s = BME280(_i2c)
        _t, _p, _n = _s.oku()
        print('adres 0x%02X, cip 0x%02X' % (_s.adres, _s.chip_id))
        if _n is None:
            print('sicaklik %.2f C   basinc %.1f hPa' % (_t, _p))
        else:
            print('sicaklik %.2f C   basinc %.1f hPa   nem %%%.1f'
                  % (_t, _p, _n))
    except Exception as _e:
        print('okunamadi:', _e)
        print('once i2c_tara.py ile pinleri dogrula.')
