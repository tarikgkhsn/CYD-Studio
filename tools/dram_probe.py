"""Where does the internal DRAM go while the panel is running?

Each HTTP request the UI makes is its own TCP connection (Connection:
close), and lwIP parks every closed socket in TIME_WAIT for about a
minute. If that is what is eating DRAM, leaving the board alone for 70
seconds should hand a large chunk of it back.
"""
import json
import sys
import time
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else '192.168.0.217'
BASE = 'http://%s' % HOST


def dram():
    with urllib.request.urlopen(BASE + '/api/status', timeout=15) as r:
        d = json.load(r)
    i = d['sys']['idf']
    return i['free'] // 1024, d['sys']['ram_free'] // 1024


print('TARAYICI SEKMELERINI KAPAT, sonra bu test dogru olcer.\n')

f, m = dram()
print('simdi          : DRAM %3d KB | MicroPython heap %3d KB' % (f, m))

print('70 saniye hic istek atilmiyor...')
time.sleep(70)

f2, m2 = dram()
print('70 sn sonra    : DRAM %3d KB | MicroPython heap %3d KB' % (f2, m2))
print('DRAM farki     : %+d KB' % (f2 - f))

if f2 - f > 15:
    print('\n-> Sonuc: DRAM kayan TCP baglantilarinda (TIME_WAIT) duruyordu.')
    print('   Panel bosta dururken proje icin yeterli bellek kaliyor.')
else:
    print('\n-> Sonuc: TIME_WAIT degil; bellegi kalici bir sey tutuyor.')
