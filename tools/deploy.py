"""Push the sources to a board over the serial port.

Layout:
    device/          shared core - identical on every board
    boards/<ad>/     that board's hardware layer (cyd.py + drivers + config)

Only uploads files whose content actually differs, so a tweak to one
module does not mean re-sending everything.

    python tools/deploy.py                      # CYD, degisen dosyalar
    python tools/deploy.py --board oled         # OLED kart
    python tools/deploy.py --all                # hepsini zorla
    python tools/deploy.py --samples            # ornekleri de yenile
    python tools/deploy.py --config             # config.json'i da yaz
                                                # (cihazdaki ayarlari EZER)

Port: CYD_PORT ortam degiskeni ya da --port COM5
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEV = os.path.join(ROOT, 'device')
BOARDS = os.path.join(ROOT, 'boards')

# Shared core, identical on every board.
CORE = ['boot.py', 'main.py', 'runtime.py', 'jobs.py', 'sysinfo.py', 'logstore.py',
        'server.py', 'settings.py', 'netmgr.py', 'store.py',
        'index.html', 'docs.md', 'docs_en.md', 'usbkopru.py']


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


BOARD = arg('--board', 'cyd')
PORT = arg('--port', os.environ.get('CYD_PORT', 'COM3'))
FORCE = '--all' in sys.argv
SAMPLES = '--samples' in sys.argv
WITH_CONFIG = '--config' in sys.argv
# --frozen: the core is baked into the firmware (tools/frozen_esp32_build.py).
# A same-named .py on the filesystem SHADOWS the frozen copy (sys.path has ''
# before '.frozen'), so those files must not be sent - and any old copies
# on the board are removed. boot.py / main.py / index.html / docs.md stay.
FROZEN = '--frozen' in sys.argv
FROZEN_CORE = ['runtime.py', 'jobs.py', 'sysinfo.py', 'logstore.py',
               'settings.py', 'netmgr.py', 'store.py', 'server.py']

BOARD_DIR = os.path.join(BOARDS, BOARD)
if not os.path.isdir(BOARD_DIR):
    sys.exit('bilinmeyen kart: %s  (mevcut: %s)'
             % (BOARD, ', '.join(sorted(os.listdir(BOARDS)))))


def mp(*args, **kw):
    return subprocess.run([sys.executable, '-m', 'mpremote', 'connect', PORT] +
                          list(args), capture_output=True, text=True, **kw)


def local_digest(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def remote_digest(name):
    r = mp('exec', (
        "import hashlib, binascii\n"
        "try:\n"
        "    h = hashlib.sha256()\n"
        "    with open('/%s','rb') as f:\n"
        "        while True:\n"
        "            b = f.read(512)\n"
        "            if not b: break\n"
        "            h.update(b)\n"
        "    print(binascii.hexlify(h.digest()).decode())\n"
        "except OSError:\n"
        "    print('missing')\n" % name))
    return r.stdout.strip()


def push(local, remote):
    r = mp('fs', 'cp', local, ':' + remote)
    ok = r.returncode == 0
    print(('  yuklendi  ' if ok else '  HATA      ') + remote)
    if not ok:
        print('    ' + (r.stderr or r.stdout).strip())
    return ok


def gonder(local, name, sent, skipped, failed):
    if not FORCE and local_digest(local) == remote_digest(name):
        print('  ayni      %s' % name)
        return sent, skipped + 1, failed
    if push(local, name):
        return sent + 1, skipped, failed
    return sent, skipped, failed + 1


def main():
    print('kart: %s   port: %s' % (BOARD, PORT))
    sent = skipped = failed = 0

    frozen_names = set()
    if FROZEN:
        frozen_names = set(FROZEN_CORE) | {n for n in os.listdir(BOARD_DIR)
                                           if n.endswith('.py')}
        # remove shadowing copies left from a non-frozen deploy
        kod = 'import os\n'
        for n in sorted(frozen_names):
            kod += ('try: os.remove("/%s"); print("silindi %s")\n'
                    'except OSError: pass\n' % (n, n))
        r = mp('exec', kod)
        for l in r.stdout.splitlines():
            print('  ' + l.strip())
        print('  frozen: %d cekirdek dosyasi firmware icinde, gonderilmiyor'
              % len(frozen_names))

    # 1) shared core
    for name in CORE:
        if name in frozen_names:
            continue
        local = os.path.join(DEV, name)
        if not os.path.exists(local):
            print('  yok       %s (atlandi)' % name)
            continue
        sent, skipped, failed = gonder(local, name, sent, skipped, failed)

    # 2) board layer - overwrites anything with the same name on purpose
    for name in sorted(os.listdir(BOARD_DIR)):
        if name in frozen_names:
            continue
        if name == 'config.json' and not WITH_CONFIG:
            print('  atlandi   config.json (yazmak icin --config)')
            continue
        local = os.path.join(BOARD_DIR, name)
        if not os.path.isfile(local):
            continue
        sent, skipped, failed = gonder(local, name, sent, skipped, failed)

    # 3) samples
    if SAMPLES:
        mp('fs', 'mkdir', ':projects')
        sdir = os.path.join(DEV, 'samples')
        if os.path.isdir(sdir):
            for name in sorted(os.listdir(sdir)):
                if name.endswith('.py'):
                    if push(os.path.join(sdir, name), 'projects/' + name):
                        sent += 1
                    else:
                        failed += 1

    print('\n%d yuklendi, %d degismemis, %d hata' % (sent, skipped, failed))
    if '--reset' in sys.argv:
        mp('reset')
        print('reset atildi')
    elif sent and not failed:
        print('reset icin: python tools/bootlog.py %s 25' % PORT)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
