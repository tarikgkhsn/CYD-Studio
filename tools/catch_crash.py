"""Watch the serial port while a project is started over HTTP.

A MicroPython traceback shows up in the web log; a hard fault (stack
overflow, guru meditation, watchdog) only ever appears on UART.
"""
import sys
import threading
import time
import urllib.request

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM3'
HOST = sys.argv[2] if len(sys.argv) > 2 else '192.168.0.217'
PROJ = sys.argv[3] if len(sys.argv) > 3 else 'ornek_ekran.py'
SECONDS = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0

p = serial.Serial()
p.port = PORT
p.baudrate = 115200
p.timeout = 0.2
p.dsrdtr = False
p.rtscts = False
p.open()
p.rts = False
p.dtr = False
time.sleep(0.3)
p.reset_input_buffer()


def trigger():
    time.sleep(1.5)
    url = 'http://%s/api/run?name=%s' % (HOST, PROJ)
    try:
        req = urllib.request.Request(url, data=b'', method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            print('\n[HTTP run -> %s]\n' % r.read().decode(), flush=True)
    except Exception as e:
        print('\n[HTTP hata: %s]\n' % e, flush=True)


threading.Thread(target=trigger, daemon=True).start()

print('--- %s baslatiliyor, UART dinleniyor (%ss) ---' % (PROJ, SECONDS), flush=True)
end = time.time() + SECONDS
while time.time() < end:
    d = p.read(512)
    if d:
        sys.stdout.write(d.decode('utf-8', 'replace'))
        sys.stdout.flush()

p.rts = False
p.dtr = False
p.close()
print('\n--- bitti ---')
