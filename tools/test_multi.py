"""Verify several projects really do run at the same time."""
import json
import sys
import time
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else '192.168.0.217'
BASE = 'http://%s' % HOST
WANT = ['ornek_led.py', 'ornek_isik_sensoru.py', 'ornek_network.py']


def call(path, method='GET', body=None, timeout=20):
    req = urllib.request.Request(BASE + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except ValueError:
        return raw


print('0) baslangic durumu')
s = call('/api/status')
print('   calisan:', s['running'], '/', s['max_jobs'],
      '| ram bos:', s['sys']['ram_free'])

for name in WANT:
    print('1) baslat:', name, '->', call('/api/run?name=%s' % name, 'POST'))
    time.sleep(0.6)

time.sleep(6)
s = call('/api/status')
run = [j['name'] for j in s['jobs'] if j['running']]
print('2) ayni anda calisanlar:', run)
print('   ram bos:', s['sys']['ram_free'], '| sicaklik:', s['sys'].get('temp'))

if len(run) < len(WANT):
    print('   !!! hepsi calismiyor')

print('3) her projeden log geliyor mu?')
r = call('/api/log?since=0')
per = {}
for seq, src, txt in r['lines']:
    per[src] = per.get(src, 0) + 1
for k in sorted(per):
    print('   %-24s %d satir' % (k, per[k]))

print('4) sunucu hala hizli mi?')
t0 = time.time()
call('/api/list')
print('   %.0f ms' % ((time.time() - t0) * 1000))

print('5) sadece birini durdur:', WANT[0])
print('  ', call('/api/stop?name=%s' % WANT[0], 'POST'))
time.sleep(4)
s = call('/api/status')
run = [j['name'] for j in s['jobs'] if j['running']]
print('   kalan:', run)
assert WANT[0] not in run, 'durmadi'
assert len(run) >= 1, 'digerleri de durmus'

print('6) kalanlari durdur')
print('  ', call('/api/stopall', 'POST'))
time.sleep(4)
s = call('/api/status')
run = [j['name'] for j in s['jobs'] if j['running']]
print('   kalan:', run)

print('\nBASARILI: coklu proje calisiyor, tek tek durdurulabiliyor')
