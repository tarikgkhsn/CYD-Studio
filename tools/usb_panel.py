"""CYD Studio panel over the USB cable - no Wi-Fi needed.

    python tools/usb_panel.py [COM3] [--port 8080] [--board cyd]

Opens http://localhost:8080/ on the PC. The page itself is served from the
local source tree (device/index.html or boards/<board>/index.html) so it
loads instantly; every /api/... call is framed as one base64 line, written
to the serial port, answered by usbkopru.py on the board (same server
routing as Wi-Fi, so every feature works), and unframed here.

Lines from the board that are not bridge frames are the board's normal
console output - they are echoed to this terminal, so you also get a live
serial log for free. Ctrl+C stops the bridge and frees the COM port
(deploy tools need it).

Measured (ESP8266, 115200 baud, 22 Sep 2026): /api/status 0.6-1 s,
save/run/log/stop 0.2-0.9 s, 11 KB docs 1.5 s. Bodies over 384 B go to the
board in 192-byte chunks, each acknowledged (~CYDA~) before the next - the
board's serial RX buffer overflowed without that. Only one client at a
time on the serial link (requests are serialised with a lock), which is
what a single browser tab needs. Use 127.0.0.1, not localhost (IPv6 first
on Windows costs ~2 s per request).
"""
import base64
import http.server
import json
import os
import socketserver
import sys
import threading
import time
import urllib.parse

import serial

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


PORT = int(arg('--port', '8080'))
BOARD = arg('--board', 'cyd')
COM = next((a for a in sys.argv[1:] if a.upper().startswith('COM') or a.startswith('/dev/')), 'COM3')

INDEX = os.path.join(ROOT, 'boards', BOARD, 'index.html')
if not os.path.exists(INDEX):
    INDEX = os.path.join(ROOT, 'device', 'index.html')

ser = serial.Serial(COM, 115200, timeout=0.05)
kilit = threading.Lock()
sayac = [0]
bekleyen = {}          # id -> cevap bytes (okuyucu thread doldurur)
olay = {}              # id -> threading.Event
onay = {}              # id -> son parca onayi (~CYDA~)
onay_olay = {}
dilimler = {}          # id -> [cevap dilimleri] (~CYDP~), ~CYDR~ birlestirir
GOVDE_ESIK = 64        # ustu parcali: istek satiri ~2x base64, 256 B'nin altinda kalsin
PARCA = 128            # ham bayt; satir ~185 B


def okuyucu():
    """Seri porttan satir okur: bizim cerceve ise kuyruga, degilse ekrana."""
    satir = bytearray()
    while True:
        try:
            b = ser.read(4096)
        except Exception as e:
            print('!!! seri port koptu:', e)
            os._exit(1)
        if not b:
            continue
        for c in b:
            if c == 10:
                s = bytes(satir)
                satir = bytearray()
                if s.startswith(b'~CYDA~'):
                    try:
                        _, _, kimlik, sonuc = s.split(b'~', 3)
                        onay[kimlik.decode()] = sonuc
                        ev = onay_olay.get(kimlik.decode())
                        if ev:
                            ev.set()
                    except Exception:
                        pass
                elif s.startswith(b'~CYDP~'):
                    # cevap dilimi (yeni kart): bitis ~CYDR~ ile gelir
                    try:
                        _, _, kimlik, veri = s.split(b'~', 3)
                        dilimler.setdefault(kimlik.decode(), []).append(base64.b64decode(veri))
                    except Exception as e:
                        print('!!! bozuk dilim:', e)
                elif s.startswith(b'~CYDR~'):
                    try:
                        _, _, kimlik, veri = s.split(b'~', 3)
                        kimlik = kimlik.decode()
                        bekleyen[kimlik] = b''.join(dilimler.pop(kimlik, [])) + base64.b64decode(veri)
                        ev = olay.get(kimlik)
                        if ev:
                            ev.set()
                    except Exception as e:
                        print('!!! bozuk cerceve:', e)
                else:
                    try:
                        print('[kart] ' + s.decode('utf-8', 'replace').rstrip())
                    except Exception:
                        pass
            elif c != 13:
                satir.append(c)


