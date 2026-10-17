# ULN2803A - EKRANSIZ HIZLI ANAHTARLAMA  (varsayilan 10 Hz)
#
# uln2803_yuk.py'nin sade kardesi: ekran yok, saniyede 10 kez yakip sonduruyor.
#
# NEDEN EKRANSIZ
#   Ekran her cizimde SPI'ya veri basar ve dahili DRAM'den yer tutar.
#   10 Hz'de her gecise cizim koymak hem gereksiz hem de zamanlamayi
#   bozardi. Burada ekrana hic dokunulmuyor.
#
# NEDEN HER GECISI LOGLAMIYORUZ
#   10 Hz = saniyede 20 durum degisimi. Panelin log hizi 12 satir/sn
#   (jobs.LOG_RATE) - fazlasi dusuruluyor ve "atlanan satir" uyarisi
#   cikiyor. Bu yuzden her gecis yerine SANIYEDE BIR ozet basiyoruz.
#
# KABLOLAMA - uln2803_yuk.py ile ayni
#
#     CYD GPIO27  ──────────────► ULN2803A 1B   (pin 1)
#     CYD GND     ──────┬───────► ULN2803A GND  (pin 9)
#                       └───────► 12 V kaynak (−)
#
#     12 V (+)    ──────┬───────► ULN2803A COM  (pin 10)
#                       └───────► Yuk (+)
#     Yuk (−)     ──────────────► ULN2803A 1C   (pin 18)   <-- BURASI KRITIK
#
# Yukun eksisi ADAPTORUN EKSISINE DEGIL, 1C'ye gidecek. Adaptorun eksisine
# baglarsan devre zaten kapali olur ve ULN'nin yapacagi bir sey kalmaz -
# yuk surekli yanik kalir.
#
# Centik ASAGI bakarken: GPIO27'nin girdigi pin sag-alttadir (1B),
# 1C ise onun TAM KARSISI, yani SOL-ALT.
#
# CIPLAK LED KULLANIYORSAN SERI DIRENC SART
#   12 V'a dogrudan bagli bir LED yanar. ULN'nin ~1,1 V doyma dusumunu de
#   sayarsak 20 mA icin:  (12 − 2 − 1,1) / 0,02 = ~445 Ω  ->  470 Ω kullan.
#   Uzerinde direnci olan 12 V LED modul/serit ise gerek yok.
#
# HIZ SINIRI
#   ULN2803A Darlington'dur, kapanmasi acilmasindan yavastir. 10 Hz cok
#   rahat; birkac yuz Hz'e kadar sorunsuz calisir, PWM ile karartma da
#   yapilabilir. Onun ustune cikacaksan MOSFET'e gec.
import cyd
import time
from machine import Pin

KANALLAR = (27,)       # ikinci kanal istersen (27, 22)
HZ = 10                # saniyede kac kez yanip sonsun
RAPOR_SN = 1           # loga kac saniyede bir ozet basilsin

YARIM_MS = max(1, int(500 / HZ))       # 10 Hz -> 50 ms acik, 50 ms kapali

pinler = [Pin(p, Pin.OUT, value=0) for p in KANALLAR]


def hepsi(deger):
    for p in pinler:
        p.value(deger)


print('ULN2803A hizli anahtarlama - EKRANSIZ')
print('  kanallar : GPIO %s' % ', '.join(str(p) for p in KANALLAR))
print('  hiz      : %d Hz  (%d ms acik / %d ms kapali)'
      % (HZ, YARIM_MS, YARIM_MS))
print('  log      : her gecis degil, %d saniyede bir ozet' % RAPOR_SN)
print()

tur = 0
acik = False
basla = time.ticks_ms()
son_rapor = basla
# Sabit hedef zamanla ilerliyoruz; her turda sleep eklemek kayma biriktirir.
sonraki = time.ticks_ms()

try:
    while not cyd.should_stop():
        acik = not acik
        hepsi(1 if acik else 0)
        if acik:
            tur += 1

        sonraki = time.ticks_add(sonraki, YARIM_MS)
        kalan = time.ticks_diff(sonraki, time.ticks_ms())
        if kalan > 0:
            if not cyd.sleep(kalan / 1000):
                break
        else:
            # Geride kaldik (baska proje CPU aldi) - hedefi simdiye cek,
            # yoksa acigi kapatmak icin cilgin gibi donmeye calisir.
            sonraki = time.ticks_ms()

        simdi = time.ticks_ms()
        if time.ticks_diff(simdi, son_rapor) >= RAPOR_SN * 1000:
            gecen = time.ticks_diff(simdi, basla) / 1000
            print('%6.0f sn   %d tur   %.1f Hz'
                  % (gecen, tur, tur / gecen if gecen else 0))
            son_rapor = simdi

finally:
    hepsi(0)
    gecen = time.ticks_diff(time.ticks_ms(), basla) / 1000
    print()
    print('yuk KAPATILDI - %d tur / %.1f sn (%.1f Hz)'
          % (tur, gecen, tur / gecen if gecen else 0))
