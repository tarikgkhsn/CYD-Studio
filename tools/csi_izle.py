"""Read CSI from the board and turn it into a motion reading.

The sketch streams one line per received packet:

    CSI,<sira>,<rssi>,<adet>,<genlik0>,<genlik1>,...

Each amplitude is one OFDM subcarrier - a separate measurement of one
propagation path. A person moving changes some paths and leaves others
alone, so the useful signal is not the average level (that is RSSI, and
it barely moves) but how much the subcarriers WOBBLE over a short window.

Method:
  * keep a sliding window of the last N samples
  * per subcarrier, standard deviation across that window
  * average those deviations -> one "wobble" number per instant
  * calibrate the quiet-room level first, then flag departures from it

Calibration matters: every room has a different baseline. Stand still
while it runs, or better, leave the room.

    python tools/csi_izle.py [COM3] [--kalibrasyon 15] [--esik 3.5]
"""
import argparse
import collections
import math
import sys
import time

try:
    import serial
except ImportError:
    sys.exit('pyserial yok:  pip install pyserial')

p = argparse.ArgumentParser()
p.add_argument('port', nargs='?', default='COM3')
p.add_argument('--baud', type=int, default=921600)
p.add_argument('--pencere', type=int, default=40,
               help='kac ornek uzerinden oynama olculsun')
p.add_argument('--kalibrasyon', type=float, default=15.0,
               help='sessiz oda olcumu, saniye')
p.add_argument('--esik', type=float, default=3.5,
               help='taban gurultunun kac katinda hareket sayilsin')
p.add_argument('--sure', type=float, default=0.0,
               help='0 = sonsuz')
a = p.parse_args()

try:
    ser = serial.Serial(a.port, a.baud, timeout=1)
except Exception as e:
    sys.exit('%s acilamadi: %s' % (a.port, e))

print('CSI izleniyor: %s @%d' % (a.port, a.baud))
print()

pencere = collections.deque(maxlen=a.pencere)
alt_sayi = None


def oynama():
    """Alt tasiyici bazinda standart sapma, sonra ortalamasi."""
    n = len(pencere)
    if n < max(8, a.pencere // 2):
        return None
    k = min(len(x) for x in pencere)
    if not k:
        return None
    toplam = 0.0
    for i in range(k):
        s = 0.0
        s2 = 0.0
        for x in pencere:
            v = x[i]
            s += v
            s2 += v * v
        ort = s / n
        var = s2 / n - ort * ort
        toplam += math.sqrt(var) if var > 0 else 0.0
    return toplam / k


def cizgi(deger, tavan, genislik=34):
    if tavan <= 0:
        return ' ' * genislik
    d = int(min(1.0, deger / tavan) * genislik)
    return '#' * d + '.' * (genislik - d)


basla = time.time()
kal_bitis = basla + a.kalibrasyon
kal_ornek = []
taban = None
esik = None
son_yaz = 0.0
paket = 0
son_sn = time.time()
hiz = 0
son_durum = None

try:
    while True:
        ham = ser.readline()
        if not ham:
            continue
        try:
            s = ham.decode('ascii', 'ignore').strip()
        except Exception:
            continue
        if s.startswith('#'):
            print(' ', s)
            continue
        if not s.startswith('CSI,'):
            continue
        parca = s.split(',')
        if len(parca) < 5:
            continue
        try:
            genlik = [int(v) for v in parca[4:]]
        except ValueError:
            continue
        if not genlik:
            continue
        if alt_sayi is None:
            alt_sayi = len(genlik)
            print('  alt tasiyici sayisi: %d' % alt_sayi)
        pencere.append(genlik)
        paket += 1
        hiz += 1

        simdi = time.time()
        if simdi - son_sn >= 1.0:
            oran = hiz / (simdi - son_sn)
            hiz = 0
            son_sn = simdi
        else:
            oran = None

        o = oynama()
        if o is None:
            continue

        # --- kalibrasyon
        if taban is None:
            kal_ornek.append(o)
            if simdi - son_yaz > 0.5:
                son_yaz = simdi
                kalan = kal_bitis - simdi
                print('\r  KALIBRASYON  kipirdamayin  %4.1f sn  (oynama %.2f)'
                      % (max(0, kalan), o), end='')
            if simdi >= kal_bitis and len(kal_ornek) > 10:
                kal_ornek.sort()
                orta = kal_ornek[len(kal_ornek) // 2]
                sapma = sum(abs(x - orta) for x in kal_ornek) / len(kal_ornek)
                taban = orta
                esik = taban + a.esik * max(sapma, 0.05)
                print('\r' + ' ' * 70)
                print('  taban oynama : %.2f' % taban)
                print('  gurultu      : %.2f' % sapma)
                print('  esik         : %.2f  (%.1fx)' % (esik, a.esik))
                print()
            continue

        # --- izleme
        hareket = o > esik
        if simdi - son_yaz > 0.15:
            son_yaz = simdi
            durum = 'HAREKET VAR' if hareket else 'sakin      '
            hz = ('%5.0f/sn' % oran) if oran else '        '
            print('\r  %s  %6.2f  [%s]  esik %.2f  %s'
                  % (durum, o, cizgi(o, esik * 3), esik, hz), end='')
            if hareket != son_durum:
                son_durum = hareket
        if a.sure and simdi - basla > a.sure:
            break
except KeyboardInterrupt:
    print()
    print('durduruldu')
finally:
    ser.close()
    print()
    print('%d CSI ornegi islendi' % paket)
