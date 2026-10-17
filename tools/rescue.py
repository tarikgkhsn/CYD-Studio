"""Catch a board that brown-outs before you can talk to it.

main.py brings Wi-Fi up a fraction of a second after boot and the board
resets, so there is no steady window for mpremote. This keeps the port
open (reopening it every time USB drops) and streams Ctrl-C at the board,
so the very first thing MicroPython sees after boot is an interrupt. Once
the REPL prompt appears we rename main.py and the loop is broken.

    python tools/rescue.py COM4 off   # main.py -> main.off
    python tools/rescue.py COM4 on    # geri al
"""
import sys
import time

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM4'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'off'
LIMIT = float(sys.argv[3]) if len(sys.argv) > 3 else 180.0

if MODE == 'off':
    KOMUT = "import os\r\nos.rename('main.py','main.off')\r\n"
    BEKLENEN = 'main.off'
else:
    KOMUT = "import os\r\nos.rename('main.off','main.py')\r\n"
    BEKLENEN = 'main.py'


def ac():
    p = serial.Serial()
    p.port = PORT
    p.baudrate = 115200
    p.timeout = 0.05
    p.dsrdtr = False
    p.rtscts = False
    p.open()
    p.rts = False          # EN yuksek - cipi resette tutma
    p.dtr = False
    return p


print('%s kurtariliyor (%.0f sn) - Ctrl-C yagdiriliyor' % (PORT, LIMIT))
son = time.time() + LIMIT
p = None
buf = ''
prompt_gorulen = 0

while time.time() < son:
    if p is None:
        try:
            p = ac()
            buf = ''
            print('  port acildi')
        except Exception:
            time.sleep(0.3)
            continue

    try:
        p.write(b'\x03')              # Ctrl-C: calisani kes
        d = p.read(256)
    except Exception:
        try:
            p.close()
        except Exception:
            pass
        p = None
        time.sleep(0.2)
        continue

    if d:
        buf += d.decode('utf-8', 'replace')
        buf = buf[-4000:]

        if '>>>' in buf and prompt_gorulen == 0:
            prompt_gorulen = 1
            print('  REPL YAKALANDI - komut gonderiliyor')
            try:
                p.write(b'\r\n')
                time.sleep(0.2)
                p.write(KOMUT.encode())
                time.sleep(1.0)
                p.write(b"import os; print('DOSYALAR:', os.listdir('/'))\r\n")
                time.sleep(1.0)
                d2 = p.read(4000)
                cikti = d2.decode('utf-8', 'replace')
                print(cikti)
                if BEKLENEN in cikti:
                    print('BASARILI: %s' % BEKLENEN)
                    p.rts = False
                    p.dtr = False
                    p.close()
                    sys.exit(0)
                prompt_gorulen = 0     # tutmadi, devam
            except Exception as e:
                print('  komut gonderilemedi:', e)
                prompt_gorulen = 0

    time.sleep(0.02)

if p:
    try:
        p.rts = False
        p.dtr = False
        p.close()
    except Exception:
        pass
print('BASARISIZ - REPL yakalanamadi')
sys.exit(1)
