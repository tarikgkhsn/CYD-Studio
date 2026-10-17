# server.py (NodeMCU / ESP8266 sade surumu)
#
# Cekirdekteki tam sunucu ~9 KB yigin yiyor; ESP8266'da toplam 35 KB var ve
# WiFi kalkinca geriye ~1 KB kaliyor - istek isleyemiyor. Bu surum sadece
# gerekli rotalari tutuyor: dosya listele/oku/yaz/sil, calistir, kalici log,
# reset. WiFi ayari, ekran API'si, dokuman, artifact YOK.
#
# Calistir artik paneli KAPATMIYOR. _thread yok ama gerek de yok: proje
# sunucuyla ayni is parcaciginda, satir ici kosar. serve_forever her bos
# turda mgr.bekleyeni_calistir() cagirir; proje cyd.sleep() dedikce
# runtime.pompala() -> tek_tur() ile istekler islenir. Solo (/api/solo)
# her bayti isteyen projeler icin secenek olarak duruyor.
import socket
import select
import json
import gc
import os
import time
import machine

import store
import settings

INDEX = '/index.html'
CHUNK = 512
LOG_PAGE = 25


def _bol(s, sep):
    """str.partition ESP8266'nin minimal derlemesinde YOK."""
    i = s.find(sep)
    if i < 0:
        return s, '', ''
    return s[:i], sep, s[i + len(sep):]


def _unquote(s):
    if '%' not in s and '+' not in s:
        return s
    s = s.replace('+', ' ')
    p = s.split('%')
    out = [p[0]]
    for x in p[1:]:
        try:
            out.append(chr(int(x[:2], 16)) + x[2:])
        except ValueError:
            out.append('%' + x)
    return ''.join(out)


def _qs(q):
    d = {}
    for pair in q.split('&'):
        if pair:
            k, _, v = _bol(pair, '=')
            d[_unquote(k)] = _unquote(v)
    return d


