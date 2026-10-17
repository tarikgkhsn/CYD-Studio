# HARICI bir LED'i ISIK SENSORU olarak kullanmak.
#
# DIKKAT - scriptte iki ayri LED geciyor, karistirma:
#   * Harici LED (GPIO22 ile GPIO27 arasinda)  -> SENSOR, isigi olcen bu
#   * Kart uzerindeki RGB LED                  -> GOSTERGE, karanlikta yanar
#
# YONTEM: LED tersten bakinca fotodiyottur. Gerilimini okumak zayif kalir,
# bunun yerine EKLEM KAPASITESININ BOSALMA SURESINI oluyoruz:
#   1. LED'i TERS kutupla (katot +3.3V, anot 0V) -> kapasite dolar
#   2. Katot pinini girise al, yuksek empedansta birak
#   3. Mantiksal 0'a dusene kadar gecen sureyi say
# Isik ne kadar cok ise bosalma o kadar HIZLI olur.
#   kucuk sure = AYDINLIK      buyuk sure = KARANLIK
#
# KABLOLAMA - iki pin kullaniyoruz, YON FARK ETMEZ:
#     LED'in bir bacagi --> GPIO22
#     LED'in obur bacagi --> GPIO27
#   Hangi bacagin nereye gittigini bilmene gerek yok: script her iki yonu
#   de deneyip dogru olani kendisi buluyor. Direnc gerekmez, LED hic
#   iletime girmiyor.
#
# En iyi sonuc: SEFFAF govdeli LED. Buzlu govde isigi dagitir, zayif olur.
from machine import Pin
import time
import cyd

PIN_A = 22
PIN_B = 27
ZAMAN_ASIMI = 250        # MILISANIYE; bunu asarsa "cok karanlik" ya da bagli degil
ORNEK = 3
ARALIK = 0.4
KALIBRASYON = 12


def olc(katot, anot, timeout_ms=ZAMAN_ASIMI):
    """LED'i ters kutuplayip bosalma suresini olcer (MILISANIYE).

    Neden sikı dongu degil de sleep_ms ile yokluyoruz: mikrosaniye
    cozunurluklu bir `while` dongusu CPU'yu birakmiyor ve web panelini
    ac birakiyor (denendi - panel cevap veremez oldu). Isik/karanlik
    ayrimi icin milisaniye fazlasiyla yeterli, sleep_ms de zamanlayiciya
    yer aciyor.
    """
    k = Pin(katot, Pin.OUT)
    a = Pin(anot, Pin.OUT)
    k.value(1)                      # katot +3.3V
    a.value(0)                      # anot 0V  -> TERS kutup
    time.sleep_us(300)              # kapasite dolsun
    k.init(Pin.IN, None)            # yuksek empedans, pull YOK
    for ms in range(timeout_ms):
        if not k.value():
            return ms
        time.sleep_ms(1)
    return timeout_ms


def yon_bul():
    """Hangi pin katot?

    Uc olasi sonuc var:
      ~0            -> LED duz kutuplandi, yon yanlis
      orta bir deger-> DOGRU yon, ters kutuplu LED
      hep ZAMAN_ASIMI -> pin BOSTA (LED o pine bagli degil)

    Bosta kalan pin de yuksek deger verdigi icin sadece "en buyugu sec"
    demek yanlisti; bosta olani ayirt etmemiz gerekiyor.
    """
    a_ol = [olc(PIN_A, PIN_B) for _ in range(5)]
    b_ol = [olc(PIN_B, PIN_A) for _ in range(5)]
    a_max, b_max = max(a_ol), max(b_ol)
    a_bos = all(x >= ZAMAN_ASIMI for x in a_ol)
    b_bos = all(x >= ZAMAN_ASIMI for x in b_ol)
    print('yon denemesi: GPIO%d katot -> %s ms | GPIO%d katot -> %s ms'
          % (PIN_A, a_ol, PIN_B, b_ol))

    if a_bos and b_bos:
        return None, None, 'BOSTA'          # iki pin de bagli degil
    if a_bos:
        return PIN_B, PIN_A, b_max          # A bosta -> B dogru olmali
    if b_bos:
        return PIN_A, PIN_B, a_max
    if a_max >= b_max:
        return PIN_A, PIN_B, a_max
    return PIN_B, PIN_A, b_max


