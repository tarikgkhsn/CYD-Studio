# Network ornegi: WiFi zaten acilista bagli, projede tekrar baglanma.
#
# Not: HTTPS normal modda ENOMEM verir (TLS ~40-50 KB bitisik dahili DRAM
# ister, panel aciken ~30 KB kalir). Duz HTTP ve NTP sorunsuz calisir.
# HTTPS gerekiyorsa arayuzdeki "Solo" dugmesiyle calistir.
import requests
import cyd

wlan = cyd.wifi()
print('bagli    :', wlan.isconnected())
print('ip       :', wlan.ifconfig()[0])
print('sinyal   :', wlan.status('rssi'), 'dBm')
print('bos DRAM : %d KB' % (cyd.dram() // 1024))

# --- saat: NTP guvenilir, HTTP saat servislerinden daha az kirilgan
try:
    import ntptime
    import time
    ntptime.settime()
    y, m, d, h, mi, s = time.localtime()[:6]
    print('NTP saat : %04d-%02d-%02d %02d:%02d:%02d UTC' % (y, m, d, h, mi, s))
except Exception as e:
    print('NTP hata :', e)

sayac = 0
while not cyd.should_stop():
    sayac += 1
    try:
        r = requests.get('http://example.com', timeout=10)
        print('%d) HTTP %s, %d bayt' % (sayac, r.status_code, len(r.text)))
        r.close()
    except Exception as e:
        print('%d) istek basarisiz: %s' % (sayac, e))

    if not cyd.sleep(10):
        break

print('network ornegi bitti')
