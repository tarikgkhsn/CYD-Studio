# Kart uzerinde calisir: OLED'in I2C pinlerini bulur.
from machine import Pin, I2C, SoftI2C
import time

ADAYLAR = ((5, 4), (4, 15), (21, 22), (16, 17), (13, 14))

# cogu kartta OLED reset hatti GPIO16
try:
    r = Pin(16, Pin.OUT)
    r.value(0)
    time.sleep_ms(20)
    r.value(1)
    time.sleep_ms(20)
    print('GPIO16 reset darbesi verildi')
except Exception as e:
    print('reset denemesi:', e)

bulundu = False
for sda, scl in ADAYLAR:
    for ad, yapici in (('I2C', I2C), ('SoftI2C', SoftI2C)):
        try:
            if yapici is I2C:
                i2c = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=400000)
            else:
                i2c = SoftI2C(sda=Pin(sda), scl=Pin(scl), freq=400000)
            a = i2c.scan()
        except Exception as e:
            continue
        if a:
            print('SDA=%-2d SCL=%-2d  %-7s -> %s'
                  % (sda, scl, ad, [hex(x) for x in a]))
            if 0x3C in a or 0x3D in a:
                print('   ==> OLED BULUNDU: SDA=%d SCL=%d adres=0x%02X'
                      % (sda, scl, 0x3C if 0x3C in a else 0x3D))
                bulundu = True
        else:
            print('SDA=%-2d SCL=%-2d  %-7s -> bos' % (sda, scl, ad))
    if bulundu:
        break

if not bulundu:
    print('OLED bulunamadi - pin adaylarini genisletmek gerekebilir')
