"""Verify the Stop button survives a project that ignores it.

Uploads a tight loop that never polls should_stop(), presses Stop, and
checks the board hard-resets and comes back serving on its own.
"""
import json
import sys
import time
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else '192.168.0.217'
BASE = 'http://%s' % HOST

RUNAWAY = b"""# durdurma sinyalini kasten yok sayar
import time
i = 0
while True:
    i += 1
    if i % 200000 == 0:
        print('inatci dongu', i)
    time.sleep_ms(1)
"""


def call(path, method='GET', body=None, timeout=15):
    req = urllib.request.Request(BASE + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except ValueError:
        return raw


print('1) inatci proje yukleniyor')
print('  ', call('/api/save?name=inatci.py', 'POST', RUNAWAY))

print('2) calistiriliyor')
print('  ', call('/api/run?name=inatci.py', 'POST'))
time.sleep(3)
s = call('/api/status')
print('   calisiyor:', s['running'])

print('3) DURDUR basiliyor (proje dinlemiyor -> zorla reset beklenir)')
try:
    print('  ', call('/api/stop', 'POST'))
except Exception as e:
    print('   stop cagrisi kesildi (beklenebilir):', e)

print('4) cihazin geri gelmesi bekleniyor...')
t0 = time.time()
back = False
while time.time() - t0 < 60:
    try:
        s = call('/api/status', timeout=3)
        if not s['running'] and s['uptime'] < 40:
            back = True
            break
    except Exception:
        pass
    time.sleep(1)

if not back:
    print('   !!! cihaz 60s icinde geri gelmedi')
    sys.exit(1)

print('   geri geldi: %.0f saniyede, uptime=%ss, calisan proje=%s'
      % (time.time() - t0, s['uptime'], s['name']))
print('5) temizlik')
print('  ', call('/api/delete?name=inatci.py', 'POST'))
print('\nBASARILI: durdur butonu inatci projede de calisiyor')
