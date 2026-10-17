# usbkopru.py - panel USB kablosundan: WiFi olmadan da calisir.
#
# PC'deki tools/usb_panel.py tarayici isteklerini seri porttan buraya
# iletir; burasi ayni sunucu isleyicisini (server._route) sahte bir
# baglanti nesnesiyle calistirip HTTP cevabini geri yazar. Yani panel,
# API, projeler - ne varsa - kablodan da aynen calisir.
#
# Cerceve (tek satir, base64: icinde Ctrl-C/Ctrl-D olamaz, REPL'i bozmaz):
#   PC  -> kart : ~CYDB~<id>~<b64 parca>\n   (buyuk govde: /.usb_govde'ye eklenir)
#   PC  -> kart : ~CYD~<id>~<b64 json {"m":yontem,"p":yol,"q":sorgu,"b":b64govde|"f":1}>\n
#   kart -> PC  : ~CYDP~<id>~<b64 dilim>\n   (0..n kez, cevap yazildikca)
#   kart -> PC  : ~CYDR~<id>~<b64 kalan>\n   (bitis)
# Govde ve cevap RAM'de biriktirilmez: govde dosyadan okunur (ESP8266'da
# 3 KB'lik kayit bile heap'e sigmiyordu, olculdu), cevap yazildikca
# base64'e cevrilip porta akar (11 KB docs.md 'allocating 4201 bytes').
# Marker'la baslamayan satirlar kartin normal cikisidir (log).
#
# Dosya sisteminde durur (dondurulmus degil): main.py varsa import eder,
# yoksa sessizce gecer. Heap maliyeti ~2 KB (+ ESP32'de 6 KB thread yigini).
import sys
import select
import binascii
import json
import gc
import os

try:
    import _thread
except ImportError:
    _thread = None

BASLIK = b'~CYD~'
PARCA = b'~CYDB~'
GOVDE_DOSYA = '/.usb_govde'
STACK = 6 * 1024


class _SahteBaglanti:
    """write(): cevabi aninda base64'leyip porta akitir. Her dilim KENDI
    satiri (~CYDP~id~...), son satir ~CYDR~id~ (bitis). Istek islenirken
    sistemin print'leri (jobs 'baslatildi' vb.) araya girse de ayri satir
    kalir, cerceveyi bozmaz (olculdu 22 Eyl 2026: tek satirlik cevapta
    run/stop 504 aliyordu). Dilimli: 3.4 KB'yi tek seferde base64'lemek
    ESP8266'da 'allocating 4482 bytes' veriyordu. read(): govde dosyasindan
    ya da kucuk govdeden okur - sade sunucunun akitmali _kaydet'i boyle
    cagiriyor."""

    # 3'un kati: base64 hizasi korunur. 96: 9 KB bos, parcali heap'te 384'luk
    # dilim + decode + '%' birlestirme 3 x ~540 B istiyordu -> 'allocating
    # 544 bytes' (23 Eyl 2026, i2c_tara sonrasi). Simdi satir basina tek
    # ~130 B'lik ayirma: b2a_base64 ciktisi (sonu zaten '\n') porta aynen.
    DILIM = 96

    def __init__(self, kimlik, govde=b'', dosya=None):
        self._g = govde
        self._i = 0
        self._f = open(dosya, 'rb') if dosya else None
        self._art = b''             # base64 hizasi icin arta kalan 1-2 bayt
        self._k = kimlik.encode() + b'~'

    def _satir(self, isaret, veri):
        # tek write: ESP32'de kopru ayri thread, arada baska print girmesin
        sys.stdout.buffer.write(isaret + self._k +
                                (binascii.b2a_base64(veri) if veri else b'\n'))

    def write(self, b):
        m = memoryview(b)
        n = len(m)
        if self._art:
            k = 3 - len(self._art)
            self._art += bytes(m[:k])
            m = m[k:]
            if len(self._art) < 3:
                return n
            self._satir(b'~CYDP~', self._art)
            self._art = b''
        kes = len(m) - len(m) % 3
        for i in range(0, kes, self.DILIM):
            self._satir(b'~CYDP~', m[i:min(i + self.DILIM, kes)])
        self._art = bytes(m[kes:])
        return n

    def bitir(self):
        self._satir(b'~CYDR~', self._art)
        self._art = b''
        if self._f:
            self._f.close()
            self._f = None

    def read(self, n=-1):
        if self._f:
            return self._f.read(n if n and n > 0 else 4096)
        if n is None or n < 0:
            n = len(self._g) - self._i
        p = self._g[self._i:self._i + n]
        self._i += len(p)
        return p

    def settimeout(self, t):
        pass

    def close(self):
        pass


