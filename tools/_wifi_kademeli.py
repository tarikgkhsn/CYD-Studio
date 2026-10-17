# Kart uzerinde calisir: WiFi'yi kademe kademe acip TAM OLARAK nerede
# coktugunu bulur. Kart resetlenirse en son basilan satir bize yeri soyler.
#
# Her adimda akimi dusurmeye calisiyoruz:
#   - islemci 80 MHz
#   - verici gucu en dusuk
#   - modem power save acik
#   - adimlar arasi bekleme (kondansatorler toparlansin)
import machine
import network
import time

SEBEP = {1: 'guc verildi', 2: 'harici reset', 3: 'yazilim reset',
         4: 'WATCHDOG', 5: 'derin uyku', 6: 'BROWNOUT'}

print('=== KADEMELI WIFI TESTI ===')
print('son acilis:', SEBEP.get(machine.reset_cause(), machine.reset_cause()))

print('[1] islemci 80 MHz')
machine.freq(80000000)
time.sleep(1)

print('[2] STA arayuzu olusturuluyor')
wlan = network.WLAN(network.STA_IF)
time.sleep(1)

print('[3] radyo aciliyor (ILK BUYUK AKIM BURADA)')
wlan.active(True)
time.sleep(2)
print('    radyo acildi, hayattayiz')

print('[4] verici gucu dusuruluyor')
for guc in (8, 10, 11, 13):
    try:
        wlan.config(txpower=guc)
        print('    txpower =', guc, 'dBm kabul edildi')
        break
    except Exception as e:
        print('    txpower', guc, 'olmadi:', e)
time.sleep(1)

print('[5] modem power save aciliyor')
try:
    wlan.config(pm=network.WLAN.PM_POWERSAVE)
    print('    power save acik')
except Exception as e:
    print('    power save ayarlanamadi:', e)
time.sleep(1)

print('[6] statik IP')
try:
    wlan.ifconfig(('192.168.0.216', '255.255.255.0',
                   '192.168.1.1', '192.168.1.1'))
    print('    statik ip verildi')
except Exception as e:
    print('    ifconfig hatasi:', e)
time.sleep(1)

print('[7] BAGLANILIYOR (IKINCI BUYUK AKIM BURADA)')
wlan.connect('WIFI_ADINIZ', 'WIFI_SIFRESI')   # kendi aginizi yazin

for i in range(30):
    if wlan.isconnected():
        print('    BAGLANDI:', wlan.ifconfig()[0])
        break
    if i % 3 == 0:
        print('    bekleniyor... %d sn (durum %s)' % (i, wlan.status()))
    time.sleep(1)
else:
    print('    baglanamadi, durum:', wlan.status())

print()
print('[8] 30 saniye baglantida bekleniyor (surekli akim testi)')
for i in range(1, 31):
    if i % 5 == 0:
        try:
            print('    %2d sn  ayakta  rssi %s' % (i, wlan.status('rssi')))
        except Exception:
            print('    %2d sn  ayakta' % i)
    time.sleep(1)

print()
print('HEPSI GECTI - bu ayarlarla kart WiFi ile ayakta kalabiliyor.')
