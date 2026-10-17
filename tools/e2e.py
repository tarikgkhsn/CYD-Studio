"""End-to-end check: run a project, read its log, stop it again."""
import json
import sys
import time
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else '192.168.0.217'
PROJ = sys.argv[2] if len(sys.argv) > 2 else 'ornek_led.py'
BASE = 'http://%s' % HOST


def call(path, method='GET', body=None):
    req = urllib.request.Request(BASE + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def show_log(since=0):
    r = call('/api/log?since=%d' % since)
    for seq, line in r['lines']:
        print('   |', line)
    return r['seq']


print('1) durum')
s = call('/api/status')
print('   calisiyor:', s['running'], '| ram:', s['ram_free'])

print('2) %s calistiriliyor' % PROJ)
print('  ', call('/api/run?name=%s' % PROJ, 'POST'))

seq = 0
for i in range(4):
    time.sleep(1.2)
    seq = show_log(seq)

s = call('/api/status')
print('3) durum: calisiyor=%s  sure=%ss' % (s['running'], s['seconds']))
assert s['running'], 'PROJE CALISMIYOR'

print('4) web sunucusu hala cevap veriyor mu?')
t0 = time.time()
call('/api/list')
print('   evet, %.0f ms' % ((time.time() - t0) * 1000))

print('5) durduruluyor')
print('  ', call('/api/stop', 'POST'))
for i in range(4):
    time.sleep(1.0)
    seq = show_log(seq)
    s = call('/api/status')
    if not s['running']:
        break

print('6) son durum: calisiyor=%s' % s['running'])
if s['running']:
    print('   !!! DURMADI')
    sys.exit(1)
print('\nBASARILI: calistir / log / durdur dongusu calisiyor')
