"""Run one project in solo mode and watch it over the serial port.

Solo mode boots without the web panel, so the project keeps the internal
DRAM the panel would hold. That is what BLE and TLS need.

    python tools/solo_run.py <proje.py> [wifi 0|1] [saniye] [COM3] [host]

Wi-Fi on  -> ~81 KB free (BLE and HTTPS both fit)
Wi-Fi off -> ~129 KB free (BLE only, no network)

The flag is one-shot: pressing RESET brings the panel straight back.
"""
import json
import os
import sys
import threading
import time
import urllib.request

import serial

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PROJ = sys.argv[1] if len(sys.argv) > 1 else 'ornek_ble.py'
WIFI = sys.argv[2] if len(sys.argv) > 2 else '1'
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 40.0
PORT = sys.argv[4] if len(sys.argv) > 4 else 'COM3'
HOST = sys.argv[5] if len(sys.argv) > 5 else '192.168.0.217'
BASE = 'http://%s' % HOST


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


print('panel bekleniyor...')
if not wait_panel():
    sys.exit('panel acilmadi - once: python tools/bootlog.py %s 20' % PORT)

# a stale autostart entry would launch the wrong thing in solo mode
for name in call('/api/status')['autostart']:
    call('/api/autostart?name=%s&on=0' % name, 'POST')

local = os.path.join(ROOT, 'device', 'samples', PROJ)
if os.path.exists(local):
    with open(local, 'rb') as f:
        print('yukleniyor:', PROJ, call('/api/save?name=%s' % PROJ, 'POST',
                                        f.read()))

print('SOLO baslatiliyor: %s  (wifi=%s, %.0f sn dinlenecek)\n'
      % (PROJ, WIFI, SECS))

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
        call('/api/solo?name=%s&wifi=%s' % (PROJ, WIFI), 'POST', timeout=8)
    except Exception:
        pass          # the board reboots mid-reply, which is expected


threading.Thread(target=trigger, daemon=True).start()

end = time.time() + SECS
while time.time() < end:
    chunk = p.read(512)
    if chunk:
        sys.stdout.write(chunk.decode('utf-8', 'replace'))
        sys.stdout.flush()

p.rts = False
p.dtr = False
p.close()
print('\n\n--- bitti. paneli geri getir: python tools/bootlog.py %s 20'
      % PORT)
