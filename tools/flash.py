"""Erase and write MicroPython, retrying while BOOT is held.

Two hard-won details are baked in:

  * --before no-reset / --after no-reset: esptool's own reset pulse takes
    these boards straight back out of download mode.
  * a fixed 115200 baud: passing --baud 460800 leaves the stub talking at
    that rate, and the next command then fails to connect at 115200. Slower
    but every retry starts from the same place.

    python tools/flash.py [COM4] [firmware.bin] [--koru]

  --koru: do NOT erase; only write the image at 0x1000. The LittleFS
  partition (projects, config.json, logs) stays intact - used when the
  firmware is rebuilt (tools/frozen_esp32_build.py) and nothing else changed.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

KORU = '--koru' in sys.argv
argv = [a for a in sys.argv if a != '--koru']
PORT = argv[1] if len(argv) > 1 else 'COM4'
FW = argv[2] if len(argv) > 2 else os.path.join(
    ROOT, 'firmware', 'micropython-esp32.bin')

if not os.path.exists(FW):
    sys.exit('firmware bulunamadi: %s' % FW)

BASE = [sys.executable, '-m', 'esptool', '--port', PORT, '--baud', '115200',
        '--before', 'no-reset', '--after', 'no-reset', '--connect-attempts', '1']


def run(cmd, label, timeout_s, window):
    print('\n### %s ###' % label, flush=True)
    end = time.time() + window
    n = 0
    while time.time() < end:
        n += 1
        try:
            r = subprocess.run(BASE + cmd, capture_output=True, text=True,
                               timeout=timeout_s)
        except subprocess.TimeoutExpired:
            print('  deneme %d: zaman asimi' % n, flush=True)
            continue
        out = r.stdout + r.stderr
        if r.returncode == 0:
            print(out, flush=True)
            return True
        err = [l.strip() for l in out.splitlines() if 'fatal error' in l.lower()]
        print('  deneme %d: %s' % (n, err[-1] if err else 'rc=%d' % r.returncode),
              flush=True)
        time.sleep(0.4)
    return False


print('port: %s' % PORT)
print('firmware: %s (%d bayt)' % (FW, os.path.getsize(FW)))
print('BOOT BASILI TUTULMALI - islem bitene kadar birakma\n')

if KORU:
    print('--koru: flash silinmiyor, dosya sistemi korunuyor')
elif not run(['erase-flash'], 'FLASH SILINIYOR', 180, 90):
    sys.exit('ERASE_FAILED')

if not run(['write-flash', '-z', '0x1000', FW],
           'MICROPYTHON YAZILIYOR', 400, 420):
    sys.exit('WRITE_FAILED')

print('FLASH_OK')
print('Artik BOOT u birakabilirsin. RESET e bas.')
