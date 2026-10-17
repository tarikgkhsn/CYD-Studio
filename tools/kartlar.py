"""Which board is on which COM port?

Both the CYD and the NodeMCU use a CH340, same VID/PID - the port number
is the only thing that differs, and that changes with the USB socket. So
instead of guessing we ask each board what it is: sys.platform tells us
esp32 from esp8266, and the presence of _thread confirms it.

Deploying the wrong profile to the wrong board breaks both, so this runs
before every deploy.

    python tools/kartlar.py
"""
import subprocess
import sys

import serial.tools.list_ports as lp

SORGU = (
    "import sys, gc\n"
    "try:\n"
    "    import _thread; t = 'var'\n"
    "except ImportError:\n"
    "    t = 'yok'\n"
    "try:\n"
    "    import settings; ip = settings.get('ip') or '-'\n"
    "except Exception:\n"
    "    ip = '?'\n"
    "gc.collect()\n"
    "print('|%s|%s|%d|%s' % (sys.platform, t, gc.mem_free(), ip))\n"
)

PROFIL = {
    'esp32': 'cyd',        # ya da oled - ikisi de esp32, ayrimi ip/ekran yapar
    'esp8266': 'nodemcu',
}


def sor(port):
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'mpremote', 'connect', port, 'exec', SORGU],
            capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None
    for satir in (r.stdout or '').splitlines():
        if satir.startswith('|'):
            p = satir.strip('|').split('|')
            if len(p) == 4:
                return {'platform': p[0], 'thread': p[1],
                        'ram': int(p[2]), 'ip': p[3]}
    return None


portlar = list(lp.comports())
if not portlar:
    sys.exit('hic seri port yok')

print('%-6s %-10s %-8s %-9s %-15s %s'
      % ('PORT', 'PLATFORM', '_thread', 'BOS RAM', 'IP', 'PROFIL'))
print('-' * 72)

for p in portlar:
    bilgi = sor(p.device)
    if bilgi is None:
        print('%-6s %-10s %-8s %-9s %-15s %s'
              % (p.device, '?', '?', '?', '?', 'cevap yok (kart mesgul olabilir)'))
        continue
    profil = PROFIL.get(bilgi['platform'], '?')
    if bilgi['platform'] == 'esp32' and bilgi['ip'].endswith('.216'):
        profil = 'oled'
    print('%-6s %-10s %-8s %-9s %-15s %s'
          % (p.device, bilgi['platform'], bilgi['thread'],
             '%d KB' % (bilgi['ram'] // 1024), bilgi['ip'], profil))

print()
print('Deploy ornegi:')
print('  python tools/deploy.py --board cyd --port COM3')
print('  python tools/deploy_mpy.py --board nodemcu --port COM5')
