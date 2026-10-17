"""Confirm a project can reach the internet on its own."""
import json
import sys
import time
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else '192.168.0.217'
BASE = 'http://%s' % HOST
PROJ = 'ornek_network.py'


def call(path, method='GET', timeout=20):
    req = urllib.request.Request(BASE + path,
                                 data=(b'' if method == 'POST' else None),
                                 method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def wait_ready(limit=90):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            s = call('/api/status', timeout=4)
            print('   hazir (%.0f sn, uptime %ss)' % (time.time() - t0,
                                                      s['sys']['uptime']))
            return s
        except Exception:
            time.sleep(2)
    raise SystemExit('cihaz %ds icinde acilmadi' % limit)


print('0) cihaz bekleniyor')
wait_ready()

print('1) %s calistiriliyor' % PROJ)
print('  ', call('/api/run?name=%s' % PROJ, 'POST'))

print('2) 25 sn boyunca izleniyor')
time.sleep(25)

d = call('/api/log?since=0')
lines = [t for _, src, t in d['lines'] if src == PROJ]
for t in lines:
    print('   |', t)

st = call('/api/status')
print('3) calisan:', [j['name'] for j in st['jobs'] if j['running']])
print('  ', call('/api/stop?name=%s' % PROJ, 'POST'))

basarili = any('saat:' in t for t in lines)
print('\n%s' % ('BASARILI: proje icinden internete cikildi'
                if basarili else
                '!!! HTTP istegi sonuc vermedi - loglara bak'))
sys.exit(0 if basarili else 1)
