"""Listen passively to the bridged target's serial output.

Unlike kopru_repl.py this sends NOTHING - it just prints whatever the
target says. That makes it the right tool for catching boot messages and
crash reasons, above all the ESP32 ROM line:

    Brownout detector was triggered

which settles the power question for good. Reset the target while this
is running.

    python tools/kopru_dinle.py [192.168.0.217] [saniye]
"""
import re
import socket
import sys
import time

IP = sys.argv[1] if len(sys.argv) > 1 else '192.168.0.217'
SURE = int(sys.argv[2]) if len(sys.argv) > 2 else 60
PORT = 2323

ISARETLER = [
    (r'[Bb]rownout', 'BROWNOUT - besleme yetersiz, gerilim cokuyor'),
    (r'rst:0x[0-9a-f]+', 'reset sebebi'),
    (r'[Gg]uru [Mm]editation', 'cekirdek panigi'),
    (r'[Ww]atchdog|wdt', 'watchdog resetledi'),
    (r'MicroPython', 'MicroPython acildi'),
    (r'Traceback', 'Python hatasi'),
    (r'[Nn]etwork config|ifconfig|WiFi|wifi', 'ag katmani'),
]

print('Dinleniyor: %s:%d  (%d sn)' % (IP, PORT, SURE))
print('Hicbir sey gondermiyorum - sadece okuyorum.')
print('SIMDI hedefe RESET at (BOOT basili OLMASIN).')
print('-' * 62)

s = socket.socket()
s.settimeout(5)
try:
    s.connect((IP, PORT))
except OSError as e:
    print('Koprüye baglanilamadi: %s' % e)
    print()
    print('  - CYD panelinde kopru_uart.py calisiyor mu?')
    print('  - CYD nin IP si %s mi?' % IP)
    sys.exit(1)

s.settimeout(1)
bitis = time.time() + SURE
tampon = b''
toplam = 0
bulgular = []

try:
    while time.time() < bitis:
        try:
            veri = s.recv(1024)
        except socket.timeout:
            continue
        except OSError:
            break
        if not veri:
            print('\n[koprü baglantiyi kapatti]')
            break
        toplam += len(veri)
        tampon += veri
        while b'\n' in tampon:
            satir, tampon = tampon.split(b'\n', 1)
            metin = satir.decode('utf-8', 'replace').rstrip('\r')
            if not metin.strip():
                continue
            print(' ', metin)
            for desen, ad in ISARETLER:
                if re.search(desen, metin) and ad not in bulgular:
                    bulgular.append(ad)
except KeyboardInterrupt:
    print('\n[durduruldu]')
finally:
    try:
        s.close()
    except Exception:
        pass

if tampon.strip():
    print(' ', tampon.decode('utf-8', 'replace').rstrip())

print('-' * 62)
print('%d bayt alindi' % toplam)

if toplam == 0:
    print()
    print('HIC VERI YOK. Ihtimaller:')
    print('  - Hedef hic calismiyor (besleme yok / regulator olu)')
    print('  - Hedefin TX i CYD GPIO22 ye bagli degil')
    print('  - Ortak GND yok')
    print('  - RESET atmadin')
elif bulgular:
    print()
    print('Gorulenler:')
    for b in bulgular:
        print('  *', b)
