# CIPLAK MICROPYTHON WIFI TESTI
#
# Bizim sistemimizden tek satir yok: ne server, ne jobs, ne cyd.
# Sadece MicroPython'un kendi network modulu. Burada da cokerse
# sorunun yazilimla ilgisi olmadigi kesinlesir.
import machine
import network
import time

SEBEP = {1: 'guc verildi', 2: 'harici reset', 3: 'yazilim reset',
         4: 'WATCHDOG', 5: 'derin uyku', 6: 'BROWNOUT (dusuk voltaj)'}

print('=== CIPLAK WIFI TESTI ===')
print('son acilis sebebi:', SEBEP.get(machine.reset_cause(), machine.reset_cause()))
print('frekans:', machine.freq() // 1000000, 'MHz')
print()

print('[1] WLAN nesnesi olusturuluyor (radyo henuz kapali)')
w = network.WLAN(network.STA_IF)
time.sleep(1)
print('    tamam')

print()
print('[2] w.active(True)  <-- BROWNOUT HEP BURADA OLUYORDU')
print('    bu satirdan sonra yazi gelmezse donanim kesinlesir')
time.sleep(0.5)
w.active(True)
print('    RADYO ACILDI - HAYATTAYIZ')

print()
print('[3] 5 saniye radyo acik bosta bekleniyor')
for i in range(1, 6):
    time.sleep(1)
    print('    %d sn ayakta' % i)

print()
print('[4] aglar taraniyor (verici calisiyor)')
try:
    aglar = w.scan()
    print('    %d ag bulundu' % len(aglar))
except Exception as e:
    print('    tarama hatasi:', e)

print()
print('[5] baglaniliyor')
w.connect('WIFI_ADINIZ', 'WIFI_SIFRESI')   # kendi aginizi yazin
for i in range(25):
    if w.isconnected():
        print('    BAGLANDI:', w.ifconfig()[0])
        break
    if i % 3 == 0:
        print('    bekleniyor %d sn (durum %s)' % (i, w.status()))
    time.sleep(1)
else:
    print('    baglanamadi, durum:', w.status())

print()
print('[6] 20 saniye baglantida bekleniyor')
for i in range(1, 21):
    time.sleep(1)
    if i % 5 == 0:
        try:
            print('    %2d sn ayakta, rssi %s' % (i, w.status('rssi')))
        except Exception:
            print('    %2d sn ayakta' % i)

print()
print('SONUC: CIPLAK MICROPYTHON ILE WIFI CALISIYOR.')
print('Demek ki sorun bizim sistemimizde, donanimda degil.')
