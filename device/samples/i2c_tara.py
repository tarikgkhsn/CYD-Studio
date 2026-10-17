# I2C tarayici - sensoru hangi pinlere bagladigini bulur.
#
# CYD'de I2C icin kullanilabilecek pin sadece iki tane: GPIO22 ve GPIO27.
#   GPIO35 -> sadece giris, I2C cift yonlu oldugu icin KULLANILAMAZ
#   GPIO21 -> ekran arka aydinlatmasi, dokunma
# Bu yuzden iki olasilik var, ikisini de deniyoruz.
from machine import Pin, SoftI2C
import time

CIFTLER = (
    (22, 27),      # sda=22, scl=27
    (27, 22),      # sda=27, scl=22
)

BILINEN = {
    0x76: 'BME280 / BMP280  (SDO=GND)',
    0x77: 'BME280 / BMP280  (SDO=VCC)',
    0x68: 'MPU6050 / DS3231',
    0x3C: 'SSD1306 OLED',
    0x27: 'PCF8574 LCD',
    0x48: 'ADS1115 / LM75',
    0x40: 'SHT21 / INA219',
    0x5A: 'CCS811',
}


def cip_kimligi(i2c, adres):
    """BME280 ise 0x60, BMP280 ise 0x58 doner."""
    try:
        return i2c.readfrom_mem(adres, 0xD0, 1)[0]
    except Exception:
        return None


bulundu = False
bos_tarama = False        # hic adres yanit vermedi
tasan_tarama = False      # asiri adres yanit verdi (hat havada)

for sda, scl in CIFTLER:
    print('--- SDA=GPIO%d  SCL=GPIO%d' % (sda, scl))
    try:
        i2c = SoftI2C(sda=Pin(sda), scl=Pin(scl), freq=100000)
    except Exception as e:
        print('    I2C kurulamadi: %s' % e)
        continue

    try:
        adresler = i2c.scan()
    except Exception as e:
        print('    tarama hatasi: %s' % e)
        continue

    if not adresler:
        print('    cihaz yok')
        bos_tarama = True
        time.sleep_ms(200)
        continue

    # Pull-up yoksa hat havada kalir ve TUM adresler yanit veriyormus gibi
    # gorunur. Gercek bir sensorde bir ya da iki adres cikar.
    if len(adresler) > 6:
        print('    %d adres yanit verdi (0x%02X..0x%02X) - bu gercek cihaz'
              % (len(adresler), adresler[0], adresler[-1]))
        print('    DEGIL, hat bosta kalmis demek. Ya kablo bagli degil ya da')
        print('    pull-up direnci yok.')
        tasan_tarama = True
        time.sleep_ms(200)
        continue

    bulundu = True
    for a in adresler:
        ad = BILINEN.get(a, 'bilinmeyen cihaz')
        satir = '    0x%02X  %s' % (a, ad)
        cid = cip_kimligi(i2c, a)
        if cid == 0x60:
            satir += '  -> BME280 DOGRULANDI (nem var)'
        elif cid == 0x58:
            satir += '  -> BMP280 (nem YOK)'
        elif cid is not None:
            satir += '  (cip kimligi 0x%02X)' % cid
        print(satir)

    print()
    print('    ==> BUNU KULLAN:  SDA=%d  SCL=%d  adres=0x%02X'
          % (sda, scl, adresler[0]))
    break

print()
if not bulundu:
    # Iki ariza imzasi birbirinden ayirt edilebilir:
    #   bos liste  -> hat pull-up'li ama cip ACK vermiyor
    #   cok adres  -> hat havada, pull-up yok
    if bos_tarama and not tasan_tarama:
        print('TESHIS: hicbir adres yanit vermedi (bos liste).')
        print()
        print('Hat pull-up dirençleriyle yukari cekilmis durumda, yani modulun')
        print('VCC ve GND baglantisi buyuk ihtimalle SAGLAM. Eksik olan SCL.')
        print('SCL kopuksa sensor saat darbesi alamaz, hic ACK uretemez ve')
        print('tam boyle bos bir liste gorursun.')
        print()
        print('  -> ONCE SCL KABLOSUNA BAK (GPIO27 tarafi)')
        print('  -> Sonra CSB pinine bak: 6 bacakli modullerde CSB bosta')
        print('     kalirsa cip SPI modunda takilir ve I2C ye hic cevap vermez.')
        print('     CSB 3.3V a cekilmeli.')
    elif tasan_tarama:
        print('TESHIS: cok sayida adres yanit verdi, yani hat HAVADA.')
        print()
        print('  -> SDA kablosu bagli degil ya da modul beslenmiyorndan')
        print('     pull-up direncleri calismiyor.')
        print('  -> VCC ve SDA baglantilarini kontrol et.')
    else:
        print('HICBIR I2C CIHAZI BULUNAMADI.')
    print()
    print('Diger olasiliklar:')
    print('  - VCC gercekten 3.3V mu? (5V pinine bagladiysan modulun')
    print('    regulatoru yoksa calismaz)')
    print('  - GND ortak mi?')
    print('  - Lehim/jumper temasi - en sik sebep bu.')
else:
    print('Bu degerleri ornek_bme280.py icindeki SDA/SCL satirlarina yaz.')
