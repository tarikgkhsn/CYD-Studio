"""Flash the compiled Arduino sketch, retrying while BOOT is held.

Same two constraints as the MicroPython flasher on this board:
  * --before/--after no-reset - esptool's own reset pulse drops the chip
    out of download mode
  * fixed 115200 - a faster --baud leaves the stub at that rate and the
    next command cannot reconnect

    python tools/flash_arduino.py [COM4]
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, 'arduino', 'build')
CORE = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Arduino15', 'packages',
                    'esp32', 'hardware', 'esp32', '3.3.11', 'tools',
                    'partitions', 'boot_app0.bin')

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM4'

PARCALAR = [
    ('0x1000', os.path.join(BUILD, 'wifi_testi.ino.bootloader.bin')),
    ('0x8000', os.path.join(BUILD, 'wifi_testi.ino.partitions.bin')),
    ('0xe000', CORE),
    ('0x10000', os.path.join(BUILD, 'wifi_testi.ino.bin')),
]

for adres, yol in PARCALAR:
    if not os.path.exists(yol):
        sys.exit('dosya yok: %s' % yol)

BASE = [sys.executable, '-m', 'esptool', '--port', PORT, '--baud', '115200',
        '--before', 'no-reset', '--after', 'no-reset', '--connect-attempts', '1']

cmd = ['write-flash', '-z']
for adres, yol in PARCALAR:
    cmd += [adres, yol]

toplam = sum(os.path.getsize(y) for _, y in PARCALAR)
print('port: %s   toplam: %d bayt' % (PORT, toplam))
print('BOOT BASILI TUTULMALI - islem bitene kadar birakma\n')

end = time.time() + 420
n = 0
while time.time() < end:
    n += 1
    try:
        r = subprocess.run(BASE + cmd, capture_output=True, text=True,
                           timeout=400)
    except subprocess.TimeoutExpired:
        print('  deneme %d: zaman asimi' % n, flush=True)
        continue
    out = r.stdout + r.stderr
    if r.returncode == 0 and 'verified' in out.lower():
        print(out[-1500:], flush=True)
        print('FLASH_OK')
        print('BOOT u birakip RESET e bas.')
        sys.exit(0)
    err = [l.strip() for l in out.splitlines() if 'fatal error' in l.lower()]
    print('  deneme %d: %s' % (n, err[-1] if err else 'rc=%d' % r.returncode),
          flush=True)
    time.sleep(0.4)

print('FLASH_FAILED')
sys.exit(1)
