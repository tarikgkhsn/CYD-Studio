"""Make the bridged target's config identical to the CYD's.

The target still carried my brownout workarounds - 80 MHz CPU, 8 dBm TX,
modem power save. Those were meant to keep it alive on a starved rail,
but they never protected the moment it actually dies: wlan.active(True)
brings the radio up at full power before any txpower setting applies.
Worth removing them anyway so the board runs a known-good configuration
rather than my improvised one.

Only the four power keys change; ssid, ip and the rest stay.

    python tools/hedef_cyd_ayari.py [socket://192.168.0.217:2323]
"""
import subprocess
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else 'socket://192.168.0.217:2323'
ATILACAK = ('txpower', 'wifi_pm', 'disable_bod')

KOD = (
    "import json\n"
    "c = json.load(open('/config.json'))\n"
    "print('ONCE:', json.dumps({k: c.get(k) for k in "
    "('cpu_freq','txpower','wifi_pm','disable_bod')}))\n"
    "for k in %r:\n"
    "    c.pop(k, None)\n"
    "c['cpu_freq'] = 240\n"
    "open('/config.json', 'w').write(json.dumps(c))\n"
    "print('SONRA:', json.dumps({k: c.get(k) for k in "
    "('cpu_freq','txpower','wifi_pm','disable_bod')}))\n"
    "print('TAMAM')\n"
) % (ATILACAK,)


# The board is in a brownout reset loop, so the REPL only exists for the
# second or two between boot and the radio coming up. mpremote's Ctrl-C
# lands inside main.py during that window and stops it - but only if we
# happen to knock at the right moment, hence many short attempts.
for n in range(1, 26):
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'mpremote', 'connect', PORT, 'exec', KOD],
            capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        print('deneme %2d: zaman asimi' % n)
        continue
    out = (r.stdout or '') + (r.stderr or '')
    if 'TAMAM' in out:
        print()
        for s in out.splitlines():
            if s.strip():
                print(' ', s.rstrip()[:200])
        print()
        print('Yazildi. Hedefe RESET at (veya guc kes-ver).')
        sys.exit(0)
    kisa = [l for l in out.splitlines() if l.strip()]
    print('deneme %2d: %s' % (n, (kisa[-1][:78] if kisa else 'cevap yok')))
    time.sleep(0.4)

print()
print('REPL yakalanamadi - kart reset dongusunde, aralik cok dar.')
print('Alternatif: hedefi BOOT basili tutarak resetle (download modu),')
print('o zaman main.py hic calismaz ve REPL sabit kalir.')
sys.exit(1)
