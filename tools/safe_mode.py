"""Stop main.py from running so a brown-out looping board holds still.

Renaming main.py leaves the board sitting at the REPL, which is stable
because nothing ever brings the radio up. That gives a window to run
controlled experiments on it.

    python tools/safe_mode.py COM4 off    # main.py -> main.off  (guvenli)
    python tools/safe_mode.py COM4 on     # main.off -> main.py  (geri al)

The board resets constantly in the failing state, so every mpremote call
is retried until one lands in the gap.
"""
import subprocess
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM4'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'off'

if MODE == 'off':
    KOD = ("import os\n"
           "try:\n"
           "    os.rename('main.py', 'main.off')\n"
           "    print('GUVENLI MOD: main.py devre disi')\n"
           "except OSError as e:\n"
           "    print('zaten kapali olabilir:', e)\n"
           "print(os.listdir('/'))\n")
else:
    KOD = ("import os\n"
           "try:\n"
           "    os.rename('main.off', 'main.py')\n"
           "    print('NORMAL MOD: main.py geri geldi')\n"
           "except OSError as e:\n"
           "    print('zaten acik olabilir:', e)\n"
           "print(os.listdir('/'))\n")

print('%s uzerinde deneniyor (kart resetlenirken araya girmeye calisiyoruz)'
      % PORT)

for n in range(1, 41):
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'mpremote', 'connect', PORT, 'exec', KOD],
            capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        print('  deneme %d: zaman asimi' % n)
        continue
    out = (r.stdout + r.stderr).strip()
    if r.returncode == 0 and out:
        print(out)
        print('BASARILI')
        sys.exit(0)
    kisa = out.splitlines()[-1][:80] if out else 'baglanamadi'
    print('  deneme %d: %s' % (n, kisa))
    time.sleep(0.6)

print('BASARISIZ - port hic sabit kalmadi')
sys.exit(1)
