"""Deploy the core as precompiled .mpy - the only way it fits on ESP8266.

Importing a .py costs RAM twice: the source is read in, then the parser
builds bytecode from it. With ~35 KB free on an ESP8266 that is enough to
fail halfway through importing the web server. A .mpy is already bytecode,
so the parser never runs and the source never occupies the heap.

boot.py and main.py stay as .py: MicroPython runs those two by filename,
not by import.

    python tools/deploy_mpy.py --board nodemcu --port COM5
    python tools/deploy_mpy.py --board nodemcu --port COM5 --config

FROZEN MODE (--frozen): the core lives inside the firmware image
(firmware/micropython-esp8266-frozen.bin, built from
firmware/esp8266-frozen-manifest.py). Then the core must NOT be on the
filesystem at all - a stray server.py or server.mpy on the FS shadows the
frozen copy and the RAM saving silently disappears. So --frozen skips the
core entirely, uploads only boot/main/index/config(/samples), and purges
any leftover core .py/.mpy it finds.

    python tools/flash_esp8266.py COM5
    python tools/deploy_mpy.py --board nodemcu --port COM5 --frozen --config --samples
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEV = os.path.join(ROOT, 'device')
BOARDS = os.path.join(ROOT, 'boards')
BUILD = os.path.join(ROOT, 'build_mpy')

# Bunlar derlenir (import ile yuklenirler)
DERLE = ['runtime.py', 'jobs.py', 'sysinfo.py', 'logstore.py', 'server.py',
         'settings.py', 'netmgr.py', 'store.py']
# Bunlar oldugu gibi gider (isimleriyle calistiriliyorlar / veri dosyasi)
AYNEN = ['boot.py', 'main.py', 'index.html', 'docs.md', 'docs_en.md', 'usbkopru.py']


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


BOARD = arg('--board', 'nodemcu')
PORT = arg('--port', 'COM5')
WITH_CONFIG = '--config' in sys.argv
WITH_SAMPLES = '--samples' in sys.argv
FROZEN = '--frozen' in sys.argv
BOARD_DIR = os.path.join(BOARDS, BOARD)
SAMPLES = os.path.join(DEV, 'samples')

if not os.path.isdir(BOARD_DIR):
    sys.exit('bilinmeyen kart: %s' % BOARD)


sys.path.insert(0, HERE)
from tek_oturum import Oturum   # noqa: E402

_kart = None


def kart():
    # Tek oturum: bu PC'de port her acilista karti resetliyor; dosya basina
    # mpremote = dosya basina reset + kacan Ctrl-C (bkz. tek_oturum.py).
    global _kart
    if _kart is None:
        _kart = Oturum(PORT)
    return _kart


def derle(src, out):
    r = subprocess.run([sys.executable, '-m', 'mpy_cross', src, '-o', out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print('  DERLEME HATASI %s' % os.path.basename(src))
        print('    ' + (r.stderr or r.stdout).strip()[:300])
        return False
    return True


def yukle(local, remote):
    try:
        kart().cp(local, remote)
        ok, hata = True, ''
    except Exception as e:
        ok, hata = False, repr(e)
    print(('  yuklendi  ' if ok else '  HATA      ') + remote)
    if not ok:
        print('    ' + hata[:200])
    return ok


shutil.rmtree(BUILD, ignore_errors=True)
os.makedirs(BUILD, exist_ok=True)

print('kart: %s   port: %s%s' % (BOARD, PORT, '   [FROZEN]' if FROZEN else ''))
if FROZEN:
    print('--- cekirdek firmware icinde, derlenmiyor/yuklenmiyor ---')
else:
    print('--- derleniyor ---')

hedefler = []
for ad in ([] if FROZEN else DERLE):
    src = os.path.join(DEV, ad)
    if not os.path.exists(src):
        continue
    out = os.path.join(BUILD, ad[:-3] + '.mpy')
    if derle(src, out):
        kucuk = os.path.getsize(out)
        buyuk = os.path.getsize(src)
        print('  %-14s %5d -> %5d bayt  (%%%d)'
              % (ad, buyuk, kucuk, 100 - kucuk * 100 // buyuk))
        hedefler.append((out, ad[:-3] + '.mpy'))

# kartin donanim katmani da derlenir
board_cyd = os.path.join(BOARD_DIR, 'cyd.py')
if not FROZEN and os.path.exists(board_cyd):
    out = os.path.join(BUILD, 'cyd.mpy')
    if derle(board_cyd, out):
        print('  %-14s -> cyd.mpy' % 'cyd.py')
        hedefler.append((out, 'cyd.mpy'))

# kartin diger surucu dosyalari (ssd1306 vb.)
for ad in ([] if FROZEN else sorted(os.listdir(BOARD_DIR))):
    if ad.endswith('.py') and ad != 'cyd.py':
        out = os.path.join(BUILD, ad[:-3] + '.mpy')
        if derle(os.path.join(BOARD_DIR, ad), out):
            print('  %-14s -> %s' % (ad, ad[:-3] + '.mpy'))
            hedefler.append((out, ad[:-3] + '.mpy'))

print('\n--- yukleniyor ---')
sent = failed = 0
for local, remote in hedefler:
    if yukle(local, remote):
        sent += 1
    else:
        failed += 1

for ad in AYNEN:
    # Kart profili ayni adli bir dosya veriyorsa o kazanir (ornegin
    # ESP8266'nin sade index.html'i cekirdekteki 36 KB'lik panelin yerine).
    src = os.path.join(BOARD_DIR, ad)
    if not os.path.exists(src):
        src = os.path.join(DEV, ad)
    if os.path.exists(src):
        if yukle(src, ad):
            sent += 1
        else:
            failed += 1

if WITH_CONFIG:
    cfg = os.path.join(BOARD_DIR, 'config.json')
    if os.path.exists(cfg) and yukle(cfg, 'config.json'):
        sent += 1

if WITH_SAMPLES and os.path.isdir(SAMPLES):
    # Taze (silinmis) bir FS'te /projects yoktur; olusmus olmasi zarar vermez.
    print('\n--- ornek projeler ---')
    for d in ('projects', 'logs'):
        kart().mkdir(d)
    for ad in sorted(os.listdir(SAMPLES)):
        if ad.endswith('.py'):
            if yukle(os.path.join(SAMPLES, ad), 'projects/' + ad):
                sent += 1
            else:
                failed += 1

# FS'teki bir kopya, ayni adli dondurulmus/derlenmis modulu GOLGELER.
# Frozen modda cekirdegin hicbir kopyasi FS'te kalmamali (.py de .mpy de);
# normal modda ise .mpy yuklendigi icin .py kalmamali.
print('\n--- golgeleyen kopyalar siliniyor ---')
if FROZEN:
    adlar = [a[:-3] for a in DERLE] + ['cyd'] + [
        a[:-3] for a in os.listdir(BOARD_DIR) if a.endswith('.py') and a != 'cyd.py']
    silinecek = [a + u for a in adlar for u in ('.py', '.mpy')]
else:
    silinecek = [remote[:-4] + '.py' for _, remote in hedefler]
for dosya in silinecek:
    if kart().rm(dosya):
        print('  silindi   ' + dosya)

print('\n%d yuklendi, %d hata' % (sent, failed))

# mpremote ham REPL'den calisir: once main.py'yi Ctrl-C ile keser, isini
# yapar ve karti REPL'de BIRAKIR - yeniden baslatmaz. Yani her deploy'dan
# sonra panel kapalidir; main.py ancak reset ile tekrar kosar. (Olculdu:
# kopyadan sonra kart REPL'de, port 80 bos, RAM 35 KB - hicbir sey yuklu
# degil.) --reset burada machine.reset() atar.
if '--reset' in sys.argv:
    kart().reset()
    print('reset: gonderildi, panel ~10 sn')
else:
    kart().close()
    print('KART REPL DE, PANEL KAPALI. Reset at: --reset bayragi ya da RST tusu.')
sys.exit(1 if failed else 0)
