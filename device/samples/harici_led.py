# Extended IO konnektorune bagli harici LED'i yakip sondurur.
#
# KABLOLAMA:
#   GPIO22 --[ 220 ohm ]--|>|-- GND
#                        LED    (uzun bacak = anot, dirence bakar)
#
# DIRENC ZORUNLU. Direncsiz LED 100 mA+ ceker, ESP32 pini 12 mA icindir.
#
# Extended IO konnektorundeki diger pinler:
#   GPIO35 -> sadece GIRIS, cikis veremez, LED yakmaz
#   GPIO21 -> ekranin arka aydinlatmasi, dokunma
from machine import Pin
import cyd

# CYD: GPIO22 (Extended IO). NodeMCU: D1 (GPIO5) - cyd.D1 varsa o kart.
# ESP8266'da 22 diye pin yok, 'invalid pin' verir (10 Eyl 2026'da goruldu).
PIN = getattr(cyd, 'D1', 22)   # LED'in bagli oldugu pin
SANIYE = 0.5        # yanik ve sonuk sureleri
EKRANA_YAZ = True   # durumu ekranda da goster

led = Pin(PIN, Pin.OUT)
led.value(0)

d = None
if EKRANA_YAZ:
    try:
        d = cyd.display()
        d.fill(cyd.BLACK)
        d.text('Harici LED', 10, 10, cyd.CYAN, cyd.BLACK, 3)
        d.text('GPIO %d' % PIN, 10, 48, cyd.WHITE, cyd.BLACK, 2)
    except Exception as e:
        print('ekran kullanilamadi:', e)

print('GPIO %d uzerinde LED yanip sonuyor (%.1f sn)' % (PIN, SANIYE))

sayac = 0
try:
    while not cyd.should_stop():
        sayac += 1
        led.value(1)
        print('%4d  YANIK' % sayac)
        if d:
            d.fill_rect(10, 90, 200, 60, cyd.GREEN)
            d.text('YANIK', 24, 108, cyd.BLACK, cyd.GREEN, 3)
        if not cyd.sleep(SANIYE):
            break

        led.value(0)
        print('%4d  sonuk' % sayac)
        if d:
            d.fill_rect(10, 90, 200, 60, cyd.BLACK)
            d.text('sonuk', 24, 108, cyd.GREY, cyd.BLACK, 3)
        if not cyd.sleep(SANIYE):
            break
finally:
    led.value(0)          # Durdur'a basildiginda LED yanik kalmasin
    if d:
        d.fill_rect(10, 90, 200, 60, cyd.BLACK)
        d.text('durdu', 24, 108, cyd.RED, cyd.BLACK, 3)

print('%d kez yanip sondu, LED kapatildi' % sayac)
