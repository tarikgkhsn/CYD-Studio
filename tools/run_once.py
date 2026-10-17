"""Upload a local sample and run it once, streaming its log back.

    python tools/run_once.py net_deneme.py [seconds] [host]
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

NAME = sys.argv[1] if len(sys.argv) > 1 else 'net_deneme.py'
WAIT = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
HOST = sys.argv[3] if len(sys.argv) > 3 else '192.168.0.217'
BASE = 'http://%s' % HOST


def call(path, method='GET', body=None, timeout=25):
    if method == 'POST' and body is None:
        body = b''
    req = urllib.request.Request(BASE + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def wait_ready(limit=90):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            call('/api/status', timeout=4)
            return
        except Exception:
            time.sleep(2)
    raise SystemExit('cihaz acilmadi')


wait_ready()

path = os.path.join(ROOT, 'device', 'samples', NAME)
if os.path.exists(path):
    with open(path, 'rb') as f:
        data = f.read()
    print('yukleniyor: %s (%d bayt)' % (NAME, len(data)))
    print(' ', call('/api/save?name=%s' % NAME, 'POST', data))

print('calistiriliyor: %s' % NAME)
r = call('/api/run?name=%s' % NAME, 'POST')
print(' ', r)
if not r.get('ok'):
    sys.exit(1)

seq = 0
end = time.time() + WAIT
while time.time() < end:
    time.sleep(1.2)
    d = call('/api/log?since=%d' % seq)
    for s, src, t in d['lines']:
        seq = s
        if src == NAME:
            print('  |', t)
    st = call('/api/status')
    if not any(j['running'] and j['name'] == NAME for j in st['jobs']):
        print('  (proje bitti)')
        break
else:
    call('/api/stop?name=%s' % NAME, 'POST')
    print('  (sure doldu, durduruldu)')
