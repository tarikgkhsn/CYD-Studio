"""Undo the brownout throttling on the bridged target's radio.

While the board was starving on the CYD's 3.3V rail I clamped its radio
to survive: 8 dBm TX, 80 MHz CPU, power save on. With a real 5V supply
those limits are no longer protective - 8 dBm may simply be too weak to
associate, which looks exactly like "the board never joins the network".

Reads the target's config over the bridge, restores full radio, writes it
back and resets. Nothing else in the config is touched.

    python tools/hedef_radyo_ac.py [socket://192.168.0.217:2323]
"""
import subprocess
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else 'socket://192.168.0.217:2323'

OKU = (
    "import json\n"
    "try:\n"
    "    c = json.load(open('/config.json'))\n"
    "    print('CFG:', json.dumps(c))\n"
    "except Exception as e:\n"
    "    print('CFG-HATA:', e)\n"
)

YAZ = (
    "import json, machine\n"
    "c = json.load(open('/config.json'))\n"
    "c['txpower'] = 20\n"
    "c['cpu_freq'] = 160\n"
    "c['wifi_pm'] = False\n"
    "c['disable_bod'] = False\n"
    "open('/config.json', 'w').write(json.dumps(c))\n"
    "print('YAZILDI:', json.dumps(c))\n"
    "import time; time.sleep(1)\n"
    "machine.reset()\n"
)


def calistir(kod, etiket, tekrar=6):
    for n in range(1, tekrar + 1):
        try:
            r = subprocess.run(
                [sys.executable, '-m', 'mpremote', 'connect', PORT, 'exec', kod],
                capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print('  %s deneme %d: zaman asimi' % (etiket, n))
            continue
        out = (r.stdout or '') + (r.stderr or '')
        if etiket in out or 'YAZILDI' in out or 'CFG' in out:
            return out
        kisa = [l for l in out.splitlines() if l.strip()]
        print('  %s deneme %d: %s' % (etiket, n, kisa[-1][:80] if kisa else 'cevap yok'))
        time.sleep(2)
    return None


print('1) Hedefin mevcut ayari okunuyor...')
o = calistir(OKU, 'CFG')
if not o:
    print()
    print('Hedefe ulasilamadi. Kontrol:')
    print('  - CYD panelinde kopru_uart.py calisiyor mu?')
    print('  - Hedef NORMAL modda mi? (BOOT basili DEGIL, bir kez RESET)')
    print('  - GPIO27->hedef RX, GPIO22<-hedef TX, ortak GND')
    sys.exit(1)
for s in o.splitlines():
    if s.strip():
        print('  ', s.rstrip()[:200])

print()
print('2) Radyo tam guce aliniyor (txpower 20, cpu 160 MHz, pm kapali)...')
y = calistir(YAZ, 'YAZILDI')
if not y:
    print('  Yazilamadi.')
    sys.exit(1)
for s in y.splitlines():
    if s.strip():
        print('  ', s.rstrip()[:200])

print()
print('3) Hedef resetlendi. Aga cikmasi ~10 sn surer.')
