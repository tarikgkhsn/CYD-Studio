# OLED (SSD1306) canlilik testi.
#
# Once pinleri BULUR - hangi pine bagladigini bilmemize gerek yok, aday
# ciftleri deneyip 0x3C/0x3D adresini arar. Sonra ekranda ust uste birkac
# belirgin desen gosterir; ekranda bir sey oynuyorsa donanim saglam.
#
# SSD1306 TEK RENKTIR: renk yerine piksel desenleri kullaniyoruz.
#
# NodeMCU'da yaygin baglanti:
#     OLED VCC -> 3.3V     GND -> GND
#     OLED SDA -> D2 (GPIO4)     SCL -> D1 (GPIO5)
from machine import Pin, SoftI2C
import time

# (sda, scl) - NodeMCU'da en yaygin olanlar once
ADAYLAR = ((4, 5), (5, 4), (0, 2), (2, 0), (14, 12), (12, 14))
ADRESLER = (0x3C, 0x3D)
BEKLE = 1.6


def bul():
    for sda, scl in ADAYLAR:
        try:
            i2c = SoftI2C(sda=Pin(sda), scl=Pin(scl), freq=400000)
            bulunan = i2c.scan()
        except Exception:
            continue
        if not bulunan:
            print('  SDA=%-2d SCL=%-2d -> bos' % (sda, scl))
            continue
        if len(bulunan) > 6:
            print('  SDA=%-2d SCL=%-2d -> %d adres yanit verdi = hat BOSTA '
                  '(pull-up yok / kablo takili degil)' % (sda, scl, len(bulunan)))
            continue
        print('  SDA=%-2d SCL=%-2d -> %s' % (sda, scl, [hex(x) for x in bulunan]))
        for a in ADRESLER:
            if a in bulunan:
                return i2c, a, sda, scl
    return None, None, None, None


print('OLED araniyor...')
i2c, adres, sda, scl = bul()

if i2c is None:
    print()
    print('OLED BULUNAMADI. Sirayla kontrol et:')
    print('  1) VCC 3.3V ve GND bagli mi?')
    print('  2) SDA ve SCL yerleri dogru mu? (ters takmak cok yaygin)')
    print('  3) Yukarida "hat BOSTA" yaziyorsa kablolardan biri kopuk')
    print('  4) Modulun adresi 0x3C ya da 0x3D olmali')
    raise SystemExit

print()
print('BULUNDU -> adres 0x%02X, SDA=GPIO%d, SCL=GPIO%d' % (adres, sda, scl))

import ssd1306

# Cogu modul 128x64; 128x32 olanlar da var. Once 64 deneriz.
G, Y = 128, 64
try:
    ekran = ssd1306.SSD1306_I2C(G, Y, i2c, addr=adres)
except Exception as e:
    print('128x64 acilamadi (%s), 128x32 deneniyor' % e)
    G, Y = 128, 32
    ekran = ssd1306.SSD1306_I2C(G, Y, i2c, addr=adres)

print('ekran hazir: %dx%d' % (G, Y))
print('simdi ekrana bak - desenler degisecek')
print()


def goster(ad):
    print('  ->', ad)
    ekran.show()


# 1) hepsi YANIK - en belirgin test, ekran komple parlar
ekran.fill(1)
goster('1/7  TUM PIKSELLER YANIK (ekran komple parlamali)')
if not __import__('cyd').sleep(BEKLE):
    raise SystemExit

# 2) hepsi sonuk
ekran.fill(0)
goster('2/7  hepsi sonuk (ekran komple karanlik)')
if not __import__('cyd').sleep(BEKLE):
    raise SystemExit

# 3) satranc tahtasi - piksel adreslemesi dogru mu
ekran.fill(0)
for y in range(0, Y, 8):
    for x in range(0, G, 8):
        if ((x // 8) + (y // 8)) % 2 == 0:
            ekran.fill_rect(x, y, 8, 8, 1)
goster('3/7  satranc tahtasi')
if not __import__('cyd').sleep(BEKLE):
    raise SystemExit

# 4) cerceve - dort kenar da gorunuyor mu, olculer dogru mu
ekran.fill(0)
ekran.rect(0, 0, G, Y, 1)
ekran.rect(2, 2, G - 4, Y - 4, 1)
ekran.text('%dx%d' % (G, Y), 8, Y // 2 - 4, 1)
goster('4/7  cerceve (dort kenara da degmeli)')
if not __import__('cyd').sleep(BEKLE):
    raise SystemExit

# 5) yazi
ekran.fill(0)
ekran.text('CYD Studio', 4, 4, 1)
ekran.text('OLED calisiyor', 4, 18, 1)
ekran.text('0x%02X SDA%d SCL%d' % (adres, sda, scl), 4, 32, 1)
goster('5/7  yazi')
if not __import__('cyd').sleep(BEKLE):
    raise SystemExit

# 6) yatay cizgiler
ekran.fill(0)
for y in range(0, Y, 4):
    ekran.hline(0, y, G, 1)
goster('6/7  yatay cizgiler')
if not __import__('cyd').sleep(BEKLE):
    raise SystemExit

# 7) dolan cubuk - animasyon calisiyor mu
import cyd
for i in range(0, G - 8, 8):
    ekran.fill(0)
    ekran.rect(2, Y // 2 - 8, G - 4, 16, 1)
    ekran.fill_rect(4, Y // 2 - 6, i, 12, 1)
    ekran.show()
    if not cyd.sleep(0.12):
        break
print('  -> 7/7  dolan cubuk')

ekran.fill(0)
ekran.text('TEST BITTI', 20, Y // 2 - 4, 1)
ekran.show()

print()
print('TEST BITTI.')
print('Desenleri gorduysen ekran calisiyor: adres 0x%02X, SDA=%d, SCL=%d'
      % (adres, sda, scl))
print('Hicbir sey gormediysen VCC/GND baglantisina ve modulun 3.3V')
print('ile calistigina bak (5V modulleri bu kartta calismaz).')
