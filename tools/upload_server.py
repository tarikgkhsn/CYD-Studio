"""Tiny receiver for what the board uploads - a stand-in for your server.

    python tools/upload_server.py [port] [klasor]

Accepts  POST /yukle?ad=<dosya>  with the raw bytes as the body and writes
them into the folder. Prints your LAN IP so you can paste it into the
project's SUNUCU setting.
"""
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
OUTDIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gelen')

os.makedirs(OUTDIR, exist_ok=True)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()


def safe_name(name):
    name = (name or 'dosya.bin').replace('\\', '/').rsplit('/', 1)[-1]
    return ''.join(c for c in name if c.isalnum() or c in '._-') or 'dosya.bin'


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        name = safe_name(parse_qs(parsed.query).get('ad', ['dosya.bin'])[0])
        length = int(self.headers.get('Content-Length') or 0)

        dest = os.path.join(OUTDIR, name)
        written = 0
        with open(dest, 'wb') as f:
            while written < length:
                chunk = self.rfile.read(min(4096, length - written))
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)

        print('  alindi: %-24s %8d bayt -> %s' % (name, written, dest))
        body = b'OK %d\n' % written
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = b'yukleme sunucusu calisiyor. POST /yukle?ad=dosya\n'
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass          # our own prints are enough


ip = lan_ip()
print('yukleme sunucusu hazir')
print('  adres  : http://%s:%d/yukle' % (ip, PORT))
print('  klasor : %s' % OUTDIR)
print()
print('Projede su satiri ayarla:  SUNUCU = %r   PORT = %d' % (ip, PORT))
print('Durdurmak icin Ctrl+C.\n')

HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
