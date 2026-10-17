# sd_kontrol.py - SD karti teshis eder, istenirse FAT olarak bicimlendirir.
#
# Calistir, logu oku. Kart "dosya sistemi yok / tanimiyor" diyorsa en sik
# sebep exFAT: 64 GB ve ustu kartlar fabrikadan exFAT gelir, MicroPython
# sadece FAT okur. O zaman BICIMLE = True yapip bir kez daha calistir.
#
# DIKKAT: BICIMLE = True karttaki HER SEYI siler.
import os
import cyd
from machine import Pin

BICIMLE = False          # True -> kart FAT olarak bicimlenir (SILER!)
YOL = '/sd'

# CYD'de SD okuyucu VSPI'de (slot 3). Slot 2'yi ASLA kullanma: o ekranin
# hatti, basarisiz bir deneme ekrani kilitler.
SCK = getattr(cyd, 'SD_SCK', 18)
MOSI = getattr(cyd, 'SD_MOSI', 23)
MISO = getattr(cyd, 'SD_MISO', 19)
CS = getattr(cyd, 'SD_CS', 5)


def mb(n):
    return '%.1f MB' % (n / 1048576)


def bagli_mi():
    try:
        os.listdir(YOL)
        return True
    except OSError:
        return False


def kart_ac():
    """Karti dosya sistemine bakmadan acar: (nesne, aciklama) ya da (None, hata)."""
    try:
        from machine import SDCard
        sd = SDCard(slot=3, sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO), cs=Pin(CS))
        try:
            boyut = sd.info()[0]
            return sd, 'machine.SDCard, kapasite ' + mb(boyut)
        except Exception:
            return sd, 'machine.SDCard'
    except Exception as e1:
        hata = 'machine.SDCard: %s' % e1
    try:
        import sdcard
        from machine import SPI
        spi = SPI(2, baudrate=1000000, sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))
        kart = sdcard.SDCard(spi, Pin(CS))
        blok = kart.ioctl(4, 0)
        return kart, 'sdcard.py (SPI), kapasite ' + mb(blok * 512)
    except Exception as e2:
        return None, hata + ' | sdcard.py: %s' % e2


def test_yaz():
    p = YOL + '/_cyd_test.txt'
    with open(p, 'w') as f:
        f.write('CYD Studio SD testi')
    with open(p) as f:
        ok = f.read() == 'CYD Studio SD testi'
    os.remove(p)
    return ok


def ozet():
    st = os.statvfs(YOL)
    toplam = st[0] * st[2]
    bos = st[0] * st[3]
    print('dosya sistemi: toplam %s, bos %s' % (mb(toplam), mb(bos)))
    ls = os.listdir(YOL)
    print('kokte %d oge: %s' % (len(ls), ', '.join(ls[:10])))
    print('yaz/oku testi:', 'TAMAM' if test_yaz() else 'HATALI')


print('--- SD kontrol ---')
if bagli_mi() and not BICIMLE:
    print('kart zaten bagli:', YOL)
    ozet()
else:
    if bagli_mi():
        os.umount(YOL)
        print('bicimlemek icin ayrildi:', YOL)
    kart, bilgi = kart_ac()
    if kart is None:
        print('KART ALGILANMADI:', bilgi)
        print('kontrol: kart tam oturdu mu? temaslar temiz mi? baska kart dene.')
    else:
        print('kart algilandi:', bilgi)
        try:
            os.mount(kart, YOL)
            print('baglandi:', YOL)
            if BICIMLE:
                os.umount(YOL)
                raise OSError('bicimleme istendi')
            ozet()
        except OSError as e:
            if not BICIMLE:
                print('DOSYA SISTEMI TANINMADI (%s)' % e)
                print('buyuk ihtimalle exFAT ya da bozuk. BICIMLE = True yapip tekrar calistir.')
            else:
                print('FAT olarak bicimleniyor... (kapasiteye gore 10-60 sn)')
                os.VfsFat.mkfs(kart)
                os.mount(kart, YOL)
                print('bicimlendi ve baglandi:', YOL)
                ozet()
                print('NOT: karti kalici kullanmak icin RESET at. Depolama "otomatik" ise')
                print('projeler artik SD de aranir (bos gorunur) - Ayarlar > Depolama.')
print('--- bitti ---')
