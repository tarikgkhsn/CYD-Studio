# Kart uzerindeki RGB LED'i sirayla yakar.
# Durdur'a basinca temiz sekilde cikar.
import cyd

sira = (('kirmizi', True, False, False),
        ('yesil',   False, True, False),
        ('mavi',    False, False, True),
        ('mor',     True, False, True),
        ('sari',    True, True, False),
        ('beyaz',   True, True, True))

print('LED donguse basladi')

while not cyd.should_stop():
    for ad, r, g, b in sira:
        if cyd.should_stop():
            break
        cyd.led(r, g, b)
        print('renk:', ad)
        if not cyd.sleep(0.4):
            break

cyd.led_off()
print('LED kapatildi')
