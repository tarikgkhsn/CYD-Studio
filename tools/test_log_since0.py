"""Pin the failure down: is it /api/log?since=0 on a full buffer?

Fills the ring buffer by letting the noisy project run, then asks for the
whole log the way a freshly opened browser tab does.
"""
import json
import sys
import time
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else '192.168.0.217'
BASE = 'http://%s' % HOST
PROJ = 'hizli_led.py'


def call(path, method='GET', body=None, timeout=20):
    if method == 'POST' and body is None:
        body = b''
    req = urllib.request.Request(BASE + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


print('1) log tamponu dolduruluyor (proje 20 satir/sn yaziyor)')
try:
    call('/api/run?name=%s' % PROJ, 'POST')
except Exception as e:
    print('   (zaten calisiyor olabilir: %s)' % e)

for i in range(6):
    time.sleep(5)
    try:
        d = json.loads(call('/api/status', timeout=8))
        print('   %2d sn  log seq=%-6d python RAM=%d KB  dram=%d KB'
              % ((i + 1) * 5, d['seq'], d['sys']['ram_free'] / 1024,
                 d['sys']['idf']['free'] / 1024))
    except Exception as e:
        print('   %2d sn  durum alinamadi: %s' % ((i + 1) * 5, e))

print('\n2) tarayici sayfayi yeni acmis gibi: /api/log?since=0')
for deneme in range(1, 6):
    t0 = time.time()
    try:
        raw = call('/api/log?since=0', timeout=20)
        ms = (time.time() - t0) * 1000
        j = json.loads(raw)
        print('   deneme %d: OK  %.0f ms  %d bayt  %d satir'
              % (deneme, ms, len(raw), len(j['lines'])))
    except Exception as e:
        ms = (time.time() - t0) * 1000
        print('   deneme %d: HATA %.0f ms  %s' % (deneme, ms, e))
    time.sleep(1)

print('\n3) ayni anda kucuk istek hala calisiyor mu?')
for deneme in range(1, 4):
    t0 = time.time()
    try:
        call('/api/status', timeout=8)
        print('   status OK  %.0f ms' % ((time.time() - t0) * 1000))
    except Exception as e:
        print('   status HATA: %s' % e)
    time.sleep(1)

print('\n4) proje durduruluyor')
try:
    print('  ', json.loads(call('/api/stop?name=%s' % PROJ, 'POST')))
except Exception as e:
    print('   hata:', e)