def karta(method, path, query, body, zaman=25):
    sayac[0] += 1
    kimlik = str(sayac[0])
    # Kucuk govde istegin icinde gider; buyugu PARCA baytlik onayli
    # parcalarla once karttaki gecici dosyaya akar (ESP8266'da 3 KB'lik kayit
    # heap'e sigmiyordu). Her satir < 256 bayt kalmali: ESP8266'nin stdin
    # halka tamponu 256 B, kart pompada degilken dolup satir sonu kayboluyordu
    # (olculdu 22 Eyl 2026: 192 B parca = 265 B satir, 2. parca onaysiz).
    buyuk = len(body) > GOVDE_ESIK
    istek = {'m': method, 'p': path, 'q': query}
    if buyuk:
        istek['f'] = 1
    else:
        istek['b'] = base64.b64encode(body).decode() if body else ''
    cerceve = b'~CYD~' + kimlik.encode() + b'~' + base64.b64encode(json.dumps(istek).encode()) + b'\n'
    ev = threading.Event()
    olay[kimlik] = ev
    with kilit:
        if buyuk:
            for i in range(0, len(body), PARCA):
                ev2 = threading.Event()
                onay_olay[kimlik] = ev2
                ser.write(b'~CYDB~' + kimlik.encode() + b'~' + base64.b64encode(body[i:i + PARCA]) + b'\n')
                ser.flush()
                # parca basina onay: kartin seri RX tamponu ~256 bayt, onaysiz
                # akista tasip parca bozuluyordu (olculdu: 'incorrect padding')
                if not ev2.wait(5) or b'HATA' in onay.get(kimlik, b''):
                    onay_olay.pop(kimlik, None)
                    return (b'HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\n'
                            b'parca onaylanmadi: ' + onay.get(kimlik, b'zaman asimi'))
            onay_olay.pop(kimlik, None)
        ser.write(cerceve)
        ser.flush()
        ok = ev.wait(zaman + len(body) // 1000)
    olay.pop(kimlik, None)
    cevap = bekleyen.pop(kimlik, None)
    if not ok or cevap is None:
        return b'HTTP/1.1 504 Gateway Timeout\r\nContent-Type: text/plain\r\n\r\nkart cevap vermedi (%ds)' % zaman
    return cevap


class Istek(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def _yerel(self):
        with open(INDEX, 'rb') as f:
            d = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def _ilet(self, method):
        u = urllib.parse.urlsplit(self.path)
        if u.path in ('/', '/index.html'):
            return self._yerel()
        if u.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        n = int(self.headers.get('Content-Length', 0) or 0)
        body = self.rfile.read(n) if n else b''
        ham = karta(method, u.path, u.query, body)
        # Kartin HTTP cevabini oldugu gibi aktar: durum, basliklar, govde
        bas, _, govde = ham.partition(b'\r\n\r\n')
        satirlar = bas.split(b'\r\n')
        try:
            durum = int(satirlar[0].split()[1])
        except Exception:
            durum = 200
        self.send_response(durum)
        for h in satirlar[1:]:
            k, _, v = h.partition(b':')
            k = k.strip().decode('latin-1')
            if k.lower() in ('content-type', 'cache-control'):
                self.send_header(k, v.strip().decode('latin-1'))
        self.send_header('Content-Length', str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self):
        self._ilet('GET')

    def do_POST(self):
        self._ilet('POST')


class Sunucu(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


threading.Thread(target=okuyucu, daemon=True).start()
print('USB kopru: %s  ->  http://127.0.0.1:%d/   (panel: %s)' % (COM, PORT, os.path.relpath(INDEX, ROOT)))
print('(127.0.0.1 yaz, localhost degil: Windows once IPv6 dener, her istek ~2 sn gecikir)')
print('kart cikisi asagida akar; Ctrl+C kapatir')
try:
    Sunucu(('127.0.0.1', PORT), Istek).serve_forever()
except KeyboardInterrupt:
    pass
finally:
    ser.close()