class Server:
    def __init__(self, mgr, port=80):
        self.mgr = mgr
        self.port = port
        self.sock = None
        self._poll = None
        self._hata = 0
        self.acilis = time.ticks_ms()
        mgr.panel = self

    def listen(self):
        a = socket.getaddrinfo('0.0.0.0', self.port)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(a)
        s.listen(2)
        self.sock = s
        # accept() bloke etmesin diye once poll ile "gelen var mi" diye
        # bakiyoruz. errno'ya bakmak porttan porta degisiyor, poll degismiyor.
        self._poll = select.poll()
        self._poll.register(s, select.POLLIN)
        return s

    def tek_tur(self):
        """BLOKE ETMEYEN tek tur: bekleyen baglanti varsa BIR istegi isler.

        Hem serve_forever hem de proje calisirken runtime.pompala() bunu
        cagirir. Istek islendiyse True, yoksa hemen False doner.
        """
        if self.sock is None:
            self.listen()
        try:
            if not self._poll.poll(0):
                return False
            conn, _ = self.sock.accept()
            self._hata = 0
        except OSError as e:
            self._hata += 1
            if self._hata > 25:
                print('dinleyici soket yeniden kuruluyor:', e)
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
                self._hata = 0
            return False
        try:
            conn.settimeout(8)
            self._handle(conn)
        except Exception as e:
            print('istek hatasi:', e)
            try:
                self._send(conn, '500', 'text/plain', 'hata')
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            pass
        gc.collect()
        return True

    def serve_forever(self):
        """Asyncio dongusu ANA is parcaciginda: sunucu turu + normal moddaki
        projeler (her biri bir gorev) yan yana. Thread yok, yigin yok:
        proje basina maliyet sadece heap'teki gorev nesnesi.

        Sunucu turu runtime.pompala() uzerinden gider ki zamanlayici
        kesicisi (_son_pompa) ve bekci (bekci_tik, saniyede bir) ayni yoldan
        beslensin; pompa kayitli degilse dogrudan tek_tur.
        Donusumu uymayan proje eski satir ici yoldan kosar
        (bekleyeni_calistir) - o sirada normal gorevler bekler, bu yuzden
        jobs.start onu yalniz baska proje yokken kabul eder."""
        if self.sock is None:
            self.listen()
        import asyncio
        import runtime
        runtime._normal_aktif = True
        mgr = self.mgr

        async def ana():
            while True:
                if runtime._pompa is not None:
                    runtime.pompala()
                else:
                    self.tek_tur()
                kosan = mgr.normal_tik()
                if not kosan and mgr.bekleyen:
                    mgr.bekleyeni_calistir()
                await asyncio.sleep_ms(20)

        try:
            asyncio.run(ana())
        finally:
            runtime._normal_aktif = False
            try:
                asyncio.new_event_loop()
            except Exception:
                pass

    # ------------------------------------------------------------ gonderim
    def _send(self, conn, durum, tip, govde):
        if isinstance(govde, str):
            govde = govde.encode()
        conn.write(('HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n'
                    'Cache-Control: no-store\r\nConnection: close\r\n\r\n'
                    % (durum, tip, len(govde))).encode())
        if govde:
            conn.write(govde)

    def _json(self, conn, o):
        self._send(conn, '200 OK', 'application/json', json.dumps(o))

    def _ok(self, conn, **kw):
        d = {'ok': True}
        d.update(kw)
        self._json(conn, d)

    def _err(self, conn, msg):
        self._json(conn, {'ok': False, 'error': str(msg)})

    def _dosya(self, conn, yol, tip):
        try:
            n = os.stat(yol)[6]
        except OSError:
            return self._send(conn, '404 Not Found', 'text/plain', 'yok')
        conn.write(('HTTP/1.1 200 OK\r\nContent-Type: %s\r\n'
                    'Content-Length: %d\r\nConnection: close\r\n\r\n'
                    % (tip, n)).encode())
        with open(yol, 'rb') as f:
            while True:
                b = f.read(CHUNK)
                if not b:
                    break
                conn.write(b)

    def _rota_calistir(self, conn, fn, yontem, yol, q, govde):
        """Projenin cyd.rota() isleyicisi: str -> html/text, dict/list -> json,
        bytes -> ham, (durum, tip, govde) / (tip, govde) -> ozel."""
        try:
            r = fn({'yontem': yontem, 'yol': yol, 'sorgu': q, 'govde': govde})
        except Exception as e:
            return self._send(conn, '500 Internal Server Error', 'text/plain',
                              'rota hatasi: %s' % e)
        durum, tip = '200 OK', None
        if isinstance(r, tuple):
            if len(r) == 3:
                durum, tip, r = r
            elif len(r) == 2:
                tip, r = r
        if isinstance(r, (dict, list)):
            return self._send(conn, durum, tip or 'application/json', json.dumps(r))
        if r is None:
            r = ''
        if tip is None:
            tip = ('text/html; charset=utf-8'
                   if isinstance(r, str) and r.lstrip().startswith('<')
                   else 'text/plain; charset=utf-8')
        return self._send(conn, durum, tip, r)

    # -------------------------------------------------------------- istek
    def _handle(self, conn):
        satir = conn.readline()
        if not satir:
            return
        try:
            yontem, hedef, _ = satir.decode().split(' ', 2)
        except ValueError:
            return
        uzunluk = 0
        while True:
            h = conn.readline()
            if not h or h in (b'\r\n', b'\n'):
                break
            try:
                k, _, v = _bol(h.decode(), ':')
                if k.strip().lower() == 'content-length':
                    uzunluk = int(v.strip())
            except Exception:
                pass
        yol, _, q = _bol(hedef, '?')
        qs = _qs(q)

        # Dosya yazmayi belleğe almadan, geldigi gibi diske akitiyoruz.
        # 5 KB bos yiginda 2.4 KB'lik bir dosyayi RAM'de biriktirmek
        # (ustelik her parcada yeniden kopyalayarak) yetmiyordu.
        if yol == '/api/save' and yontem == 'POST':
            return self._kaydet(conn, qs, uzunluk)

        govde = b''
        kalan = uzunluk
        parcalar = []
        while kalan > 0:
            p = conn.read(min(CHUNK, kalan))
            if not p:
                break
            parcalar.append(p)
            kalan -= len(p)
        if parcalar:
            govde = b''.join(parcalar)
        self._route(conn, yontem, yol, qs, govde)

    def _kaydet(self, conn, q, uzunluk):
        try:
            ad = store.safe(q.get('name', ''))
            hedef = store.path(ad)
        except Exception as e:
            return self._err(conn, e)
        yazilan = 0
        try:
            with open(hedef, 'wb') as f:
                kalan = uzunluk
                while kalan > 0:
                    p = conn.read(min(CHUNK, kalan))
                    if not p:
                        break
                    f.write(p)
                    yazilan += len(p)
                    kalan -= len(p)
                    gc.collect()
        except Exception as e:
            return self._err(conn, e)
        return self._ok(conn, name=ad, size=yazilan)

    # ------------------------------------------------------------- rotalar
    def _route(self, conn, yontem, yol, q, govde):
        m = self.mgr

        if yol == '/' or yol == '/index.html':
            return self._dosya(conn, INDEX, 'text/html; charset=utf-8')

        if yol == '/favicon.ico':
            return self._send(conn, '204 No Content', 'image/x-icon', b'')

        if yol == '/api/status':
            gc.collect()
            import network
            import runtime
            w = network.WLAN(network.STA_IF)
            try:
                ip = w.ifconfig()[0]
                rssi = w.status('rssi')
            except Exception:
                ip, rssi = '0.0.0.0', None
            st = os.statvfs('/')
            return self._json(conn, {
                'ok': True, 'platform': 'esp8266', 'solo_only': False,
                'inline': True,
                'jobs': [j.info() for j in m.jobs.values()],
                'running': len(m.running_jobs()),
                'ram_free': gc.mem_free(), 'ram_total': gc.mem_free() + gc.mem_alloc(),
                'flash_free': st[0] * st[3], 'flash_total': st[0] * st[2],
                'ip': ip, 'rssi': rssi, 'freq': machine.freq(),
                'uptime': time.ticks_diff(time.ticks_ms(), self.acilis) // 1000,
                'autostart': settings.autostart_list(),
                'rotalar': runtime.rotalar()})

        if yol == '/api/caps':
            import runtime
            return self._json(conn, {'ok': True, 'caps': runtime.ozellikler()})

        if yol == '/api/list':
            # Listeyi tek JSON stringi olarak kurmak 17 dosyada bile 7 KB'lik
            # yigini asiyordu. Bunun yerine AKITIYORUZ: her an sadece tek bir
            # dosyalik kucuk parca bellekte duruyor. Content-Length vermeyip
            # baglantiyi kapatarak bitiriyoruz (HTTP/1.0 usulu).
            gc.collect()
            conn.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                       b'Cache-Control: no-store\r\nConnection: close\r\n\r\n')
            kok = store.base()
            conn.write(b'{"ok":true,"base":"')
            conn.write(kok.encode())
            conn.write(b'","modlar":')
            conn.write(json.dumps(settings.get('modlar', {}) or {}).encode())
            conn.write(b',"files":[')
            ilk = True
            try:
                adlar = os.listdir(kok)
            except OSError:
                adlar = []
            for ad in adlar:
                try:
                    d = os.stat(kok + '/' + ad)
                except OSError:
                    continue
                if d[0] & 0x4000:          # klasorleri atla
                    continue
                if not ilk:
                    conn.write(b',')
                ilk = False
                conn.write(('{"name":"%s","size":%d,"py":%s}'
                            % (ad, d[6],
                               'true' if ad.endswith('.py') else 'false')).encode())
                gc.collect()
            conn.write(b']}')
            return

        if yol == '/api/file':
            try:
                return self._send(conn, '200 OK', 'text/plain; charset=utf-8',
                                  store.read(q.get('name', '')))
            except Exception as e:
                return self._err(conn, e)

        if yol == '/api/delete' and yontem == 'POST':
            try:
                store.delete(store.safe(q.get('name', '')))
                return self._ok(conn)
            except Exception as e:
                return self._err(conn, e)

        # Calistir: proje "bekleyen" olur, cevap gider, sunucu dongusu bir
        # sonraki bos turda satir ici calistirir. Panel ACIK kalir.
        if yol == '/api/run' and yontem == 'POST':
            try:
                ad = store.safe(q.get('name', ''))
                p = store.path(ad)
                os.stat(p)
            except Exception as e:
                return self._err(conn, 'dosya yok: %s' % e)
            ok, msg = m.start(ad, p, q.get('mod') or None)
            if ok:
                return self._ok(conn, name=ad,
                                msg='baslatiliyor - panel acik kalir')
            return self._err(conn, msg)

        # Calisma modu: dosya basina kalici (normal | solo; thread bu kartta yok)
        if yol == '/api/mod' and yontem == 'POST':
            try:
                ad = store.safe(q.get('name', ''))
            except Exception as e:
                return self._err(conn, e)
            mod = q.get('mod', '')
            if mod not in ('normal', 'solo'):
                return self._err(conn, 'mod normal|solo olmali')
            modlar = dict(settings.get('modlar', {}) or {})
            modlar[ad] = mod
            settings.save(modlar=modlar)
            return self._ok(conn, modlar=modlar)

        if yol == '/api/stopall' and yontem == 'POST':
            return self._ok(conn, stopped=m.stop_all())

        if yol == '/api/stop' and yontem == 'POST':
            try:
                ok, msg = m.stop(store.safe(q.get('name', '')))
            except Exception as e:
                return self._err(conn, e)
            return self._json(conn, {'ok': ok, 'error': None if ok else msg})

        # Solo: panel KAPANIR, proje tum RAM'i alir. Her bayti isteyen ya da
        # cyd.sleep() cagirmayan projeler icin. RESET paneli geri getirir.
        if yol == '/api/solo' and yontem == 'POST':
            try:
                ad = store.safe(q.get('name', ''))
                os.stat(store.path(ad))
            except Exception as e:
                return self._err(conn, 'dosya yok: %s' % e)
            settings.save(solo_once=True, solo_wifi=q.get('wifi', '1') == '1',
                          solo_proje=ad)
            self._ok(conn, name=ad, solo=True,
                     msg='solo modda baslatiliyor - cikti kalici loga yazilir, '
                         'paneli geri getirmek icin RESET at')
            time.sleep_ms(300)
            machine.reset()
            return

        if yol == '/api/log/file':
            # Logu belleğe alip gondermek 5 KB'lik yiginda patliyordu
            # (3 KB okuma + decode). Dosyayi dogrudan sokete akitiyoruz;
            # her an sadece CHUNK kadar bayt bellekte.
            try:
                import logstore
                ad = q.get('name', '')
                logstore.bosalt(ad)          # tampondakiler de diske insin
                p = logstore.yol(ad)
                try:
                    boyut = os.stat(p)[6]
                except OSError:
                    return self._send(conn, '200 OK',
                                      'text/plain; charset=utf-8', '')
                conn.write(b'HTTP/1.1 200 OK\r\n'
                           b'Content-Type: text/plain; charset=utf-8\r\n'
                           b'Cache-Control: no-store\r\nConnection: close\r\n\r\n')
                with open(p, 'rb') as f:
                    if boyut > 4096:         # sondan oku, bastakiler eski
                        f.seek(boyut - 4096)
                        f.readline()         # yarim satiri at
                    while True:
                        b = f.read(CHUNK)
                        if not b:
                            break
                        conn.write(b)
                        gc.collect()
                return
            except Exception as e:
                print('log okuma hatasi:', e)
                return

        # ---- canli log: RAM'deki halka tampon (MAX_LOG satir). Tek JSON
        # stringi kurmak yerine satir satir akitiyoruz; buyuk sunucuyla ayni
        # sema: {"ok":true,"seq":N,"lines":[[seq,kaynak,satir],...]}
        if yol == '/api/log':
            try:
                since = int(q.get('since', '0'))
            except ValueError:
                since = 0
            rows, top = m.log_since(since)
            rows = rows[-LOG_PAGE:]
            gc.collect()
            conn.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                       b'Cache-Control: no-store\r\nConnection: close\r\n\r\n')
            conn.write(('{"ok":true,"seq":%d,"lines":[' % top).encode())
            ilk = True
            for r in rows:
                if not ilk:
                    conn.write(b',')
                ilk = False
                conn.write(json.dumps([r[0], r[1], r[2]]).encode())
            conn.write(b']}')
            return

        if yol == '/api/log/clear' and yontem == 'POST':
            m.clear_log()
            return self._ok(conn)

        # ---- dokuman: /docs.md FS'te durur, akitilir (RAM'e alinmaz)
        if yol == '/api/docs':
            d = '/docs.md'
            if q.get('dil') == 'en':
                try:
                    os.stat('/docs_en.md')
                    d = '/docs_en.md'
                except OSError:
                    pass
            return self._dosya(conn, d, 'text/markdown; charset=utf-8')

        # ---- ag ayarlari: stokta 2,5 KB RAM ile kesilmisti, frozen sonrasi var
        if yol == '/api/wifi' and yontem == 'GET':
            import netmgr
            cfg = settings.load()
            return self._json(conn, {
                'ok': True, 'ssid': cfg.get('ssid', ''),
                'has_password': bool(cfg.get('password')),
                'ip': cfg.get('ip', ''), 'netmask': cfg.get('netmask', ''),
                'gateway': cfg.get('gateway', ''), 'dns': cfg.get('dns', ''),
                'hostname': cfg.get('hostname', ''),
                'ap_ssid': cfg.get('ap_ssid', ''),
                'net': netmgr.status()})

        if yol == '/api/wifi' and yontem == 'POST':
            try:
                d = json.loads(govde) if govde else {}
                kw = {'ssid': d.get('ssid', ''), 'ip': d.get('ip', ''),
                      'netmask': d.get('netmask') or '255.255.255.0',
                      'gateway': d.get('gateway', ''), 'dns': d.get('dns', '')}
                if d.get('password'):          # bos birakilirsa eski sifre kalir
                    kw['password'] = d['password']
                if d.get('hostname'):
                    kw['hostname'] = d['hostname']
                settings.save(**kw)
                self._ok(conn, msg='kaydedildi, yeniden baslatiliyor')
                time.sleep_ms(400)
                machine.reset()
            except Exception as e:
                self._err(conn, e)
            return

        if yol == '/api/scan':
            import netmgr
            gc.collect()
            return self._json(conn, {'ok': True, 'networks': netmgr.scan()})

        if yol == '/api/log/file/clear' and yontem == 'POST':
            try:
                import logstore
                return self._ok(conn, silindi=logstore.sil(q.get('name', '')))
            except Exception as e:
                return self._err(conn, e)

        if yol == '/api/autostart' and yontem == 'POST':
            try:
                ad = store.safe(q.get('name', ''))
            except Exception as e:
                return self._err(conn, e)
            liste = settings.autostart_list()
            if q.get('on', '1') == '1':
                if ad not in liste:
                    liste.append(ad)
            elif ad in liste:
                liste.remove(ad)
            settings.save(autostart=liste)
            return self._ok(conn, autostart=liste)

        if yol == '/api/reset' and yontem == 'POST':
            self._ok(conn, msg='yeniden baslatiliyor')
            time.sleep_ms(250)
            machine.reset()
            return

        if yol == '/api/rotalar':
            import runtime
            return self._json(conn, {'ok': True, 'rotalar': runtime.rotalar()})

        # ---- proje rotalari: /api disi her sey once cyd.rota kayitlarina
        # bakar. Ikinci sunucu yok, ayni port, ayni dongu.
        import runtime
        h = runtime.rota_bul(yol)
        if h:
            return self._rota_calistir(conn, h, yontem, yol, q, govde)

        self._send(conn, '404 Not Found', 'text/plain', 'yok: ' + yol)


autostart_list = settings.autostart_list
