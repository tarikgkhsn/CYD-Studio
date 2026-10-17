"""Solo mode with the radio off: does BLE finally come up?

Wi-Fi costs ~44 KB of internal DRAM and BLE needs more than what is left,
so this boots the board with the panel and the radio both switched off and
watches the serial port to see whether the BLE stack initialises.
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
PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM3'
HOST = sys.argv[2] if len(sys.argv) > 2 else '192.168.0.217'
WIFI = sys.argv[3] if len(sys.argv) > 3 else '0'
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


print('1) panel bekleniyor')
t0 = time.time()
while time.time() - t0 < 90:
    try:
        call('/api/status', timeout=4)
        break
    except Exception:
        time.sleep(2)
else:
    sys.exit('panel acilmadi')

print('2) acilis listesi temizleniyor')
for name in call('/api/status')['autostart']:
    call('/api/autostart?name=%s&on=0' % name, 'POST')

with open(os.path.join(ROOT, 'device', 'samples', PROJ), 'rb') as f:
    call('/api/save?name=%s' % PROJ, 'POST', f.read())

print('3) SOLO + WiFi %s ile yeniden baslatiliyor' % (chr(65) if WIFI==chr(49) else chr(75)))

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
        pass          # the board reboots mid-reply


threading.Thread(target=trigger, daemon=True).start()

print('   35 sn seri port dinleniyor...\n')
end = time.time() + 35
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
solo = 'SOLO MOD' in buf
ble = 'BLE acildi' in buf
yayin = 'yayin basladi' in buf
print('solo moda girdi :', 'EVET' if solo else 'HAYIR')
print('BLE acildi      :', 'EVET' if ble else 'HAYIR')
print('yayin basladi   :', 'EVET' if yayin else 'HAYIR')
if ble:
    print('\nTelefondan "CYD-BLE" adini gorebilmelisin.')
print('\npaneli geri getir: python tools/bootlog.py %s 20' % PORT)
sys.exit(0 if (solo and ble) else 1)
