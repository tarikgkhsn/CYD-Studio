"""Get an ESP32 into download mode when auto-reset will not do it.

Both boards here need the same trick: esptool's own reset pulse drops the
chip back out of download mode, so BOOT is held by hand and esptool is
told not to touch the reset lines at all.

    python tools/boot_connect.py [COM4] [saniye]

Kullanici yapmali:
    1. BOOT'a bas ve BASILI TUT
    2. Basili tutarken RESET (EN) tusuna bir kez bas-birak
    3. BOOT'u BIRAKMA - bu script baglanana kadar tut
"""
import subprocess
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM4'
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0

CMD = [sys.executable, '-m', 'esptool', '--port', PORT, '--baud', '115200',
       '--before', 'no-reset', '--after', 'no-reset', '--connect-attempts', '1',
       'flash-id']

print('%s uzerinde download modu araniyor (%.0f sn)' % (PORT, SECS))
print('BOOT basili tut -> RESET bas-birak -> BOOT u BIRAKMA\n')

end = time.time() + SECS
n = 0
son = ''
while time.time() < end:
    n += 1
    try:
        r = subprocess.run(CMD, capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        print('  deneme %d: zaman asimi' % n)
        continue
    out = r.stdout + r.stderr
    if 'Chip is' in out or 'MAC:' in out or 'Chip type' in out:
        print(out)
        print('BAGLANDI')
        sys.exit(0)
    for line in out.splitlines():
        if 'fatal error' in line.lower():
            son = line.strip()
    print('  deneme %d: %s' % (n, son or 'baglanamadi'))
    time.sleep(0.4)

print('\nBAGLANAMADI')
print('Kontrol et: BOOT gercekten basili mi? RESET e bastin mi?')
print('Bazi kartlarda BOOT tusu arkada, RESET onde olabilir.')
sys.exit(1)
