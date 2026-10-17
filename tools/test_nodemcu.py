"""End-to-end on the NodeMCU: run a project solo, reset, read its log.

This is the whole point of the design on a board with no threads: the
project runs alone with the panel shut down, writes to a persistent log
on flash, and the log is still there after the reset that brings the
panel back.
"""
import json
import subprocess
import sys
import time
import urllib.request

import serial

HOST = sys.argv[1] if len(sys.argv) > 1 else '192.168.0.215'
PORT = sys.argv[2] if len(sys.argv) > 2 else 'COM5'
BASE = 'http://%s' % HOST
PROJ = 'led_deneme.py'

KOD = b"""# NodeMCU dahili LED (GPIO2, ters mantik) + kalici log denemesi
import cyd
import time

print('proje basladi')
print('bos RAM:', __import__('gc').mem_free(), 'bayt')

for i in range(1, 11):
    cyd.led(g=True)
    print('%2d yanik' % i)
    time.sleep(0.4)
    cyd.led_off()
    time.sleep(0.4)

print('10 kez yanip sondu, proje bitti')
"""


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


def bekle(limit=90):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            call('/api/status', timeout=5)
            return True
        except Exception:
            time.sleep(2)
    return False


def reset():
    """Seri porttan EN darbesi - panel solo moddan geri gelsin."""
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
    p.rts = True
    time.sleep(0.15)
    p.rts = False
    p.rts = False
    p.dtr = False
    p.close()


print('1) panel bekleniyor')
if not bekle():
    sys.exit('panel gelmedi')

print('2) proje yukleniyor:', PROJ)
print('  ', call('/api/save?name=%s' % PROJ, 'POST', KOD))

print('3) eski log temizleniyor')
try:
    call('/api/log/file/clear?name=%s' % PROJ, 'POST')
except Exception:
    pass

print('4) SOLO calistiriliyor (kart yeniden baslayacak, panel kapanacak)')
try:
    print('  ', call('/api/run?name=%s' % PROJ, 'POST', timeout=8))
except Exception as e:
    print('   (cevap kesildi, beklenen):', type(e).__name__)

print('5) proje calisiyor - 25 sn bekleniyor')
time.sleep(25)

print('6) RESET atiliyor (panel geri gelsin)')
reset()

print('7) panel bekleniyor')
if not bekle(90):
    sys.exit('panel geri gelmedi')

print('8) KALICI LOG okunuyor\n')
log = call('/api/log/file?name=%s' % PROJ)
if isinstance(log, str) and log.strip():
    for satir in log.strip().split('\n'):
        print('   |', satir)
    print('\nBASARILI: proje solo calisti, logu reset sonrasi da duruyor')
else:
    print('   (log bos)')
    print('\nBASARISIZ: kalici log yazilmamis')
    sys.exit(1)
