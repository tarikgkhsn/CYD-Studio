"""Regression test: does the panel stay up while a project runs, and does Stop work?

Uploads a small cooperative project (loops with cyd.sleep), starts it over
the API, then hammers /api/status and /api/list WHILE it runs. On the ESP8266
this exercises "beraber mod" (project inline, server pumped from
cyd.sleep); on the ESP32 it exercises the thread path. Then it stops the
project and checks the persistent log for the full lifecycle.

Pass criteria:
  * every status poll during the run answers        (panel alive)
  * status reports the project as running
  * /api/list answers mid-run                        (bigger request)
  * after /api/stop the project is gone within ~4 s
  * log contains '>>> baslatildi' and '<<< durduruldu'

    python tools/test_beraber.py                    # NodeMCU 192.168.0.215
    python tools/test_beraber.py --ip 192.168.0.217 # CYD
"""
import json
import sys
import time
import urllib.request

IP = '192.168.0.215'
if '--ip' in sys.argv:
    IP = sys.argv[sys.argv.index('--ip') + 1]
B = 'http://' + IP
AD = 'test_beraber.py'
POLL = 6            # kac kez yoklayalim
ARA = 2             # saniye

PROJE = ("import cyd, gc\n"
         "for i in range(60):\n"
         "    if cyd.should_stop():\n"
         "        break\n"
         "    gc.collect()\n"
         "    print('tur', i, 'RAM', gc.mem_free())\n"
         "    cyd.sleep(1)\n"
         "print('dongu bitti')\n")


def api(yol, data=None, t=15):
    s = urllib.request.urlopen(B + yol, data=data, timeout=t).read().decode('utf-8', 'replace')
    try:
        return json.loads(s)
    except ValueError:
        return s


def q(ad):
    return urllib.request.quote(ad)


sonuc = []


def kontrol(ad, ok, detay=''):
    sonuc.append(ok)
    print('  [%s] %-38s %s' % ('x' if ok else ' ', ad, detay))


print('hedef: %s' % B)
st = api('/api/status')
print('platform=%s inline=%s running=%s RAM=%s' % (
    st.get('platform') or st.get('sys', {}).get('platform'),
    st.get('inline'), st.get('running'),
    st.get('ram_free') or st.get('sys', {}).get('ram_free')))
if st.get('running'):
    sys.exit('once calisan projeleri durdur')

print('\n--- yukle + baslat ---')
r = api('/api/save?name=' + q(AD), PROJE.encode(), 25)
kontrol('yukleme', bool(r.get('ok')), str(r)[:60])
r = api('/api/run?name=' + q(AD), b'', 15)
kontrol('baslatma', bool(r.get('ok')), r.get('msg') or r.get('error') or '')

print('\n--- proje kosarken panel ---')
cevap = 0
kosuyor = 0
for i in range(POLL):
    time.sleep(ARA)
    try:
        s = api('/api/status', t=6)
        cevap += 1
        adlar = [j['name'] for j in s.get('jobs', []) if j.get('running')]
        if AD in adlar:
            kosuyor += 1
        print('    %2ds  cevap  running=%s  RAM=%s' % (
            (i + 1) * ARA, adlar, s.get('ram_free') or s.get('sys', {}).get('ram_free')))
    except Exception as e:
        print('    %2ds  CEVAP YOK (%s)' % ((i + 1) * ARA, type(e).__name__))
kontrol('panel her yoklamaya cevap verdi', cevap == POLL, '%d/%d' % (cevap, POLL))
kontrol('proje calisiyor gorunuyor', kosuyor >= POLL - 1, '%d/%d' % (kosuyor, POLL))
try:
    n = len(api('/api/list', t=12).get('files', []))
    kontrol('/api/list kosarken', True, '%d dosya' % n)
except Exception as e:
    kontrol('/api/list kosarken', False, type(e).__name__)

print('\n--- durdur ---')
r = api('/api/stop?name=' + q(AD), b'', 15)
kontrol('durdurma istegi', bool(r.get('ok')), r.get('error') or '')
durdu = False
for _ in range(8):
    time.sleep(0.5)
    s = api('/api/status', t=6)
    if not [j for j in s.get('jobs', []) if j.get('running') and j['name'] == AD]:
        durdu = True
        break
kontrol('4 sn icinde durdu', durdu)

lg = str(api('/api/log/file?name=' + q(AD), t=20))
kontrol("log: '>>> baslatildi'", '>>> baslatildi' in lg)
kontrol("log: '<<< durduruldu'", '<<< durduruldu' in lg)
kontrol('log: tur satirlari', 'tur 0' in lg and 'tur 1' in lg)

print('\n--- temizlik ---')
api('/api/delete?name=' + q(AD), b'', 15)
try:
    api('/api/log/file/clear?name=' + q(AD), b'', 15)
except Exception:
    pass

basarili = sum(1 for x in sonuc if x)
print('\n%d/%d kontrol gecti -> %s' % (basarili, len(sonuc),
                                       'BASARILI' if basarili == len(sonuc) else 'BASARISIZ'))
sys.exit(0 if basarili == len(sonuc) else 1)
