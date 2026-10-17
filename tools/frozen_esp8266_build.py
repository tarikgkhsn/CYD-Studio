"""Build the frozen ESP8266 firmware: CYD Studio's core baked into the image.

Why: on the NodeMCU the core (server, jobs, runtime, ...) used to be loaded
into a 38 KB heap and left 2.5-4.8 KB free - too little to even compile a
3 KB project. Frozen modules live in flash and execute from there, which
measured 24.7 KB free in panel mode instead. Projects stay ordinary .py
files on the filesystem, so the browser edit-and-run workflow is unchanged.

The build runs inside WSL Ubuntu, where the toolchain lives. One-time setup
is documented in CLAUDE.md ("ESP8266: çekirdek firmware'e gömülü"). This
script does the per-build chain:

  1. stage the module set   -> ~/cydstudio-frozen/modules
  2. write the manifest     -> stock frozen list + ours
  3. make ports/esp8266     -> FROZEN_MANIFEST=... ESPTOOL=esptool
  4. copy the .bin back     -> firmware/micropython-esp8266-frozen.bin

Afterwards:
    python tools/flash_esp8266.py COM3
    python tools/deploy_mpy.py --board nodemcu --port COM3 --frozen --config --samples

    python tools/frozen_esp8266_build.py            # build
    python tools/frozen_esp8266_build.py --check    # verify prerequisites only
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Must stay in step with deploy_mpy.DERLE - the same modules that used to be
# shipped as .mpy are the ones frozen now.
CEKIRDEK = ['runtime', 'jobs', 'sysinfo', 'logstore', 'settings', 'netmgr', 'store']
BOARD = 'nodemcu'          # every boards/<BOARD>/*.py is frozen; its server.py
                           # overrides device/server.py (the lite server)
CIKTI = 'micropython-esp8266-frozen.bin'


def wsl_yolu(win):
    """C:\\Users\\x -> /mnt/c/Users/x"""
    win = os.path.abspath(win).replace('\\', '/')
    return '/mnt/' + win[0].lower() + win[2:]


SRC = wsl_yolu(ROOT)

KONTROL = r'''
set -e
ok=1
t() { if eval "$2" >/dev/null 2>&1; then echo "  [x] $1"; else echo "  [ ] $1"; ok=0; fi; }
t "make / gcc"                 "which make gcc"
t "esptool (apt/pip)"          "which esptool"
t "python -> python3"          "which python"
t "~/micropython v1.28.0"      "test -f $HOME/micropython/ports/esp8266/Makefile"
t "mpy-cross derlenmis"        "test -x $HOME/micropython/mpy-cross/build/mpy-cross"
t "submodules (axtls)"         "test -f $HOME/micropython/lib/axtls/Makefile"
t "xtensa-lx106-elf-gcc"       "test -x $HOME/xtensa-lx106-elf/bin/xtensa-lx106-elf-gcc"
t "eski esptool.py SILINMIS"   "test ! -e $HOME/xtensa-lx106-elf/bin/esptool.py"
t "kaynak erisilebilir"        "test -d SRC_YOLU/device"
[ $ok = 1 ] && echo "HAZIR" || echo "EKSIK - CLAUDE.md kurulum adimlarina bak"
'''.replace('SRC_YOLU', SRC)

DERLEME = r'''
set -e
SRC=SRC_YOLU
ST=$HOME/cydstudio-frozen
export PATH=$HOME/xtensa-lx106-elf/bin:$PATH
rm -rf $ST && mkdir -p $ST/modules
for f in CEKIRDEK_LISTE; do cp $SRC/device/$f.py $ST/modules/; done
cp $SRC/boards/BOARD_ADI/*.py $ST/modules/
# Tek tirnak: $(PORT_DIR) manifest araci icin literal kalmali, bash acmamali.
printf '# CYD Studio - NodeMCU icin dondurulmus cekirdek (tools/frozen_esp8266_build.py uretir).\n# Stok listeyi koru, ustune asyncio (normal mod gorevleri) ve bizim moduller.\ninclude("$(PORT_DIR)/boards/manifest.py")\ninclude("$(MPY_DIR)/extmod/asyncio")\nfreeze("%s/modules")\n' "$ST" > $ST/manifest.py
# execfile: normal mod donusturulmus kaynagi DOSYADAN derler (string heap'e
# girmez). ESP8266 portu kapali tutuyor; bizim derlemede aciyoruz.
sed -i 's/^#define MICROPY_PY_BUILTINS_EXECFILE            (0)$/#define MICROPY_PY_BUILTINS_EXECFILE            (1)/' $HOME/micropython/ports/esp8266/mpconfigport.h
grep -n "MICROPY_PY_BUILTINS_EXECFILE" $HOME/micropython/ports/esp8266/mpconfigport.h
echo "=== sahne ==="; ls $ST/modules | tr '\n' ' '; echo
echo "=== derleme ==="
make -C $HOME/micropython/ports/esp8266 BOARD=ESP8266_GENERIC ESPTOOL=esptool \
     FROZEN_MANIFEST=$ST/manifest.py -j8 2>&1 | tee $ST/build.log | grep -E "^MPY |error|Error|irom0text|^total" || true
B=$HOME/micropython/ports/esp8266/build-ESP8266_GENERIC
test -f $B/firmware.bin || { echo "FIRMWARE YOK - derleme basarisiz"; exit 1; }
echo "=== dondurulan modullerimiz imajda mi ==="
# "^MPY x.py" satiri tam eslesir; "store" gibi bir ad "logstore" ile karismaz.
# Degismemis dosya yeniden derlenmezse o satir cikmaz; o zaman frozen_content.c
# icinde tirnakli dosya adina bakiyoruz.
for m in $(ls $ST/modules | sed 's/\.py$//'); do
  if grep -q "^MPY $m\.py" $ST/build.log || grep -q "\"$m\.py\"" $B/frozen_content.c; then
    echo "  [x] $m"
  else
    echo "  [ ] $m  <-- YOK"; exit 1
  fi
done
cp $B/firmware.bin $SRC/firmware/CIKTI_ADI
cp $ST/manifest.py $SRC/firmware/esp8266-frozen-manifest.py
echo "=== bitti ==="; ls -l $SRC/firmware/CIKTI_ADI
'''.replace('SRC_YOLU', SRC).replace('CEKIRDEK_LISTE', ' '.join(CEKIRDEK)) \
   .replace('BOARD_ADI', BOARD).replace('CIKTI_ADI', CIKTI)


def wsl(script, timeout):
    # Windows -> wsl.exe -> bash quoting is fragile for a multi-line script;
    # writing it to a file and running that sidesteps it entirely.
    yol = os.path.join(ROOT, 'firmware', '_frozen_build.sh')
    with open(yol, 'w', encoding='utf-8', newline='\n') as f:
        f.write(script)
    try:
        r = subprocess.run(['wsl', '-e', 'bash', wsl_yolu(yol)], timeout=timeout)
        return r.returncode
    finally:
        try:
            os.remove(yol)
        except OSError:
            pass


if '--check' in sys.argv:
    print('WSL on kosullari:')
    sys.exit(wsl(KONTROL, 60))

print('WSL on kosullari:')
if wsl(KONTROL, 60) != 0:
    sys.exit(1)
print()
rc = wsl(DERLEME, 900)
if rc != 0:
    sys.exit('derleme basarisiz (kod %d)' % rc)
out = os.path.join(ROOT, 'firmware', CIKTI)
print()
print('firmware/%s  %d bayt' % (CIKTI, os.path.getsize(out)))
print('sonraki adim: python tools/flash_esp8266.py COM3')
