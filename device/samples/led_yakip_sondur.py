# Kart uzerindeki LED'i yakip sondurur. HICBIR SEY BAGLAMAYA GEREK YOK.
#
# NodeMCU : GPIO2'deki mavi LED (ters mantik - cyd.led() hallediyor)
# CYD     : kart uzerindeki RGB LED
#
# Bu kartta proje SOLO calisir: panel kapali kalir, cikti kalici loga
# yazilir. Durdurmak icin karta RESET tusuna bas - panel geri gelir ve
# "Kayitli log" ile burada ne oldugunu gorursun.
import cyd

SANIYE = 0.5        # yanik ve sonuk sureleri
LOG_HER = 10        # kac yanip sonmede bir loga yazsin

print('LED yanip sonmeye basladi (%.1f sn araliklarla)' % SANIYE)
print('durdurmak icin karta RESET at')

n = 0
try:
    while not cyd.should_stop():
        n += 1

        cyd.led(g=True)                 # yak
        if not cyd.sleep(SANIYE):
            break

        cyd.led_off()                   # sondur
        if not cyd.sleep(SANIYE):
            break

        # Her yanip sonmeyi yazmak log dosyasini bosuna doldurur
        if n % LOG_HER == 0:
            print('%d kez yanip sondu' % n)
finally:
    cyd.led_off()                       # cikarken LED yanik kalmasin

print('durduruldu - toplam %d kez yanip sondu' % n)
