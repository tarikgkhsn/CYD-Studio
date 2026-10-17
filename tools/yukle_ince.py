"""Strip comments from a project and upload it to a low-memory board.

Why this exists: jobs.py runs a project by reading the whole source into a
string and calling compile() on it. On the ESP8266 the compiler wants
several times the source size, so a well-commented 4.7 KB project dies with
MemoryError while a 3.4 KB one runs fine. The comments are exactly the part
the board does not need.

So the repo keeps the documented source and the board gets the lean bytes.
Comments are removed with tokenize, not a regex, so a '#' inside a string
survives.

    python tools/yukle_ince.py device/samples/sicaklik_led.py 192.168.0.215
    python tools/yukle_ince.py <dosya> <ip> [karttaki_ad]
"""
import io
import os
import sys
import tokenize
import urllib.request


def yorumsuz(kaynak):
    """Yorumlari ve bos satirlari atar. Docstring'ler kalir - onlar kod."""
    satirlar = kaynak.splitlines(True)
    kes = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(kaynak).readline):
            if tok.type == tokenize.COMMENT:
                kes.setdefault(tok.start[0], tok.start[1])
    except tokenize.TokenError as e:
        sys.exit('tokenize hatasi: %s' % e)

    cikti = []
    for no, s in enumerate(satirlar, 1):
        if no in kes:
            s = s[:kes[no]].rstrip()
            if not s:
                continue
            s += '\n'
        if s.strip():
            cikti.append(s)
    return ''.join(cikti)


if len(sys.argv) < 3:
    sys.exit(__doc__)

yerel = sys.argv[1]
ip = sys.argv[2]
ad = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(yerel)

kaynak = io.open(yerel, encoding='utf-8').read()
ince = yorumsuz(kaynak)

# Uretilen kod hala gecerli mi - karta bozuk dosya gondermeyelim
compile(ince, ad, 'exec')

ham = ince.encode('utf-8')
print('%s' % ad)
print('  orijinal : %5d bayt' % len(kaynak.encode('utf-8')))
print('  incelmis : %5d bayt  (%%%.0f kucuk)'
      % (len(ham), 100 - len(ham) * 100.0 / len(kaynak.encode('utf-8'))))

u = 'http://%s/api/save?name=%s' % (ip, ad)
try:
    c = urllib.request.urlopen(u, data=ham, timeout=30).read().decode()
except Exception as e:
    sys.exit('  yuklenemedi: %s' % e)
print('  yuklendi :', c[:120])
