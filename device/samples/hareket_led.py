# PIR HAREKET -> LED   (NodeMCU / ESP8266 icin, CYD'de de calisir)
#
# NEDEN BU KART: PIR modulu (HC-SR501 sinifi) 5 V istiyor - veri sayfasi
# 5-20 V diyor. NodeMCU'nun VIN pini USB'nin 5 V'unu tasiyor, yani ayri
# kaynak, ayri toprak derdi yok. CYD'de 5 V ayni konnektorde TX/RX ile
# yan yana oldugu icin orasi darlik yapiyordu.
#
# KABLOLAMA
#     PIR VCC ---- VIN      (bazi LoLin kartlarda "VU" yazar - USB 5 V)
#     PIR GND ---- GND
#     PIR OUT ---- D1       (GPIO5 - giris icin guvenli, boot pini degil)
#     LED     ---- kablo YOK, kartin uzerindeki mavi LED kullaniliyor
#
# ONCE OLCUM: VIN'i multimetreyle olc, ~5 V gormelisin. 4 V civariysa o
# pin USB'ye degil regulator girisine bagliymis demektir; o zaman PC'nin
# USB kablosundan kirmizi(+5V)/siyah(GND) al.
#
# LED DILI  (panel solo modda kapali olacagi icin geri bildirim LED'den)
#     hizli yanip sonme  -> isiniyor, bekle
#     uzun bir flas      -> hazir
#     sonuk              -> sakin
#     sabit yanik        -> HAREKET
#
# NOT: modulun cikisi en az 5 saniye yuksek kalir (Tx potunun minimumu).
# Daha kisa gorursen besleme spec altinda demektir, potla duzelmez.
import cyd
import time

try:
    PIN = cyd.D1                 # NodeMCU
except AttributeError:
    PIN = 27                     # CYD'de calistirilirsa

from machine import Pin

ISINMA_SN = 45
p = Pin(PIN, Pin.IN)


def led(ac):
    try:
        cyd.led(ac, ac, ac)
    except Exception:
        pass


# ---- isinma: bu sensorler enerji verilince 30-60 sn yalanci tetikler
print('PIR isiniyor - %d sn (LED hizli yanip soner)' % ISINMA_SN)
basla = time.ticks_ms()
while not cyd.should_stop():
    if time.ticks_diff(time.ticks_ms(), basla) >= ISINMA_SN * 1000:
        break
    led(True)
    if not cyd.sleep(0.12):
        break
    led(False)
    if not cyd.sleep(0.12):
        break

# hazir isareti: uzun bir flas
led(True)
cyd.sleep(0.8)
led(False)

# ---- dinlenme durumunu OGREN, varsayma: bazi moduller bosta 0, bazilari 1
ornek = []
for _ in range(40):
    ornek.append(p.value())
    cyd.sleep(0.02)
dinlenme = 1 if sum(ornek) > 20 else 0
print('dinlenme durumu: %d' % dinlenme)
if 0 < sum(ornek) < 40:
    print('UYARI: pin isinmadan sonra da oynuyor - kablo gevsek olabilir')

print('hazir - sensorun onunden gec')

sayac = 0
onceki = dinlenme
yukseldi = 0
son_tetik = 0
gecmis = []
izleme = time.ticks_ms()

while not cyd.should_stop():
    simdi = time.ticks_ms()
    v = p.value()

    if v != onceki:
        onceki = v
        if v != dinlenme:
            sayac += 1
            yukseldi = simdi
            gecmis.append(simdi)
            led(True)
            ara = ''
            if son_tetik:
                ara = '  (onceki tetiklemeden %.1f sn sonra)' % (
                    time.ticks_diff(simdi, son_tetik) / 1000)
            son_tetik = simdi
            print('[%4d sn] HAREKET #%d%s'
                  % (time.ticks_diff(simdi, izleme) // 1000, sayac, ara))
        else:
            led(False)
            sure = time.ticks_diff(simdi, yukseldi) / 1000
            print('[%4d sn] bitti     %.1f sn surdu%s'
                  % (time.ticks_diff(simdi, izleme) // 1000, sure,
                     '   <-- 5 sn ALTI: besleme yetersiz' if sure < 4.5 else ''))

    # son dakikadaki tetikleme sayisi - kimse yokken 0 olmali
    gecmis = [t for t in gecmis if time.ticks_diff(simdi, t) < 60000]

    cyd.sleep(0.03)

led(False)
print()
print('SONUC: %d tetikleme' % sayac)
