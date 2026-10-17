# Otomatik gece lambasi: isik sensoru karanlik gorunce LED yanar.
#
# Isik sensoru bir GIRIStir - yakip sondurulemez, olcum yapar. Yakilip
# sondurulen sey LED. Bu proje ikisini birlestiriyor.
#
# Her iki kartta da calisir; olcek farkini kendisi ogrenir:
#   CYD      -> kart uzerinde LDR var, 0..4095 okur
#   NodeMCU  -> A0 pinine LDR baglaman gerek, 0..1023 okur
#
# NodeMCU icin kablolama (gerilim bolucu):
#     3.3V ---[ LDR ]--- A0 ---[ 10k ]--- GND
#   Aydinlikta LDR direnci duser, A0 gerilimi YUKSELIR.
import cyd

ARALIK = 0.3          # kac saniyede bir olcum
KALIBRASYON = 8       # ilk kac olcumde esik ogrenilsin
HISTEREZIS = 0.12     # esigin etrafinda %12 olu bant (LED titremesin)

print('gece lambasi basladi')
print('%d olcum boyunca ortam ogreniliyor - sensoru elinle kapatip ac' % KALIBRASYON)

dusuk = None          # gorulen en karanlik deger
yuksek = None         # gorulen en aydinlik deger
yanik = False
n = 0

while not cyd.should_stop():
    n += 1
    try:
        ham = cyd.light()
    except OSError as e:
        print('sensor okunamadi:', e)
        print('bu kartta isik sensoru olmayabilir - cyd.light() destekli mi bak')
        break

    # Olcegi kendimiz ogreniyoruz: kartlar farkli araliklar donduruyor ve
    # ortam isigi da her yerde ayni degil. Sabit esik yazmak yerine
    # gordugumuz en dusuk/en yuksek degerden esik uretiyoruz.
    dusuk = ham if dusuk is None else min(dusuk, ham)
    yuksek = ham if yuksek is None else max(yuksek, ham)

    if n <= KALIBRASYON or yuksek - dusuk < 20:
        print('%3d) ham=%-5d  (ogreniliyor: %d..%d)' % (n, ham, dusuk, yuksek))
        if not cyd.sleep(ARALIK):
            break
        continue

    # 0.0 = gordugu en karanlik, 1.0 = gordugu en aydinlik
    oran = (ham - dusuk) / (yuksek - dusuk)
    esik = 0.5

    if not yanik and oran < esik - HISTEREZIS:
        yanik = True
        cyd.led(r=True, g=True, b=True)
        print('%3d) ham=%-5d  %%%-3d  KARANLIK -> LED YANDI' % (n, ham, oran * 100))
    elif yanik and oran > esik + HISTEREZIS:
        yanik = False
        cyd.led_off()
        print('%3d) ham=%-5d  %%%-3d  AYDINLIK -> LED SONDU' % (n, ham, oran * 100))
    elif n % 10 == 0:
        print('%3d) ham=%-5d  %%%-3d  %s' % (n, ham, oran * 100,
                                             'yanik' if yanik else 'sonuk'))

    if not cyd.sleep(ARALIK):
        break

cyd.led_off()
print('durduruldu - %d olcum yapildi' % n)
if dusuk is not None:
    print('gorulen aralik: %d .. %d' % (dusuk, yuksek))
