"""Re-enable main.py on the bridged target.

The target already carries the whole system; the earlier rescue only
renamed main.py to main.off so it would stop looping. Flipping that back
is one small command - it deliberately avoids bulk transfer over the
bridge, which is the fragile part.

    python tools/hedef_main_ac.py [socket://192.168.0.217:2323]
"""
import subprocess
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else 'socket://192.168.0.217:2323'

KOD = (
    "import os\n"
    "d = os.listdir('/')\n"
    "if 'main.off' in d:\n"
    "    os.rename('/main.off', '/main.py')\n"
    "    print('SONUC: main.py geri acildi')\n"
    "elif 'main.py' in d:\n"
    "    print('SONUC: main.py zaten acik')\n"
    "else:\n"
    "    print('SONUC: main dosyasi YOK')\n"
    "print('FS:', sorted(os.listdir('/')))\n"
)

for n in range(1, 8):
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'mpremote', 'connect', PORT, 'exec', KOD],
            capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        print('deneme %d: zaman asimi' % n)
        continue
    out = (r.stdout or '') + (r.stderr or '')
    if 'SONUC:' in out:
        for satir in out.splitlines():
            if satir.strip():
                print(' ', satir.rstrip())
        sys.exit(0)
    kisa = [l for l in out.splitlines() if l.strip()]
    print('deneme %d: %s' % (n, kisa[-1][:88] if kisa else 'cevap yok'))
    time.sleep(3)

print()
print('Ulasilamadi. Kontrol:')
print('  - Hedef NORMAL modda mi? (BOOT basili OLMAMALI, bir kez RESET at)')
print('  - Kopru calisiyor mu? panelde kopru_uart.py')
sys.exit(1)
