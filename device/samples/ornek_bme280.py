# BME280 - SUREKLI olcum. Sadece Durdur'a basinca durur.
#
# Bu dosya bilerek "pes etmeyen" sekilde yazildi:
#   - sensor acilista yoksa bulana kadar dener, cikmaz
#   - okuma sirasinda kablo cikarsa hatayi yazar, beklemeye devam eder
#   - kablo geri takilinca kendiliginden toparlanir
#   - beklenmedik bir hata da projeyi oldurmez
#
# KABLOLAMA:
#   VCC -> 3.3V     GND -> GND     SDA -> GPIO22     SCL -> GPIO27
from machine import Pin, SoftI2C
import cyd
import bme280

SDA = 22
SCL = 27
ARALIK = 2.0            # olcumler arasi saniye
LOG_HER = 1             # kac olcumde bir loga yazsin (1 = hepsi)

d = cyd.display()
d.fill(cyd.BLACK)

# Ayni kod hem CYD'nin 320x240 ekraninda hem OLED kartinin 128x64
# ekraninda calissin diye yerlesim ekran boyutundan hesaplaniyor.
BUYUK = d.height >= 160
if BUYUK:
    OLCEK, ETIKET_X, SATIR_Y = 3, 10, 40
    Y_BASLIK, Y_SICAK = 8, 82
    Y_DURUM = d.height - 26
else:
    OLCEK, ETIKET_X, SATIR_Y = 1, 0, 11
    Y_BASLIK, Y_SICAK = 0, 14
    Y_DURUM = d.height - 8

Y_HAZIR = Y_BASLIK + (26 if BUYUK else 9)
Y_BASINC = Y_SICAK + SATIR_Y
Y_NEM = Y_BASINC + SATIR_Y

d.text('BME280', ETIKET_X, Y_BASLIK, cyd.CYAN, cyd.BLACK, 3 if BUYUK else 1)


def satir(y, etiket, deger, birim, renk):
    d.fill_rect(0, y, d.width, SATIR_Y, cyd.BLACK)
    if BUYUK:
        d.text(etiket, ETIKET_X, y + 10, cyd.GREY, cyd.BLACK, 1)
        d.text('%s%s' % (deger, birim), 90, y, renk, cyd.BLACK, OLCEK)
    else:
        d.text('%-5s %s%s' % (etiket[:5], deger, birim), ETIKET_X, y,
               renk, cyd.BLACK, 1)


def durum(mesaj, renk=cyd.GREY):
    d.fill_rect(0, Y_DURUM, d.width, 8 if not BUYUK else 22, cyd.BLACK)
    if not BUYUK:
        mesaj = mesaj[:21]        # 128 px = 16 karakter, tasmasin
    d.text(mesaj, ETIKET_X, Y_DURUM, renk, cyd.BLACK, 1)


def sensor_bagla():
    """Sensor bulunana kadar dener. Durdur'a basilirsa None doner."""
    ilk = True
    while not cyd.should_stop():
        try:
            i2c = SoftI2C(sda=Pin(SDA), scl=Pin(SCL), freq=100000)
            s = bme280.BME280(i2c)
            print('sensor bagli: adres 0x%02X, cip 0x%02X, nem %s'
                  % (s.adres, s.chip_id, 'var' if s.nem_var else 'YOK'))
            d.fill_rect(0, Y_HAZIR, d.width, 12 if not BUYUK else 24, cyd.BLACK)
            d.text('0x%02X hazir' % s.adres, ETIKET_X, Y_HAZIR,
                   cyd.GREEN, cyd.BLACK, 2 if BUYUK else 1)
            return s
        except Exception as e:
            if ilk:
                print('sensor yok (%s) - baglanana kadar denenecek' % e)
                d.fill_rect(0, Y_HAZIR, d.width, 12 if not BUYUK else 24,
                            cyd.BLACK)
                d.text('sensor bekleniyor', ETIKET_X, Y_HAZIR,
                       cyd.ORANGE, cyd.BLACK, 2 if BUYUK else 1)
                durum('kablolari kontrol et: 3.3V GND SDA=22 SCL=27',
                      cyd.ORANGE)
                ilk = False
            if not cyd.sleep(3):
                return None
    return None


s = sensor_bagla()
n = 0
hata_ustuste = 0
t_min = t_max = None

while not cyd.should_stop():
    if s is None:
        s = sensor_bagla()
        if s is None:
            break
        hata_ustuste = 0

    try:
        t, p, nem = s.oku()
        hata_ustuste = 0
    except Exception as e:
        hata_ustuste += 1
        print('okuma hatasi (%d): %s' % (hata_ustuste, e))
        durum('okuma hatasi x%d - kabloya bak' % hata_ustuste, cyd.RED)
        if hata_ustuste >= 3:
            # sensor muhtemelen cikarildi; bastan baglanmayi dene
            print('sensor kayboldu, yeniden baglanmaya calisiliyor')
            s = None
        if not cyd.sleep(ARALIK):
            break
        continue

    n += 1
    t_min = t if t_min is None else min(t_min, t)
    t_max = t if t_max is None else max(t_max, t)

    if n % LOG_HER == 0:
        if nem is None:
            print('%4d)  %.2f C   %.1f hPa' % (n, t, p))
        else:
            print('%4d)  %.2f C   %.1f hPa   %%%.1f nem' % (n, t, p, nem))

    renk_t = cyd.CYAN if t < 18 else (cyd.GREEN if t < 27 else cyd.ORANGE)
    satir(Y_SICAK, 'SICAKLIK', '%.1f' % t, ' C', renk_t)
    satir(Y_BASINC, 'BASINC', '%.0f' % p, ' hPa', cyd.WHITE)
    if nem is not None:
        renk_n = cyd.BLUE if nem > 60 else (cyd.GREEN if nem > 30 else cyd.YELLOW)
        satir(Y_NEM, 'NEM', '%.0f' % nem, ' %', renk_n)

    dk = int(n * ARALIK) // 60
    durum('%d olcum  %d dk  min %.1f  max %.1f C' % (n, dk, t_min, t_max))

    if not cyd.sleep(ARALIK):
        break

print('durduruldu - %d olcum yapildi' % n)
if t_min is not None:
    print('sicaklik araligi: %.2f .. %.2f C' % (t_min, t_max))
durum('durduruldu', cyd.RED)
