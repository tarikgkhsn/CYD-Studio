"""Regression test: a project that never yields, a project that ignores Stop,
and project routes on the main server.

Three scenarios, in order:

  1. TIGHT LOOP  - `while True: x += 1`, no cyd.sleep, no should_stop.
     The panel must keep answering. On the ESP8266 that is the timer
     preemption (runtime.kesici_baslat); on the ESP32 the GIL slices
     threads anyway.
  2. IGNORED STOP - /api/stop on that project. It cannot honour the flag,
     so the watchdog must reset the board: panel goes away, then comes back
     with nothing running, and the saved log carries '!!! yanit vermiyor'.
  3. ROUTES - a project registers /selam (json) and /sayfa (html) with
     cyd.rota. Both must be served on port 80 while it runs, appear in
     /api/rotalar, and return 404 once it is stopped.

    python tools/test_kesici.py                    # NodeMCU 192.168.0.215
    python tools/test_kesici.py --ip 192.168.0.217 # CYD
"""
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

IP = '192.168.0.215'
if '--ip' in sys.argv:
    IP = sys.argv[sys.argv.index('--ip') + 1]
B = 'http://' + IP

SIKI = 'test_siki.py'
ROTA = 'test_rota.py'
sonuc = []


def api(yol, data=None, t=15, kez=4):
    for n in range(kez):
        try:
            s = urllib.request.urlopen(B + yol, data=data, timeout=t).read().decode('utf-8', 'replace')
            try:
                return json.loads(s)
            except ValueError:
                return s
        except urllib.error.HTTPError:
            raise
        except Exception:
            if n == kez - 1:
                raise
            time.sleep(1.5)


def acik():
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect((IP, 80))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def q(ad):
    return urllib.parse.quote(ad)


def kontrol(ad, ok, detay=''):
    sonuc.append(ok)
    print('  [%s] %-40s %s' % ('x' if ok else ' ', ad, detay))


def temizle(ad):
    try:
        api('/api/delete?name=' + q(ad), b'')
    except Exception:
        pass
    try:
        api('/api/log/file/clear?name=' + q(ad), b'')
    except Exception:
        pass


print('hedef: %s' % B)
st = api('/api/status')
if st.get('running'):
    sys.exit('once calisan projeleri durdur')
temizle(SIKI)
temizle(ROTA)

# ------------------------------------------------------------ 1) siki dongu
print('\n--- 1) siki dongu (sleep yok, should_stop yok) ---')
api('/api/save?name=' + q(SIKI), b'import cyd\nx = 0\nwhile True:\n    x += 1\n', 25)
r = api('/api/run?name=' + q(SIKI), b'')
kontrol('baslatma', bool(r.get('ok')), r.get('msg') or r.get('error') or '')
cevap = 0
for i in range(6):
    time.sleep(2)
    try:
        s = api('/api/status', t=6, kez=1)
        cevap += 1
        print('    %2ds  cevap  running=%s' % ((i + 1) * 2, [j['name'] for j in s.get('jobs', []) if j.get('running')]))
    except Exception as e:
        print('    %2ds  CEVAP YOK (%s)' % ((i + 1) * 2, type(e).__name__))
kontrol('panel siki dongude cevap verdi', cevap >= 5, '%d/6' % cevap)

# ------------------------------------------------------ 2) durdurmayi yoksay
print('\n--- 2) /api/stop yoksayilinca bekci resetlemeli ---')
try:
    api('/api/stop?name=' + q(SIKI), b'', 10, kez=1)
except Exception:
    pass
gitti = None
for i in range(20):
    time.sleep(1)
    if not acik():
        gitti = i + 1
        break
kontrol('panel kapandi (reset)', gitti is not None, ('%d sn' % gitti) if gitti else 'kapanmadi')
geldi = None
for i in range(60):
    if acik():
        geldi = i
        break
    time.sleep(1)
kontrol('panel geri geldi', geldi is not None, ('%d sn' % geldi) if geldi is not None else 'gelmedi')
if geldi is None:
    print('\nkart geri gelmedi - RST at'); sys.exit(1)
time.sleep(2)
s = api('/api/status')
kontrol('reset sonrasi calisan yok', not s.get('running'))
kl = str(api('/api/log/file?name=' + q(SIKI), t=20))
kontrol("logda '!!! yanit vermiyor'", 'yanit vermiyor' in kl)
temizle(SIKI)

# ------------------------------------------------------------------ 3) rota
print('\n--- 3) rota: proje kendi sayfasini ana portta sunar ---')
KOD = ("import cyd\n"
       "n = [0]\n"
       "def selam(i):\n"
       "    n[0] += 1\n"
       "    return {'selam': 'dunya', 'n': n[0], 'sorgu': i['sorgu']}\n"
       "def sayfa(i):\n"
       "    return '<h1>rota</h1>'\n"
       "cyd.rota('/selam', selam)\n"
       "cyd.rota('/sayfa', sayfa)\n"
       "while not cyd.should_stop():\n"
       "    cyd.sleep(0.5)\n")
api('/api/save?name=' + q(ROTA), KOD.encode(), 25)
r = api('/api/run?name=' + q(ROTA), b'')
kontrol('baslatma', bool(r.get('ok')))
time.sleep(3)
rl = [x['yol'] for x in api('/api/rotalar').get('rotalar', [])]
kontrol('/api/rotalar listeliyor', '/selam' in rl and '/sayfa' in rl, str(rl))
j = api('/selam?a=1')
kontrol('/selam json + sorgu', isinstance(j, dict) and j.get('selam') == 'dunya' and j.get('sorgu', {}).get('a') == '1', str(j)[:60])
j2 = api('/selam')
kontrol('cagrilar arasi durum (sayac)', isinstance(j2, dict) and j2.get('n') == 2, 'n=%s' % (j2.get('n') if isinstance(j2, dict) else '?'))
h = str(api('/sayfa'))
kontrol('/sayfa html', h.startswith('<h1>'), h[:30])
api('/api/stop?name=' + q(ROTA), b'')
time.sleep(3)
try:
    urllib.request.urlopen(B + '/selam', timeout=10)
    kontrol('durunca 404', False, 'hala cevap veriyor')
except urllib.error.HTTPError as e:
    kontrol('durunca 404', e.code == 404, str(e.code))
except Exception as e:
    kontrol('durunca 404', False, type(e).__name__)
kontrol('rotalar bosaldi', not api('/api/rotalar').get('rotalar'))
temizle(ROTA)

n = sum(1 for x in sonuc if x)
print('\n%d/%d kontrol gecti -> %s' % (n, len(sonuc), 'BASARILI' if n == len(sonuc) else 'BASARISIZ'))
sys.exit(0 if n == len(sonuc) else 1)
