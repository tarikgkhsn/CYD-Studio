# LED'i bagladin ama yanmiyor mu? Bu, aday pinleri sirayla dener.
# Hangi adimda LED yanip sonuyorsa, o pini harici_led.py icindeki
# PIN degiskenine yaz.
#
# Konnektor pin sirasi kart revizyonuna gore degisebiliyor, bu yuzden
# tahmin etmek yerine olcuyoruz.
from machine import Pin
import cyd

# (pin, aciklama, uyari)
if hasattr(cyd, 'D1'):            # NodeMCU: D etiketleri
    ADAYLAR = (
        (cyd.D1, 'D1 (GPIO5)', ''),
        (cyd.D2, 'D2 (GPIO4)', ''),
        (cyd.D5, 'D5 (GPIO14)', ''),
        (cyd.D6, 'D6 (GPIO12)', ''),
        (cyd.D7, 'D7 (GPIO13)', ''),
    )
else:                             # CYD
    ADAYLAR = (
        (22, 'Extended IO - normal aday', ''),
        (27, 'Sicaklik/nem konnektoru', ''),
        (21, 'ekran arka aydinlatmasi', 'EKRAN TITREYECEK - bu normal'),
    )

TEKRAR = 6          # her pinde kac kez yanip sonsun
HIZ = 0.35

d = None
try:
    d = cyd.display()
except Exception:
    pass

print('LED bagli pini ariyoruz. Her adimda LED\'e bak.')
print('GPIO35 test EDILMIYOR - o pin sadece giris, cikis veremez.\n')

for pin_no, aciklama, uyari in ADAYLAR:
    if cyd.should_stop():
        break

    print('--- GPIO %d  (%s)' % (pin_no, aciklama))
    if uyari:
        print('    %s' % uyari)

    if d and pin_no != 21:
        d.fill(cyd.BLACK)
        d.text('Deneniyor', 10, 30, cyd.WHITE, cyd.BLACK, 2)
        d.text('GPIO %d' % pin_no, 10, 60, cyd.YELLOW, cyd.BLACK, 4)
        d.text('LED yaniyor mu?', 10, 120, cyd.GREY, cyd.BLACK, 2)

    try:
        p = Pin(pin_no, Pin.OUT)
    except Exception as e:
        print('    pin acilamadi: %s' % e)
        continue

    for i in range(TEKRAR):
        if cyd.should_stop():
            break
        p.value(1)
        if not cyd.sleep(HIZ):
            break
        p.value(0)
        if not cyd.sleep(HIZ):
            break

    p.value(1 if pin_no == 21 else 0)   # arka aydinlatmayi acik birak
    print('    bitti\n')

    if not cyd.sleep(1.0):
        break

if d:
    d.fill(cyd.BLACK)
    d.text('Tarama bitti', 10, 100, cyd.WHITE, cyd.BLACK, 3)

print('Tarama bitti.')
print('LED hangi adimda yanip sondu ise o GPIO numarasini kullan.')
print('Hicbirinde yanmadiysa: kablolamaya bak (uzun bacak dirence,')
print('kisa bacak GND ye) ya da LED ters bagli olabilir.')
