# ULN2803A ile 12 V YUK ANAHTARLAMA  -  CYD (ESP32) surumu
#
# Tasarim dokumani NodeMCU icin yazilmisti (esp8266-uln2803a-tasarim.md).
# Bu, ayni devrenin CYD uzerinde kosan hali. ELEKTRIKSEL HICBIR SEY
# DEGISMIYOR: iki kartin da lojik seviyesi 3,3 V, yani ULN giris akimi
# yine (3,3 - 1,4) / 2,7k = ~0,7 mA ve garanti yuk akimi yine 300 mA.
# Degisen tek sey pin secimi.
#
#
# KABLOLAMA
#
#     CYD GPIO27  ──────────────► ULN2803A 1B   (pin 1)
#     CYD GND     ──────┬───────► ULN2803A GND  (pin 9)
#                       └───────► 12 V kaynak (−)
#
#     12 V kaynak (+) ──┬───────► ULN2803A COM  (pin 10)
#                       └───────► Yuk (+)
#     Yuk (−)     ──────────────► ULN2803A 1C   (pin 18)
#
# Centik yukaridayken: sol sutun 1B..8B (pin 1-8) + GND (pin 9),
# sag sutun COM (pin 10) + 8C..1C (pin 11-18). 1B'nin TAM KARSISI 1C.
#
#
# NEDEN GPIO27
#
# CYD'de neredeyse her pin dolu. Bosta olanlar: 22, 27 ve 35.
# 35 SADECE GIRIS - cikis veremez, ULN surmez. Geriye 22 ve 27 kaliyor;
# ikisi de strapping pini degil, yani acilista karta karismazlar.
# Ikinci bir kanal istersen 22'yi ekle: KANALLAR = (27, 22)
#
# UYARI: 22 ve 27 ayni zamanda UART koprusunun telleri. Kopruyu
# kullanacaksan once bu projeyi durdur.
#
#
# ACILISTA YUK KENDILIGINDEN CALISIR MI
#
# Hayir. MicroPython acilana kadar GPIO27 bosta kalir, ama ULN2803A'nin
# girisinde dahili 7,2k base-emitter direnci var - bosta kalan giris
# GND'ye yakin oturur ve kanal kapali kalir. Yine de kesinlik istiyorsan
# 1B ile GND arasina 10k pull-down koy; kurusluk sigorta.
#
#
# GUVENLIK - dokumandaki maddelerin ozeti
#   * Ortak GND SART: CYD GND ile 12 V kaynagin eksisi birlesmeli
#   * 12 V'u ASLA CYD'nin 3V3 ya da GPIO pinine verme
#   * Enduktif yukte (role, motor) COM mutlaka +12 V'a bagli olmali,
#     yoksa geri EMF cikisi bozar
#   * ULN cikisi akim CEKER, VEREMEZ - 1C'den 12 V alip yuk besleyemezsin
#   * Yukun gordugu gerilim ~11 V (12 V eksi ~1 V doyma dusumu)
#   * Kanal basina 300 mA. Daha fazlasi icin kanallari paralelle
#     (1B+2B ayni GPIO'ya, 1C+2C birlesik), 1 A ustunde MOSFET'e gec.
import cyd
import time
from machine import Pin

# Surulecek ULN girisleri. Tek kanal icin (27,), iki kanal icin (27, 22).
KANALLAR = (27,)

PERIYOT = 1.0          # saniye - acik ve kapali surenin her biri
SIRALI = False         # cok kanalda: True ise sirayla yakar, False ise hepsi


pinler = [Pin(p, Pin.OUT, value=0) for p in KANALLAR]

d = None
try:
    d = cyd.display()
except Exception as e:
    print('ekran yok:', e)


def ekran(acik, tur):
    if d is None:
        return
    try:
        d.fill(cyd.BLACK)
        d.text('ULN2803A', 8, 8, cyd.GREY, cyd.BLACK, 1)
        d.text('GPIO %s' % ','.join(str(p) for p in KANALLAR),
               8, 24, cyd.GREY, cyd.BLACK, 1)
        if acik:
            d.text('YUK ACIK', 12, 70, cyd.RED, cyd.BLACK, 4)
        else:
            d.text('kapali', 12, 70, cyd.GREEN, cyd.BLACK, 4)
        d.text('tur %d' % tur, 12, 140, cyd.WHITE, cyd.BLACK, 2)
        d.text('%.1f sn periyot' % PERIYOT, 12, 176, cyd.GREY, cyd.BLACK, 1)
    except Exception:
        pass


def hepsi(deger):
    for p in pinler:
        p.value(deger)


print('ULN2803A yuk anahtarlama')
print('  kanallar : GPIO %s' % ', '.join(str(p) for p in KANALLAR))
print('  periyot  : %.1f sn acik / %.1f sn kapali' % (PERIYOT, PERIYOT))
print('  ortak GND ve COM->+12V bagli oldugundan emin ol')
print()

tur = 0
ekran(False, 0)

# try/finally SART: proje durdurulunca yuk ACIK KALMAMALI. Dokumandaki
# ciplak "while True" bunu yapmiyor - Durdur'a basinca role acik kalirdi.
try:
    while not cyd.should_stop():
        tur += 1

        if SIRALI and len(pinler) > 1:
            for i, p in enumerate(pinler):
                hepsi(0)
                p.value(1)
                print('[tur %d] kanal %d ACIK' % (tur, KANALLAR[i]))
                ekran(True, tur)
                if not cyd.sleep(PERIYOT):
                    raise KeyboardInterrupt
            hepsi(0)
            print('[tur %d] hepsi kapali' % tur)
            ekran(False, tur)
            if not cyd.sleep(PERIYOT):
                raise KeyboardInterrupt
        else:
            hepsi(1)
            print('[tur %d] YUK ACIK' % tur)
            ekran(True, tur)
            if not cyd.sleep(PERIYOT):
                raise KeyboardInterrupt

            hepsi(0)
            print('[tur %d] yuk kapali' % tur)
            ekran(False, tur)
            if not cyd.sleep(PERIYOT):
                raise KeyboardInterrupt

except KeyboardInterrupt:
    pass
finally:
    hepsi(0)
    ekran(False, tur)
    print()
    print('yuk KAPATILDI - %d tur donuldu' % tur)
