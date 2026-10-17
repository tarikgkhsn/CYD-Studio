# logstore.py - proje basina KALICI log. Reset'ten sonra da durur.
#
# Neden dosya: solo modda panel kapali oldugu icin RAM'deki log kimseye
# ulasmadan resetle birlikte ucuyor. Dosyaya yazinca proje tek basina
# calisir, sen sonra panele girip logunu okursun.
#
# Flash omru: her satiri diske yazmak gereksiz asinma yaratir, bu yuzden
# satirlar RAM'de biriktirilip toplu yaziliyor.
import os

DIZIN = '/logs'
MAX_BAYT = 8192          # proje basina ust sinir; asinca bastan yarisi atilir
TAMPON_SATIR = 12        # kac satirda bir diske yazilsin
TAMPON_BAYT = 512

_tampon = {}             # proje -> [satir, ...]


def _hazirla():
    try:
        os.mkdir(DIZIN)
    except OSError:
        pass


def _guvenli(ad):
    ad = (ad or 'bilinmeyen').replace('\\', '/').rsplit('/', 1)[-1]
    temiz = ''.join(c if (c.isalpha() or c.isdigit() or c in '._-') else '_'
                    for c in ad)
    return temiz[:40] or 'bilinmeyen'


def yol(proje):
    return '%s/%s.log' % (DIZIN, _guvenli(proje))


def ekle(proje, satir):
    """Satiri tampona koy, doluysa diske yaz."""
    b = _tampon.setdefault(proje, [])
    b.append(satir)
    if len(b) >= TAMPON_SATIR or sum(len(x) for x in b) >= TAMPON_BAYT:
        bosalt(proje)


def bosalt(proje=None):
    """Tamponu diske yaz. proje=None ise hepsini."""
    if proje is None:
        for p in list(_tampon):
            bosalt(p)
        return
    satirlar = _tampon.get(proje)
    if not satirlar:
        return
    _tampon[proje] = []
    _hazirla()
    p = yol(proje)
    try:
        with open(p, 'a') as f:
            for s in satirlar:
                f.write(s)
                f.write('\n')
    except OSError:
        return
    _kirp(p)


def _kirp(p):
    """Dosya sinirin ustune ciktiysa bastan yarisini at."""
    try:
        boyut = os.stat(p)[6]
    except OSError:
        return
    if boyut <= MAX_BAYT:
        return
    try:
        with open(p, 'rb') as f:
            f.seek(boyut - MAX_BAYT // 2)
            kuyruk = f.read()
        # ilk yarim satiri at, temiz baslasin
        n = kuyruk.find(b'\n')
        if 0 <= n < len(kuyruk) - 1:
            kuyruk = kuyruk[n + 1:]
        with open(p, 'wb') as f:
            f.write(b'--- eski kayitlar silindi (sinir %d bayt) ---\n' % MAX_BAYT)
            f.write(kuyruk)
    except OSError:
        pass


def oku(proje, max_bayt=6144):
    """Logun sonundan max_bayt kadarini dondurur."""
    bosalt(proje)
    p = yol(proje)
    try:
        boyut = os.stat(p)[6]
    except OSError:
        return ''
    try:
        with open(p, 'rb') as f:
            if boyut > max_bayt:
                f.seek(boyut - max_bayt)
                veri = f.read()
                n = veri.find(b'\n')
                if 0 <= n < len(veri) - 1:
                    veri = veri[n + 1:]
            else:
                veri = f.read()
        return veri.decode('utf-8', 'replace')
    except OSError:
        return ''


def sil(proje):
    _tampon.pop(proje, None)
    try:
        os.remove(yol(proje))
        return True
    except OSError:
        return False


def liste():
    """[{ad, boyut}] - logu olan projeler."""
    _hazirla()
    out = []
    try:
        for f in os.listdir(DIZIN):
            if not f.endswith('.log'):
                continue
            try:
                st = os.stat(DIZIN + '/' + f)
                out.append({'ad': f[:-4], 'boyut': st[6]})
            except OSError:
                pass
    except OSError:
        pass
    out.sort(key=lambda e: e['ad'])
    return out


def toplam_boyut():
    return sum(e['boyut'] for e in liste())