def olc_ortanca(katot, anot):
    o = [olc(katot, anot) for _ in range(ORNEK)]
    o.sort()
    return o[len(o) // 2]


print('LED isik sensoru - GPIO%d <-> GPIO%d arasi' % (PIN_A, PIN_B))
print('yon araniyor (LED nasil bagli oldugunu kendimiz buluyoruz)...')
katot, anot, ilk = yon_bul()

if katot is None:
    print()
    print('SENSOR BAGLI DEGIL: iki pin de bosta (hep %d ms).' % ZAMAN_ASIMI)
    print('Baglanan bir pin, bosta kalan pinden farkli davranir.')
    print()
    print('  LED in bir bacagi -> GPIO%d' % PIN_A)
    print('  LED in obur bacagi -> GPIO%d' % PIN_B)
    print('  YON FARK ETMEZ, ama iki bacak da PIN e gitmeli - GND ye DEGIL.')
    print('  Direnc gerekmez.')
    raise SystemExit

print('secilen: katot GPIO%d, anot GPIO%d (%s ms)' % (katot, anot, ilk))

if ilk < 2:
    print()
    print('UYARI: iki yonde de sure ~0. LED surekli iletiyor gibi.')
    print('  - Bacaklardan biri GND ye mi gitmis? Ikisi de PIN e gitmeli.')
    print('  - Lehim/breadboard temasina bak.')
    print()

d = None
try:
    d = cyd.display()
    d.fill(cyd.BLACK)
    d.text('LED = isik sensoru', 8, 8, cyd.CYAN, cyd.BLACK, 2)
    d.text('GPIO%d <-> GPIO%d' % (PIN_A, PIN_B), 8, 34, cyd.GREY, cyd.BLACK, 1)
except Exception:
    pass

print()
print('%d olcum boyunca ortam ogreniliyor - LED i elinle kapat, sonra ac'
      % KALIBRASYON)
print('kucuk sure = aydinlik, buyuk sure = karanlik')
print()

hizli = None
yavas = None
n = 0
karanlik = False
uyarildi = False

while not cyd.should_stop():
    n += 1
    sure = olc_ortanca(katot, anot)

    hizli = sure if hizli is None else min(hizli, sure)
    yavas = sure if yavas is None else max(yavas, sure)

    # Isik ile karanlik arasinda en az 3 kat fark gormeden esik kurmuyoruz;
    # yoksa gurultuye bakip rastgele karar veririz.
    if n <= KALIBRASYON or yavas < hizli * 3 or yavas < 5:
        print('%3d) %5d ms   (ogreniliyor: %d..%d)' % (n, sure, hizli, yavas))
        if n >= KALIBRASYON and not uyarildi:
            uyarildi = True
            print()
            print('    Henuz isik/karanlik farki olusmadi. Denenecekler:')
            print('    - LED i AVUCUNLA tamamen kapat, birkac saniye tut')
            print('    - Sonra parlak bir isiga tut (telefon feneri)')
            print('    - Seffaf govdeli LED kullan, buzlu olan zayif')
            print('    - Kirmizi LED yesil/mavi isigi en iyi gorur')
            print()
        if not cyd.sleep(ARALIK):
            break
        continue

    oran = (sure - hizli) / (yavas - hizli)

    yeni = karanlik
    if not karanlik and oran > 0.62:
        yeni = True
    elif karanlik and oran < 0.38:
        yeni = False

    if yeni != karanlik:
        karanlik = yeni
        if karanlik:
            cyd.led(r=True, g=True, b=True)      # kart uzerindeki gosterge
        else:
            cyd.led_off()
        print('%3d) %5d ms  %%%-3d  -> %s' % (n, sure, oran * 100,
                                              'KARANLIK' if karanlik else 'AYDINLIK'))
    elif n % 8 == 0:
        print('%3d) %5d ms  %%%-3d  %s' % (n, sure, oran * 100,
                                           'karanlik' if karanlik else 'aydinlik'))

    if d:
        d.fill_rect(0, 60, d.width, 92, cyd.BLACK)
        renk = cyd.BLUE if karanlik else cyd.YELLOW
        d.text('KARANLIK' if karanlik else 'AYDINLIK', 8, 62, renk, cyd.BLACK, 3)
        d.text('%d ms' % sure, 8, 104, cyd.WHITE, cyd.BLACK, 2)
        d.text('%d..%d ms' % (hizli, yavas), 8, 132, cyd.GREY, cyd.BLACK, 1)

    if not cyd.sleep(ARALIK):
        break

cyd.led_off()
print()
print('durduruldu - %d olcum' % n)
if hizli is not None:
    print('gorulen aralik: %d ms (en aydinlik) .. %d ms (en karanlik)'
          % (hizli, yavas))
