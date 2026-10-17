"""Listen to the board without resetting it.

bootlog.py pulses EN, which would destroy the very state we want to look
at. This only clears RTS/DTR (otherwise Windows holds the ESP32 in reset
the moment the port opens) and then reads.
"""
import sys
import time

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM3'
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0

p = serial.Serial()
p.port = PORT
p.baudrate = 115200
p.timeout = 0.2
p.dsrdtr = False
p.rtscts = False
p.open()
p.rts = False          # EN high - do NOT hold the chip in reset
p.dtr = False
time.sleep(0.2)

print('--- %s pasif dinleniyor (%.0f sn, reset YOK) ---' % (PORT, SECS))
end = time.time() + SECS
total = 0
while time.time() < end:
    d = p.read(512)
    if d:
        total += len(d)
        sys.stdout.write(d.decode('utf-8', 'replace'))
        sys.stdout.flush()

p.rts = False
p.dtr = False
p.close()
print('\n--- %d bayt ---' % total)
if total == 0:
    print('Hic veri yok: kart ya kilitlendi ya da sessiz calisiyor.')
