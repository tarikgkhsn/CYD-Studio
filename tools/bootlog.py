"""Reset the CYD and stream its boot log.

Opening a serial port on Windows asserts RTS, which on this board pulls EN
low and holds the ESP32 in reset - so we explicitly clear RTS/DTR first.
"""
import sys
import time

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM3'
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

p = serial.Serial()
p.port = PORT
p.baudrate = 115200
p.timeout = 0.2
p.dsrdtr = False
p.rtscts = False
p.open()
p.rts = False          # EN high  -> not held in reset
p.dtr = False          # IO0 high -> normal boot
time.sleep(0.2)

p.rts = True           # EN low
time.sleep(0.15)
p.rts = False          # release -> boot
p.reset_input_buffer()

print('--- reset gonderildi, %ss dinleniyor ---' % SECONDS, flush=True)
end = time.time() + SECONDS
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
print('\n--- toplam %d bayt ---' % total)
