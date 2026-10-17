"""Flash an ESP8266 (NodeMCU) - default: the FROZEN CYD Studio firmware.

Differs from flash.py (ESP32) in three ways that matter:
  * offset 0x0, not 0x1000 - the ESP8266 image starts at the beginning
  * --flash-size detect     - NodeMCU v3 is 4 MB, let esptool confirm it
  * auto-reset works here   - no BOOT-hold dance, no --before/--after no-reset

Erasing wipes the filesystem. Afterwards deploy the NON-frozen files only:

    python tools/flash_esp8266.py COM5
    python tools/deploy_mpy.py --board nodemcu --port COM5 --frozen --config --samples

Baud stays 115200 on purpose: ~650 KB takes about a minute, and a fixed
rate avoids the stub-left-at-460800 trap documented in CLAUDE.md.

--koru: do NOT erase first. write-flash only touches the firmware region
(0x0 .. ~0xA0000); the LittleFS filesystem lives well above it, so projects,
config and logs survive. Use this for every core rebuild after the first
install - a full erase is only needed on a fresh or corrupted board.

    python tools/flash_esp8266.py [COM5] [firmware.bin] [--koru]
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

KORU = '--koru' in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith('--')]
PORT = args[0] if len(args) > 0 else 'COM5'
FW = args[1] if len(args) > 1 else os.path.join(
    ROOT, 'firmware', 'micropython-esp8266-frozen.bin')

if not os.path.exists(FW):
    sys.exit('firmware bulunamadi: %s' % FW)

BASE = [sys.executable, '-m', 'esptool', '--chip', 'esp8266',
        '--port', PORT, '--baud', '115200', '--connect-attempts', '3']


def run(args, etiket, timeout, tekrar=3):
    for n in range(1, tekrar + 1):
        print('\n=== %s (deneme %d/%d) ===' % (etiket, n, tekrar))
        try:
            r = subprocess.run(BASE + args, timeout=timeout)
        except subprocess.TimeoutExpired:
            print('  zaman asimi')
            continue
        if r.returncode == 0:
            return True
        print('  esptool cikis kodu %d' % r.returncode)
        time.sleep(2)
    return False


print('port     : %s' % PORT)
print('firmware : %s (%d bayt)' % (FW, os.path.getsize(FW)))
print()
print('NodeMCU otomatik reset destekler - tusa basmana gerek yok.')

if not run(['flash-id'], 'CIP KIMLIGI', 40):
    sys.exit('\nKarta baglanilamadi. USB kablosu veri tasiyor mu? Port dogru mu?')

if KORU:
    print('\n--koru: flash SILINMIYOR, dosya sistemi korunuyor')
elif not run(['erase-flash'], 'FLASH SILINIYOR', 120):
    sys.exit('\nSilme basarisiz.')

if not run(['write-flash', '--flash-size', 'detect', '0x0', FW],
           'FIRMWARE YAZILIYOR', 300):
    sys.exit('\nYazma basarisiz.')

print()
print('=== TAMAM ===')
if KORU:
    print('Kart yeniden basliyor. Dosya sistemi yerinde; sadece cekirdek degisti.')
    print('main.py/boot.py degistiyse:')
    print('  python tools/deploy_mpy.py --board nodemcu --port %s --frozen' % PORT)
else:
    print('Kart yeniden basliyor. Dosya sistemi BOS - cekirdek artik firmware\'de.')
    print('Simdi sadece dondurulmamis dosyalari yukle:')
    print('  python tools/deploy_mpy.py --board nodemcu --port %s --frozen --config --samples' % PORT)
print('ILK 10 SANIYE DOKUNMA: ilk acilis FS formati / mpremote reset yarisi.')
