"""Reproduce the panel dying, this time with the browser's real load.

The web UI polls /api/log every 0.9 s and /api/status every 2 s. The
server is single threaded, so those requests compete with a project that
is drawing to the screen and printing 20 lines a second. Earlier tests
only polled status twice as slowly and never reproduced the failure.

Two simulated tabs can be requested to match a user who left the panel
open in more than one place.
"""
import json
import sys
import threading
import time
import urllib.request

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM3'
HOST = sys.argv[2] if len(sys.argv) > 2 else '192.168.0.217'
TABS = int(sys.argv[3]) if len(sys.argv) > 3 else 1
SECS = float(sys.argv[4]) if len(sys.argv) > 4 else 70.0
BASE = 'http://%s' % HOST
PROJ = 'hizli_led.py'


def call(path, method='GET', body=None, timeout=8):
    if method == 'POST' and body is None:
        body = b''
    req = urllib.request.Request(BASE + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except ValueError:
        return raw


stop = threading.Event()
stats = {'ok': 0, 'fail': 0, 'slow': 0, 'max_ms': 0.0, 'first_fail': None}
lock = threading.Lock()
t_start = [0.0]


def record(ms, ok):
    with lock:
        if ok:
            stats['ok'] += 1
            stats['max_ms'] = max(stats['max_ms'], ms)
            if ms > 2000:
                stats['slow'] += 1
        else:
            stats['fail'] += 1
            if stats['first_fail'] is None:
                stats['first_fail'] = time.time() - t_start[0]


def tab(idx):
    """One browser tab: log every 0.9 s, status every 2 s."""
    seq = 0
    last_status = 0.0
    while not stop.is_set():
        t0 = time.time()
        try:
            r = call('/api/log?since=%d' % seq, timeout=8)
            seq = r.get('seq', seq)
            record((time.time() - t0) * 1000, True)
        except Exception:
            record((time.time() - t0) * 1000, False)
        if time.time() - last_status >= 2.0:
            last_status = time.time()
            t1 = time.time()
            try:
                call('/api/status', timeout=8)
                record((time.time() - t1) * 1000, True)
            except Exception:
                record((time.time() - t1) * 1000, False)
        stop.wait(0.9)


lines = []


def sniff():
    p = serial.Serial()
    p.port = PORT
    p.baudrate = 115200
    p.timeout = 0.2
    p.dsrdtr = False
    p.rtscts = False
    p.open()
    p.rts = False
    p.dtr = False
    buf = ''
    while not stop.is_set():
        d = p.read(512)
        if d:
            buf += d.decode('utf-8', 'replace')
            while '\n' in buf:
                l, buf = buf.split('\n', 1)
                lines.append(l.rstrip())
    p.rts = False
    p.dtr = False
    p.close()


print('panel bekleniyor...')
for i in range(45):
    try:
        call('/api/status')
        break
    except Exception:
        time.sleep(2)
else:
    sys.exit('panel yok')

sn = threading.Thread(target=sniff, daemon=True)
sn.start()
time.sleep(1)

print('proje baslatiliyor: %s (0.1 sn, ekran cizimi acik)' % PROJ)
print(' ', call('/api/run?name=%s' % PROJ, 'POST'))

t_start[0] = time.time()
tabs = [threading.Thread(target=tab, args=(i,), daemon=True)
        for i in range(TABS)]
for t in tabs:
    t.start()
print('%d tarayici sekmesi taklit ediliyor (log 0.9sn + durum 2sn)\n' % TABS)

print('%-5s %-6s %-6s %-8s %s' % ('sn', 'basari', 'hata', 'en yavas', 'durum'))
while time.time() - t_start[0] < SECS:
    time.sleep(5)
    el = time.time() - t_start[0]
    with lock:
        o, f, mx, sl = stats['ok'], stats['fail'], stats['max_ms'], stats['slow']
    durum = 'iyi'
    if f:
        durum = '%d ISTEK BASARISIZ' % f
    elif sl:
        durum = '%d istek 2sn ustu' % sl
    print('%-5.0f %-6d %-6d %-8.0f %s' % (el, o, f, mx, durum))
    if f > 5:
        print('  -> panel cevap veremiyor, test kesiliyor')
        break

stop.set()
for t in tabs:
    t.join(timeout=3)
time.sleep(4)
sn.join(timeout=4)

print('\n=== sonuc ===')
print('basarili istek : %d' % stats['ok'])
print('basarisiz istek: %d' % stats['fail'])
print('en yavas cevap : %.0f ms' % stats['max_ms'])
if stats['first_fail']:
    print('ilk hata       : %.0f. saniyede' % stats['first_fail'])
    print('\n-> SORUN UREDI')
else:
    print('\n-> panel dayandi')

kritik = [l for l in lines if 'MemoryError' in l or 'Guru' in l
          or 'panic' in l.lower() or 'Traceback' in l or 'rst:' in l
          or 'alloc' in l.lower() or 'sunucu yeniden' in l]
print('\n=== kritik seri satirlar ===')
for l in kritik[-20:]:
    print('  ', l)
if not kritik:
    print('   (yok)')

try:
    call('/api/stop?name=%s' % PROJ, 'POST')
except Exception:
    pass
