"""Talk to the bridged target's REPL and report what is on it.

The target must be in normal mode, not the bootloader: release BOOT and
press RESET once first. Retries, because the bridge drops the connection
between attempts.

    python tools/kopru_repl.py [socket://192.168.0.217:2323]
"""
import subprocess
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else 'socket://192.168.0.217:2323'

KOD = (
    "import sys, os, gc\n"
    "gc.collect()\n"
    "print('MPY :', sys.version)\n"
    "print('plat:', sys.platform)\n"
    "print('RAM :', gc.mem_free() // 1024, 'KB')\n"
    "st = os.statvfs('/')\n"
    "print('flash:', st[0] * st[3] // 1024, 'KB bos /', st[0] * st[2] // 1024, 'KB')\n"
    "print('FS  :', sorted(os.listdir('/')))\n"
    "try:\n"
    "    print('projeler:', sorted(os.listdir('/projects')))\n"
    "except OSError:\n"
    "    print('projeler: yok')\n"
)

for n in range(1, 8):
    try:
        r = subprocess.run([sys.executable, '-m', 'mpremote', 'connect', PORT,
                            'exec', KOD],
                           capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print('deneme %d: zaman asimi' % n)
        continue
    out = (r.stdout or '') + (r.stderr or '')
    if 'MPY :' in out:
        for satir in out.splitlines():
            if satir.strip():
                print(' ', satir.rstrip())
        sys.exit(0)
    kisa = [l for l in out.splitlines() if l.strip()]
    print('deneme %d: %s' % (n, kisa[-1][:90] if kisa else 'cevap yok'))
    time.sleep(2)

print()
print('REPL e ulasilamadi.')
print('  - Hedefte BOOT u BIRAKIP RESET e bastin mi? (bootloader da degil,')
print('    normal modda olmali)')
print('  - Kopru calisiyor mu? panelde kopru_uart.py')
sys.exit(1)