def _parca(satir):
    """~CYDB~id~b64 : govde parcasini dosyaya ekle (RAM'e almadan)."""
    kimlik = b'0'
    try:
        _, _, kimlik, b64 = satir.split(b'~', 3)
        veri = binascii.a2b_base64(b64)
        with open(GOVDE_DOSYA, 'ab') as f:
            f.write(veri)
        # Onay: PC bir sonraki parcayi bunu gorunce yollar. Onaysiz akista
        # ESP8266'nin seri RX tamponu tasip parca bozuluyordu (olculdu:
        # 'incorrect padding').
        sys.stdout.write('~CYDA~%s~%d\n' % (kimlik.decode(), len(veri)))
    except Exception as e:
        sys.stdout.write('~CYDA~%s~HATA %s\n' % (kimlik.decode(), e))


def _isle(srv, satir):
    kimlik = '0'
    conn = None
    gc.collect()            # proje/log artigi: kucuk bloklar bosa ciksin
    try:
        parca = satir.split(b'~')            # ['', 'CYD', id, b64]
        kimlik = parca[2].decode()
        istek = json.loads(binascii.a2b_base64(parca[3]))
        dosyada = istek.get('f')
        govde = b'' if dosyada else (
            binascii.a2b_base64(istek['b']) if istek.get('b') else b'')
        uzunluk = os.stat(GOVDE_DOSYA)[6] if dosyada else len(govde)
        import server
        # Tam sunucu _parse_qs, sade (ESP8266) sunucu _qs adini kullaniyor
        qs = getattr(server, '_parse_qs', None) or getattr(server, '_qs')
        sorgu = qs(istek.get('q', ''))
        conn = _SahteBaglanti(kimlik, govde, GOVDE_DOSYA if dosyada else None)
        if istek['p'] == '/api/save' and hasattr(srv, '_kaydet'):
            srv._kaydet(conn, sorgu, uzunluk)     # sade sunucu: conn.read ile akitir
        else:
            if dosyada:                           # tam sunucu govdeyi ister
                govde = conn.read(uzunluk)
            srv._route(conn, istek['m'], istek['p'], sorgu, govde)
    except Exception as e:
        if conn is None:
            conn = _SahteBaglanti(kimlik)
        conn.write(('HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/plain\r\n'
                    'Connection: close\r\n\r\nusb kopru hatasi: %s' % e).encode())
    conn.bitir()
    try:
        os.remove(GOVDE_DOSYA)
    except OSError:
        pass
    gc.collect()


def _satir_geldi(srv, satir):
    if satir.startswith(PARCA):
        _parca(bytes(satir))
    elif satir.startswith(BASLIK):
        _isle(srv, bytes(satir))


def _dongu(srv):
    p = select.poll()
    p.register(sys.stdin, select.POLLIN)
    oku = sys.stdin.buffer.read
    satir = bytearray()
    while True:
        if not p.poll(100):
            continue
        c = oku(1)
        if not c:
            continue
        if c == b'\n':
            _satir_geldi(srv, satir)
            satir = bytearray()
        elif len(satir) < 4096:
            satir.extend(c)


_poll = None
_satir = bytearray()


def tik(srv):
    """Thread'siz kart (ESP8266): sunucu dongusunun her turunda cagrilir,
    bloke etmez. stdin'de biriken baytlari alir, tam satir olunca isler."""
    global _poll, _satir
    if _poll is None:
        _poll = select.poll()
        _poll.register(sys.stdin, select.POLLIN)
    oku = sys.stdin.buffer.read
    n = 0
    while _poll.poll(0) and n < 1024:
        c = oku(1)
        n += 1
        if not c:
            break
        if c == b'\n':
            _satir_geldi(srv, _satir)
            _satir = bytearray()
        elif len(_satir) < 4096:
            _satir.extend(c)


def baslat(srv):
    """Thread'li kartta ayri is parcacigi (True). Thread'siz kartta False
    doner; main.py o zaman tik()'i sunucu pompasina ekler."""
    try:
        os.remove(GOVDE_DOSYA)       # yarim kalmis govde
    except OSError:
        pass
    if _thread is None:
        return False
    _thread.stack_size(STACK)
    _thread.start_new_thread(_dongu, (srv,))
    return True
