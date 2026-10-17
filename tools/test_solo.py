"""Prove solo mode: panel off, project gets the DRAM, BLE actually opens."""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

import serial

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM3'
HOST = sys.argv[2] if len(sys.argv) > 2 else '192.168.0.217'
BASE = 'http://%s' % HOST
PROJ = 'ornek_ble.py'


def call(path, method='GET', body=None, timeout=20):
    if method == 'POST' and body is None:
        body = b''
    req = urllib.request.Request(BASE + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def wait_panel(limit=90):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            call('/api/status', timeout=4)
            return True
        except Exception:
            time.sleep(2)
    return False


print('1) panel bekleniyor')
if not wait_panel():
    sys.exit('panel acilmadi')

with open(os.path.join(ROOT, 'device', 'samples', PROJ), 'rb') as f:
    src = f.read()
print('  ', call('/api/save?name=%s' % PROJ, 'POST', src))

print('2) panel ACIKKEN BLE deneniyor (basarisiz olmali)')
print('  ', call('/api/run?name=%s' % PROJ, 'POST'))
time.sleep(5)
d = call('/api/log?since=0')
for _, src_, t in d['lines']:
    if src_ == PROJ:
        print('   |', t)
call('/api/stop?name=%s' % PROJ, 'POST')
time.sleep(3)

print('\n3) SOLO moda geciliyor (panel kapanacak, seri porttan izlenecek)')

p = serial.Serial()
p.port = PORT
p.baudrate = 115200
p.timeout = 0.2
p.dsrdtr = False
p.rtscts = False
p.open()
p.rts = False
p.dtr = False
time.sleep(0.2)
p.reset_input_buffer()


def trigger():
    time.sleep(1.0)
    try:
        call('/api/solo?name=%s' % PROJ, 'POST', timeout=8)
    except Exception:
        pass          # the board reboots mid-reply, which is expected


threading.Thread(target=trigger, daemon=True).start()

print('   40 sn seri port dinleniyor...')
end = time.time() + 40
buf = ''
while time.time() < end:
    chunk = p.read(512)
    if chunk:
        text = chunk.decode('utf-8', 'replace')
        buf += text
        sys.stdout.write(text)
        sys.stdout.flush()
p.rts = False
p.dtr = False
p.close()

print('\n\n=== sonuc ===')
ok_solo = 'SOLO MOD' in buf
ok_ble = 'BLE acildi' in buf
print('solo moda girdi      :', 'EVET' if ok_solo else 'HAYIR')
print('BLE acildi           :', 'EVET' if ok_ble else 'HAYIR')
print('\npaneli geri getirmek icin: python tools/bootlog.py %s 20' % PORT)
sys.exit(0 if (ok_solo and ok_ble) else 1)
