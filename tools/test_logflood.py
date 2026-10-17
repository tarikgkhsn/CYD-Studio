"""Reproduce the panel dying when a project prints in a tight loop.

Runs the LED blink at 0.1 s (20 log lines a second), polls /api/status
until it stops answering, and streams the serial port the whole time so a
MemoryError or a guru meditation is captured rather than guessed at.
"""
import json
import sys
import threading
import time
import urllib.request

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM3'
HOST = sys.argv[2] if len(sys.argv) > 2 else '192.168.0.217'
HIZ = sys.argv[3] if len(sys.argv) > 3 else '0.1'
BASE = 'http://%s' % HOST

PROJ = 'log_seli.py'
SRC = ("""# ESKI: # panel dayanikliligi testi - saniyede ~%d satir log uretir
from machine import Pin
import cyd

led = Pin(22, Pin.OUT)
n = 0
while not cyd.should_stop():
    n += 1
    led.value(1)
    print('%%4d  YANIK' %% n)
    if not cyd.sleep(%s):
        break
    led.value(0)
    print('%%4d  sonuk' %% n)
    if not cyd.sleep(%s):
        break
led.value(0)
print('bitti')
""" % (int(2 / float(HIZ)), HIZ, HIZ)).encode()


def call(path, method='GET', body=None, timeout=6):
    if method == 'POST' and body is None:
        body = b''
    req = urllib.request.Request(BASE + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except ValueError:
        return raw


print('panel bekleniyor...')
for i in range(45):
    try:
        call('/api/status')
        break
    except Exception:
        time.sleep(2)
else:
    sys.exit('panel yok - once: python tools/bootlog.py %s 20' % PORT)

print('test projesi yukleniyor (%s sn araliк)' % HIZ)
print(' ', call('/api/save?name=%s' % PROJ, 'POST', SRC, timeout=20))

# serial in the background so a crash dump is not lost
lines = []
stop = threading.Event()


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
                line, buf = buf.split('\n', 1)
                lines.append(line.rstrip())
    p.rts = False
    p.dtr = False
    p.close()


t = threading.Thread(target=sniff, daemon=True)
t.start()
time.sleep(1)

print(' ', call('/api/run?name=%s' % PROJ, 'POST'))
print('\n%-5s %-9s %-9s %-9s %s' % ('sn', 'python', 'dram', 'cevap', 'not'))

t0 = time.time()
olu = None
while time.time() - t0 < 75:
    time.sleep(2)
    el = time.time() - t0
    try:
        c0 = time.time()
        s = call('/api/status', timeout=5)
        ms = (time.time() - c0) * 1000
        y = s['sys']
        run = [j['name'] for j in s['jobs'] if j['running']]
        print('%-5.0f %-9s %-9s %-9s %s'
              % (el, '%d KB' % (y['ram_free'] / 1024),
                 '%d KB' % (y['idf']['free'] / 1024),
                 '%.0f ms' % ms,
                 'calisan: %s' % (run or 'yok')))
        if not run:
            print('  -> proje kendiliginden durdu')
            break
    except Exception as e:
        olu = el
        print('%-5.0f %-9s %-9s %-9s %s' % (el, '-', '-', 'CEVAP YOK', e))
        break

if olu is None:
    print('\nPANEL AYAKTA KALDI - sorun ureyemedi')
    try:
        call('/api/stop?name=%s' % PROJ, 'POST')
    except Exception:
        pass
else:
    print('\nPANEL %.0f saniyede DUSTU - seri port dinlemeye devam...' % olu)

time.sleep(8)
stop.set()
t.join(timeout=5)

print('\n=== seri port son 40 satir ===')
for l in lines[-40:]:
    if l.strip():
        print('  ', l)

kritik = [l for l in lines if 'MemoryError' in l or 'Guru' in l
          or 'abort' in l.lower() or 'panic' in l.lower()
          or 'Traceback' in l or 'rst:' in l]
print('\n=== kritik satirlar ===')
for l in kritik[-15:]:
    print('  ', l)
if not kritik:
    print('   (yok)')
