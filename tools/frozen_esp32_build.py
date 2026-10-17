"""Build the CYD Studio firmware for the ESP32 (CYD): core frozen + RAM diet.

Why (measured 10 Sep 2026 on the CYD, stock v1.28.0 ESP32_GENERIC):
  * panel idle: internal DRAM 27 KB free; one running project takes 15-18 KB
    of it (FreeRTOS thread stack) -> the SECOND project fails with
    "can't create thread" while the Python heap still shows 34 KB free.
  * v1.28.0 uses an auto-growing split heap: Python grabs blocks from the
    same internal DRAM the thread stacks and lwIP need. Every KB the core
    does not load into the heap stays available for projects.

What this build changes vs stock ESP32_GENERIC (a new board "CYD_STUDIO"):
  1. boards/sdkconfig.free_ram (ships with MicroPython): smaller lwIP
     windows (5760 -> 3072), fewer Wi-Fi buffers, FreeRTOS/heap/ringbuf
     functions in flash, BT controller in flash.
  2. FIXED Python heap (default 96 KB, --heap N) instead of the auto-growing
     split heap. Measured on stock: the heap DOUBLES itself (64 -> 128 KB)
     the first time a project needs a bit more, grabbing up to the largest
     free DRAM block in one go - internal DRAM fell 76 -> 12 KB with two
     small projects and lwIP starved (panel stalled 16 s, watchdog killed
     the projects). A fixed heap makes the split predictable: what the panel
     shows as "Python RAM" is exactly what projects get, and the rest stays
     for thread stacks / sockets. (mpconfigport.h gets a 2-line #ifndef
     guard around MICROPY_GC_SPLIT_HEAP_AUTO so the board can turn it off.)
  3. Our core modules frozen (bytecode executed from flash):
       device/  runtime jobs sysinfo logstore settings netmgr store server
       boards/cyd/  cyd ili9341 xpt2046 sdcard
     boot.py / main.py / index.html / docs.md stay on the filesystem so the
     recovery path (rename main.py) and the streamed HTML are unchanged.
  Projects stay ordinary .py files - the browser edit-and-run flow is intact.

Runs inside WSL Ubuntu where ESP-IDF v5.5.1 lives (~/esp-idf, installed by
`install.sh esp32`; see CLAUDE.md). Per-build chain:

  1. stage modules            -> ~/cydstudio-frozen-esp32/modules
  2. write board dir          -> ~/micropython/ports/esp32/boards/CYD_STUDIO
  3. make BOARD=CYD_STUDIO    -> build-CYD_STUDIO/firmware.bin
  4. copy back                -> firmware/micropython-esp32-cydstudio.bin

Afterwards (CYD needs the BOOT-held flash procedure, CLAUDE.md §3):
    python tools/flash.py COM3 firmware/micropython-esp32-cydstudio.bin
    python tools/deploy.py --board cyd --port COM3 --frozen --samples

    python tools/frozen_esp32_build.py            # build
    python tools/frozen_esp32_build.py --check    # prerequisites only
    python tools/frozen_esp32_build.py --stock    # same board, NO frozen/diet
                                                  # (A/B baseline, if wanted)
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CEKIRDEK = ['runtime', 'jobs', 'sysinfo', 'logstore', 'settings', 'netmgr',
            'store', 'server']
BOARD = 'cyd'
CIKTI = 'micropython-esp32-cydstudio.bin'
MP_BOARD = 'CYD_STUDIO'
HEAP_KB = 96               # --heap N overrides


def wsl_yolu(win):
    win = os.path.abspath(win).replace('\\', '/')
    return '/mnt/' + win[0].lower() + win[2:]


SRC = wsl_yolu(ROOT)

KONTROL = r'''
ok=1
t() { if eval "$2" >/dev/null 2>&1; then echo "  [x] $1"; else echo "  [ ] $1"; ok=0; fi; }
t "~/micropython v1.28.0"      "test -f $HOME/micropython/ports/esp32/Makefile"
t "~/esp-idf v5.5.1"           "grep -q 'v5.5.1' $HOME/esp-idf/version.txt 2>/dev/null || git -C $HOME/esp-idf describe --tags | grep -q v5.5.1"
t "idf.py (export.sh)"         "source $HOME/esp-idf/export.sh && which idf.py"
t "xtensa-esp32-elf-gcc"       "source $HOME/esp-idf/export.sh && which xtensa-esp32-elf-gcc"
t "cmake / ninja"              "which cmake ninja"
t "sdkconfig.free_ram var"     "test -f $HOME/micropython/ports/esp32/boards/sdkconfig.free_ram"
t "kaynak erisilebilir"        "test -d SRC_YOLU/device"
[ $ok = 1 ] && echo "HAZIR" || { echo "EKSIK - CLAUDE.md kurulum adimlarina bak"; exit 1; }
'''.replace('SRC_YOLU', SRC)

DERLEME = r'''
set -e
SRC=SRC_YOLU
ST=$HOME/cydstudio-frozen-esp32
PORTDIR=$HOME/micropython/ports/esp32
BD=$PORTDIR/boards/MP_BOARD_ADI
source $HOME/esp-idf/export.sh >/dev/null
rm -rf $ST && mkdir -p $ST/modules
if [ "STOK_MU" != "1" ]; then
  for f in CEKIRDEK_LISTE; do cp $SRC/device/$f.py $ST/modules/; done
  cp $SRC/boards/BOARD_ADI/*.py $ST/modules/
fi
rm -rf $BD && mkdir -p $BD
cat > $BD/mpconfigboard.h <<'EOF'
#define MICROPY_HW_BOARD_NAME "CYD Studio"
#define MICROPY_HW_MCU_NAME "ESP32"
EOF
if [ "STOK_MU" != "1" ]; then
cat >> $BD/mpconfigboard.h <<'EOF'
// Sabit Python heap'i: otomatik buyume (ikiye katlama) DRAM'i yutuyordu.
#define MICROPY_GC_INITIAL_HEAP_SIZE (HEAP_KB_DEGERI * 1024)
#define MICROPY_GC_SPLIT_HEAP_AUTO (0)
// py/mpconfig.h bunlari yalniz AUTO acikken tanimliyor; main.c yine kullaniyor.
#define MP_PLAT_ALLOC_HEAP(size) malloc(size)
#define MP_PLAT_FREE_HEAP(ptr) free(ptr)
EOF
# mpconfigport.h AUTO'yu kosulsuz tanimliyor; karta izin veren 2 satirlik koruma.
grep -q "ifndef MICROPY_GC_SPLIT_HEAP_AUTO" $PORTDIR/mpconfigport.h || \
  python3 - "$PORTDIR/mpconfigport.h" <<'PYEOF'
import sys, re
p = sys.argv[1]; s = open(p).read()
s2 = re.sub(r'^(#define MICROPY_GC_SPLIT_HEAP_AUTO\s+\(1\))$',
            r'#ifndef MICROPY_GC_SPLIT_HEAP_AUTO\n\1\n#endif', s, count=1, flags=re.M)
assert s2 != s, 'MICROPY_GC_SPLIT_HEAP_AUTO satiri bulunamadi'
open(p, 'w').write(s2)
PYEOF
grep -n -A2 "ifndef MICROPY_GC_SPLIT_HEAP_AUTO" $PORTDIR/mpconfigport.h | head -3
fi
if [ "STOK_MU" = "1" ]; then
cat > $BD/mpconfigboard.cmake <<'EOF'
set(SDKCONFIG_DEFAULTS boards/sdkconfig.base boards/sdkconfig.ble)
EOF
else
cat > $BD/mpconfigboard.cmake <<'EOF'
set(SDKCONFIG_DEFAULTS boards/sdkconfig.base boards/sdkconfig.ble boards/sdkconfig.free_ram)
set(MICROPY_FROZEN_MANIFEST ${MICROPY_BOARD_DIR}/manifest.py)
EOF
printf '# CYD Studio - CYD icin dondurulmus cekirdek (tools/frozen_esp32_build.py uretir).\ninclude("$(PORT_DIR)/boards/manifest.py")\nfreeze("%s/modules")\n' "$ST" > $BD/manifest.py
cp $BD/manifest.py $SRC/firmware/esp32-frozen-manifest.py
fi
cat > $BD/board.json <<'EOF'
{"deploy": ["../deploy.md"], "docs": "", "features": [], "id": "CYD_STUDIO", "images": [], "mcu": "esp32", "product": "CYD Studio", "thumbnail": "", "url": "", "vendor": "CYD Studio"}
EOF
echo "=== sahne ==="; ls $ST/modules 2>/dev/null | tr '\n' ' '; echo
echo "=== derleme (ilk sefer 10-20 dk) ==="
make -C $PORTDIR BOARD=MP_BOARD_ADI -j$(nproc) > $ST/build.log 2>&1 || { tail -40 $ST/build.log; echo "DERLEME BASARISIZ"; exit 1; }
grep -E "^MPY |frozen|firmware.bin|bytes" $ST/build.log | tail -12 || true
B=$PORTDIR/build-MP_BOARD_ADI
test -f $B/firmware.bin || { echo "FIRMWARE YOK"; exit 1; }
if [ "STOK_MU" != "1" ]; then
echo "=== dondurulan modullerimiz imajda mi ==="
for m in $(ls $ST/modules | sed 's/\.py$//'); do
  if grep -rq "\"$m\.py\"" $B/frozen_content.c; then echo "  [x] $m"; else echo "  [ ] $m  <-- YOK"; exit 1; fi
done
fi
echo "=== onemli sdkconfig degerleri ==="
grep -E "^CONFIG_(LWIP_TCP_WND_DEFAULT|LWIP_TCP_SND_BUF_DEFAULT|LWIP_MAX_SOCKETS|ESP_WIFI_STATIC_RX_BUFFER_NUM|ESP_WIFI_DYNAMIC_RX_BUFFER_NUM|ESP_WIFI_DYNAMIC_TX_BUFFER_NUM|BT_CTRL_RUN_IN_FLASH_ONLY|FREERTOS_PLACE_FUNCTIONS_INTO_FLASH)=" $B/sdkconfig || true
cp $B/firmware.bin $SRC/firmware/CIKTI_ADI
echo "=== bitti ==="; ls -l $SRC/firmware/CIKTI_ADI
'''.replace('SRC_YOLU', SRC).replace('CEKIRDEK_LISTE', ' '.join(CEKIRDEK)) \
   .replace('MP_BOARD_ADI', MP_BOARD).replace('BOARD_ADI', BOARD)


def wsl(script, timeout):
    yol = os.path.join(ROOT, 'firmware', '_frozen_build_esp32.sh')
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
    sys.exit(wsl(KONTROL, 120))

stok = '1' if '--stock' in sys.argv else '0'
cikti = CIKTI if stok == '0' else 'micropython-esp32-cydstudio-stock.bin'
print('WSL on kosullari:')
if wsl(KONTROL, 120) != 0:
    sys.exit(1)
print()
heap_kb = HEAP_KB
if '--heap' in sys.argv:
    heap_kb = int(sys.argv[sys.argv.index('--heap') + 1])
print('Python heap: %d KB (sabit)' % heap_kb)
rc = wsl(DERLEME.replace('STOK_MU', stok).replace('CIKTI_ADI', cikti)
         .replace('HEAP_KB_DEGERI', str(heap_kb)), 2400)
if rc != 0:
    sys.exit('derleme basarisiz (kod %d)' % rc)
out = os.path.join(ROOT, 'firmware', cikti)
print()
print('firmware/%s  %d bayt' % (cikti, os.path.getsize(out)))
print('sonraki adim: python tools/flash.py COM3 firmware/%s' % cikti)
