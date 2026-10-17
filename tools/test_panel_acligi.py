"""Does a running project starve the panel by CPU or by memory?

"The panel locks up" can mean two very different things and the fix is
different for each:

  * CPU  - the project's thread never yields, the server never gets
           scheduled. Response times climb but memory stays flat.
  * RAM  - the project eats the heap, the server cannot allocate to
           answer. Memory falls, then requests fail outright.

So we measure both while the project runs, instead of guessing.

    python tools/test_panel_acligi.py [proje.py] [host] [port]
"""
import json
import sys
import time
import urllib.request

PROJ = sys.argv[1] if len(sys.argv) > 1 else 'led_isik_sensoru.py'
HOST = sys.argv[2] if len(sys.argv) > 2 else '192.168.0.217'
PORT = sys.argv[3] if len(sys.argv) > 3 else 'COM3'
BASE = 'http://%s' % HOST


def call(path, method='GET', timeout=6):
    req = urllib.request.Request(BASE + path,
                                 data=(b'' if method == 'POST' else None),
                                 method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def olc():
    """(cevap suresi ms, python KB, dram KB) ya da None."""
    t0 = time.time()
    try:
        s = call('/api/status', timeout=6)
    except Exception:
        return None
    ms = (time.time() - t0) * 1000
    y = s['sys']
    return ms, y['ram_free'] // 1024, (y.get('idf') or {}).get('free', 0) // 1024


print('panel bekleniyor...')
for i in range(45):
    if olc():
        break
    time.sleep(2)
else:
    sys.exit('panel gelmedi - once: python tools/bootlog.py %s 25' % PORT)

taban = olc()
print('taban   : %.0f ms | python %d KB | dram %d KB\n' % taban)

print('%s baslatiliyor' % PROJ)
try:
    print(' ', call('/api/run?name=%s' % PROJ, 'POST', timeout=10))
except Exception as e:
    sys.exit('baslatilamadi: %s' % e)

print('\n%-4s %-9s %-10s %-9s %s' % ('sn', 'cevap', 'python', 'dram', 'durum'))
t0 = time.time()
hata = 0
while time.time() - t0 < 60:
    time.sleep(3)
    el = time.time() - t0
    r = olc()
    if r is None:
        hata += 1
        print('%-4.0f %-9s %-10s %-9s CEVAP YOK (%d)' % (el, '-', '-', '-', hata))
        if hata >= 4:
            print('\n-> PANEL DUSTU')
            break
        continue
    hata = 0
    ms, py, dr = r
    durum = 'iyi'
    if ms > 3000:
        durum = 'COK YAVAS'
    elif ms > 1200:
        durum = 'yavas'
    print('%-4.0f %-9.0f %-10s %-9s %s' % (el, ms, '%d KB' % py, '%d KB' % dr, durum))

print('\ndurduruluyor')
try:
    print(' ', call('/api/stop?name=%s' % PROJ, 'POST', timeout=10))
except Exception as e:
    print('  durdurulamadi:', e)

time.sleep(5)
son = olc()
if son:
    print('sonra   : %.0f ms | python %d KB | dram %d KB' % son)
    print('\nTESHIS:')
    if son[0] < taban[0] * 2 and hata == 0:
        print('  panel dayandi')
    elif son[1] < taban[1] * 0.5 or son[2] < 8:
        print('  BELLEK aclıgı - proje yigini tuketmis')
    else:
        print('  CPU aclıgı - proje is parcacigini birakmiyor')
else:
    print('panel hala cevap vermiyor -> tam kilitlenme')
