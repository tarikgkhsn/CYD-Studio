# BLE ornegi - SOLO modda calistir!
#
# Panel acikken bos dahili DRAM ~30 KB olur ve BLE acilmaz (EIO).
# Arayuzdeki "Solo" dugmesi paneli kapatip ~88 KB birakir; BLE o zaman acilir.
# Telefonundan "nRF Connect" gibi bir uygulamayla CYD-BLE adini gorursun.
import bluetooth
import cyd

print('bos dahili DRAM: %d KB' % (cyd.dram() // 1024))
if cyd.dram() < 60 * 1024:
    print('UYARI: DRAM az. Panel aciksa BLE acilmaz - "Solo" ile calistir.')

ble = bluetooth.BLE()
ble.active(True)
mac = ble.config('mac')[1]
print('BLE acildi, mac:', ':'.join('%02X' % b for b in mac))

AD = 'CYD-BLE'
ad = bytearray()
ad += bytes((2, 0x01, 0x06))                       # flags: genel kesfedilebilir
isim = AD.encode()
ad += bytes((len(isim) + 1, 0x09)) + isim          # tam yerel isim

ble.gap_advertise(100000, adv_data=ad)
print('yayin basladi: "%s" - telefondan tarayabilirsin' % AD)

sayac = 0
while not cyd.should_stop():
    sayac += 1
    if sayac % 10 == 0:
        print('yayinda... %d sn  (bos DRAM %d KB)'
              % (sayac, cyd.dram() // 1024))
    if not cyd.sleep(1):
        break

ble.gap_advertise(None)
ble.active(False)
print('BLE kapatildi')
