# server.py - the little HTTP server that fronts the whole thing.
# Deliberately single-threaded and blocking: user projects get their own
# threads, so the server only has to stay simple and predictable.
import socket
import json
import gc
import os
import time
import machine

import store
import settings

# netmgr ve sysinfo bilerek EN USTTE import EDILMIYOR: sadece birkac rotada
# gerekiyorlar ve ESP8266'da 35 KB yiginda her modul sayiliyor. Ihtiyac
# aninda import ediliyorlar (MicroPython zaten onbellekliyor).

INDEX = '/index.html'
CHUNK = 1024
# Most lines one /api/log response may carry. A fresh tab asks with
# since=0; serialising the whole ring buffer at once is what used to
# exhaust internal DRAM and wedge the accept() loop.
LOG_PAGE = 80
LOG_PAGE = 80          # most log lines sent in one response


def _bol(s, sep):
    """str.partition yerine - ESP8266'nin minimal derlemesinde o metot YOK.
    (once, ayrac, sonra) dondurur."""
    i = s.find(sep)
    if i < 0:
        return s, '', ''
    return s[:i], sep, s[i + len(sep):]


def _unquote(s):
    if '%' not in s and '+' not in s:
        return s
    s = s.replace('+', ' ')
    parts = s.split('%')
    out = [parts[0]]
    for p in parts[1:]:
        try:
            out.append(chr(int(p[:2], 16)) + p[2:])
        except ValueError:
            out.append('%' + p)
    return ''.join(out)


def _parse_qs(qs):
    d = {}
    if not qs:
        return d
    for pair in qs.split('&'):
        if not pair:
            continue
        k, _, v = _bol(pair, '=')
        d[_unquote(k)] = _unquote(v)
    return d


autostart_list = settings.autostart_list


class Server:
    def __init__(self, mgr, port=80):
        self.mgr = mgr
        self.port = port
        self.sock = None
        # Panel nabzi: serve_forever her turda gunceller. jobs.Manager buna
        # bakip "panel ac kaldi mi" diye karar veriyor.
        self.kalp = time.ticks_ms()
        mgr.panel = self

    # ---------------------------------------------------------- transport
    def listen(self):
        addr = socket.getaddrinfo('0.0.0.0', self.port)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(addr)
        s.listen(4)
        self.sock = s
        return s

    def serve_forever(self):
        if self.sock is None:
            self.listen()
        # Dinleyici soket BLOKE ETMEYEN: zaman asimli accept() MicroPython'da
        # beklerken GIL'i birakmiyor, yani projeleri ac birakiyor (olculdu).
        # Bunun yerine yoklayip sleep_ms ile is parcacigini birakiyoruz;
        # her turda da "yasiyorum" nabzini guncelliyoruz.
        try:
            self.sock.settimeout(0)
        except Exception:
            pass
        fails = 0
        while True:
            self.kalp = time.ticks_ms()      # panel nabzi
            if self.sock is None:
                try:
                    self.listen()
                    fails = 0
                    self.mgr.push('sunucu', '... dinleyici soket kuruldu')
                except Exception as e:
                    self.mgr.push('sunucu', '!!! soket kurulamadi: %s' % e)
                    time.sleep(2)
                    continue
            try:
                conn, addr = self.sock.accept()
                fails = 0
            except OSError as e:
                # EAGAIN / ETIMEDOUT = "su an istek yok", hata degil.
                kod = e.args[0] if e.args else 0
                if kod in (11, 110, 116, -11):      # EAGAIN, ETIMEDOUT
                    time.sleep_ms(20)               # is parcacigini birak
                    continue
                # accept() fails when lwIP is out of internal DRAM. Spinning
                # here with no delay burns the CPU and never recovers, which
                # looked exactly like a dead board while the project kept
                # running happily.
                fails += 1
                if fails <= 2 or fails % 100 == 0:
                    self.mgr.push('sunucu',
                                  '!!! accept hatasi (%d. kez): %s' % (fails, e))
                gc.collect()
                time.sleep_ms(100)
                if fails >= 25:
                    self.mgr.push('sunucu',
                                  '... soket yeniden kuruluyor (bellek toparlaniyor)')
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
                    gc.collect()
                    time.sleep(1)
                continue
            try:
                # 5 sn: tamamen takilan bir istemci paneli en fazla bu kadar
                # tutar; bekci esigi (20 sn) asilmaz. Yavas ama ilerleyen
                # istemci icin nabiz _send_file icinde her parcada guncellenir.
                conn.settimeout(5)
                self._handle(conn)
            except Exception as e:
                # Swallowing this silently made a MemoryError look like the
                # board had died. Always say what actually went wrong.
                try:
                    import io
                    import sys as _s
                    buf = io.StringIO()
                    _s.print_exception(e, buf)
                    self.mgr.push('sunucu', '!!! istek hatasi: %s: %s'
                                  % (type(e).__name__, e))
                    print(buf.getvalue())
                except Exception:
                    print('sunucu hatasi:', e)
                try:
                    self._send(conn, '500 Internal Server Error',
                               'text/plain', 'hata: %s' % e)
                except Exception:
                    pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
                gc.collect()

    # ----------------------------------------------------------- plumbing
    def _send(self, conn, status, ctype, body, extra=''):
        if isinstance(body, str):
            body = body.encode('utf-8')
        head = ('HTTP/1.1 %s\r\n'
                'Content-Type: %s\r\n'
                'Content-Length: %d\r\n'
                'Cache-Control: no-store\r\n'
                'Access-Control-Allow-Origin: *\r\n'
                'Connection: close\r\n%s\r\n' % (status, ctype, len(body), extra))
        conn.write(head.encode())
        if body:
            conn.write(body)

    def _json(self, conn, obj, status='200 OK'):
        self._send(conn, status, 'application/json', json.dumps(obj))

    def _ok(self, conn, **kw):
        d = {'ok': True}
        d.update(kw)
        self._json(conn, d)

    def _err(self, conn, msg, status='400 Bad Request'):
        self._json(conn, {'ok': False, 'error': str(msg)}, status)

    def _solo_baslat(self, conn, name, keep_wifi=True):
        """Solo modda yeniden baslat: panel acilmaz, proje tek basina kosar.

        Tek seferliktir - main.py bayragi ilk is olarak siler, yani RESET
        her zaman paneli geri getirir. Proje ciktisi kalici log dosyasina
        yazildigi icin panel geri gelince okunabilir.
        """
        try:
            name = store.safe(name)
            os.stat(store.path(name))
        except Exception as e:
            return self._err(conn, 'dosya yok: %s' % e)
        settings.save(solo_once=True, solo_wifi=bool(keep_wifi),
                      solo_proje=name)
        self._ok(conn, name=name, wifi=bool(keep_wifi), solo=True,
                 msg='solo modda yeniden baslatiliyor - cikti kalici loga '
                     'yazilacak, paneli geri getirmek icin RESET at')
        time.sleep_ms(400)
        machine.reset()

    def _send_file(self, conn, path, ctype):
        try:
            size = os.stat(path)[6]
        except OSError:
            self._send(conn, '404 Not Found', 'text/plain', 'yok')
            return
        head = ('HTTP/1.1 200 OK\r\nContent-Type: %s\r\n'
                'Content-Length: %d\r\nCache-Control: no-store\r\n'
                'Connection: close\r\n\r\n' % (ctype, size))
        conn.write(head.encode())
        with open(path, 'rb') as f:
            while True:
                buf = f.read(CHUNK)
                if not buf:
                    break
                conn.write(buf)
                # Olculdu (CYD): 512 B / 0,5 sn okuyan istemciye 51 KB'lik
                # index.html gonderirken nabiz 15-21 sn durdu, bekci projeleri
                # durdurdu. Ilerleyen gonderim canli sayilir.
                self.kalp = time.ticks_ms()

    def _rota_calistir(self, conn, fn, yontem, yol, q, govde):
        """Projenin cyd.rota() ile kaydettigi isleyiciyi calistirip cevabini
        gonderir. Donus: str -> html/text, dict/list -> json, bytes -> ham,
        (durum, tip, govde) ya da (tip, govde) -> ozel. Isleyici bu (sunucu)
        is parcaciginda kosar - projeninkinde degil; kisa tutulmali."""
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

    def _handle(self, conn):
        line = conn.readline()
        if not line:
            return
        try:
            method, target, _ = line.decode().split(' ', 2)
        except ValueError:
            return
        headers = {}
        while True:
            h = conn.readline()
            if not h or h in (b'\r\n', b'\n'):
                break
            try:
                k, _, v = _bol(h.decode(), ':')
                headers[k.strip().lower()] = v.strip()
            except Exception:
                pass
        length = int(headers.get('content-length', 0) or 0)
        body = b''
        while len(body) < length:
            part = conn.read(min(CHUNK, length - len(body)))
            if not part:
                break
            body += part
        path, _, qs = _bol(target, '?')
        self._route(conn, method, path, _parse_qs(qs), body)

    # ------------------------------------------------------------- routes
    def _route(self, conn, method, path, q, body):
        m = self.mgr

        if path == '/' or path == '/index.html':
            return self._send_file(conn, INDEX, 'text/html; charset=utf-8')

        if path == '/favicon.ico':
            return self._send(conn, '204 No Content', 'image/x-icon', b'')

        # The handover doc lives on the board so it is never out of reach.
        if path == '/api/docs':
            # ?dil=en -> /docs_en.md (varsa); panelin TR/EN secimi buraya gelir
            yol = '/docs.md'
            if q.get('dil') == 'en':
                try:
                    os.stat('/docs_en.md')
                    yol = '/docs_en.md'
                except OSError:
                    pass
            return self._send_file(conn, yol, 'text/markdown; charset=utf-8')

        # ---- dashboard ------------------------------------------------
        if path == '/api/status':
            import sysinfo
            import netmgr
            st = m.status()
            st['sys'] = sysinfo.collect(sd_mounted=store.on_sd())
            st['net'] = netmgr.status()
            st['storage'] = {'base': store.base(), 'on_sd': store.on_sd()}
            st['autostart'] = autostart_list()
            import runtime
            st['rotalar'] = runtime.rotalar()
            return self._json(conn, st)

        if path == '/api/list':
            return self._json(conn, {'ok': True, 'base': store.base(),
                                     'on_sd': store.on_sd(),
                                     'files': store.listing(),
                                     'modlar': settings.get('modlar', {}) or {}})

        if path == '/api/log':
            # Never serialise the whole ring buffer. A freshly opened tab
            # asks with since=0, and turning 400 buffered lines into one
            # JSON string is what used to take the panel down.
            since = int(q.get('since', 0) or 0)
            rows, top = m.log_since(since, q.get('source') or None)
            skipped = 0
            if len(rows) > LOG_PAGE:
                skipped = len(rows) - LOG_PAGE
                rows = rows[-LOG_PAGE:]        # jump to the newest
            return self._json(conn, {'ok': True, 'seq': top, 'lines': rows,
                                     'skipped': skipped})

        if path == '/api/log/clear' and method == 'POST':
            m.clear_log()
            return self._ok(conn)

        # ---- files ----------------------------------------------------
        if path == '/api/file':
            try:
                return self._send(conn, '200 OK', 'text/plain; charset=utf-8',
                                  store.read(q.get('name', '')))
            except Exception as e:
                return self._err(conn, e, '404 Not Found')

        if path == '/api/save' and method == 'POST':
            try:
                name = store.safe(q.get('name', ''))
                store.write(name, body)
                return self._ok(conn, name=name, size=len(body))
            except Exception as e:
                return self._err(conn, e)

        if path == '/api/delete' and method == 'POST':
            try:
                name = store.safe(q.get('name', ''))
                job = m.jobs.get(name)
                if job and job.running:
                    return self._err(conn, 'once durdur')
                store.delete(name)
                auto = autostart_list()
                if name in auto:
                    auto.remove(name)
                    settings.save(autostart=auto)
                return self._ok(conn)
            except Exception as e:
                return self._err(conn, e)

        if path == '/api/rename' and method == 'POST':
            try:
                old = store.safe(q.get('name', ''))
                new = store.safe(q.get('to', ''))
                job = m.jobs.get(old)
                if job and job.running:
                    return self._err(conn, 'once durdur')
                store.rename(old, new)
                auto = autostart_list()
                if old in auto:
                    auto[auto.index(old)] = new
                    settings.save(autostart=auto)
                return self._ok(conn, name=new)
            except Exception as e:
                return self._err(conn, e)

        # ---- run control ----------------------------------------------
        if path == '/api/run' and method == 'POST':
            name = q.get('name', '')
            try:
                p = store.path(name)
                os.stat(p)
            except Exception as e:
                return self._err(conn, 'dosya yok: %s' % e)
            ok, msg = m.start(store.safe(name), p, q.get('mod') or None)
            return self._json(conn, {'ok': ok, 'error': None if ok else msg})

        # ---- calisma modu: normal | thread | solo, dosya basina kalici
        if path == '/api/mod' and method == 'POST':
            try:
                name = store.safe(q.get('name', ''))
            except Exception as e:
                return self._err(conn, e)
            mod = q.get('mod', '')
            if mod not in ('normal', 'thread', 'solo'):
                return self._err(conn, 'mod normal|thread|solo olmali')
            modlar = dict(settings.get('modlar', {}) or {})
            modlar[name] = mod
            settings.save(modlar=modlar)
            return self._ok(conn, modlar=modlar)

        # ---- kalici log (reset'ten sonra da durur)
        if path == '/api/log/file':
            try:
                import logstore
                return self._send(conn, '200 OK', 'text/plain; charset=utf-8',
                                  logstore.oku(q.get('name', '')))
            except Exception as e:
                return self._err(conn, e)

        if path == '/api/log/files':
            try:
                import logstore
                return self._json(conn, {'ok': True, 'logs': logstore.liste()})
            except Exception as e:
                return self._err(conn, e)

        if path == '/api/log/file/clear' and method == 'POST':
            try:
                import logstore
                return self._ok(conn, silindi=logstore.sil(q.get('name', '')))
            except Exception as e:
                return self._err(conn, e)

        if path == '/api/stop' and method == 'POST':
            ok, msg = m.stop(q.get('name', ''))
            return self._json(conn, {'ok': ok, 'error': None if ok else msg})

        if path == '/api/stopall' and method == 'POST':
            return self._ok(conn, stopped=m.stop_all())

        if path == '/api/force' and method == 'POST':
            self._ok(conn, msg='yeniden baslatiliyor')
            time.sleep_ms(250)
            m.force_reset()
            return

        if path == '/api/caps':
            import runtime
            return self._json(conn, {'ok': True, 'caps': runtime.ozellikler()})

        if path == '/api/solo' and method == 'POST':
            # Reboot without the web server so the named project gets the
            # DRAM the listening socket would otherwise hold. One-shot:
            # main.py clears the flag, so a reset restores the panel.
            return self._solo_baslat(conn, q.get('name', ''),
                                     q.get('wifi', '1') == '1')

        if path == '/api/reset' and method == 'POST':
            self._ok(conn, msg='yeniden baslatiliyor')
            time.sleep_ms(250)
            machine.reset()
            return

        if path == '/api/autostart' and method == 'POST':
            try:
                name = store.safe(q.get('name', ''))
            except Exception as e:
                return self._err(conn, e)
            auto = autostart_list()
            on = q.get('on', '1') == '1'
            if on and name not in auto:
                auto.append(name)
            elif not on and name in auto:
                auto.remove(name)
            settings.save(autostart=auto)
            return self._ok(conn, autostart=auto)

        # ---- display -------------------------------------------------
        if path == '/api/display' and method == 'POST':
            try:
                import cyd
                rot = int(q.get('rot', settings.get('rotation', 1)))
                bgr = q.get('bgr', '1' if settings.get('bgr', True) else '0') == '1'
                cyd.set_display(rot, bgr)
                if q.get('test', '1') == '1':
                    d = cyd.test_pattern('rot %d  bgr %s' % (rot, 'acik' if bgr else 'kapali'))
                else:
                    d = cyd.display()
                if q.get('save', '0') == '1':
                    settings.save(rotation=rot, bgr=bgr)
                return self._ok(conn, rotation=rot, bgr=bgr,
                                width=d.width, height=d.height,
                                saved=q.get('save', '0') == '1')
            except Exception as e:
                return self._err(conn, e)

        if path == '/api/backlight' and method == 'POST':
            try:
                import cyd
                on = q.get('on', '1') == '1'
                cyd.display().backlight(on)
                return self._ok(conn, on=on)
            except Exception as e:
                return self._err(conn, e)

        # ---- settings -------------------------------------------------
        if path == '/api/settings' and method == 'POST':
            try:
                data = json.loads(body) if body else {}
                allowed = {}
                for k in ('rotation', 'splash', 'ap_ssid', 'ap_password'):
                    if k in data:
                        allowed[k] = data[k]
                settings.save(**allowed)
                return self._ok(conn, **allowed)
            except Exception as e:
                return self._err(conn, e)

        if path == '/api/wifi' and method == 'GET':
            import netmgr
            cfg = settings.load()
            return self._json(conn, {
                'ok': True, 'ssid': cfg.get('ssid', ''),
                'has_password': bool(cfg.get('password')),
                'ap_ssid': cfg.get('ap_ssid'),
                'ip': cfg.get('ip', ''), 'netmask': cfg.get('netmask', ''),
                'gateway': cfg.get('gateway', ''), 'dns': cfg.get('dns', ''),
                'rotation': cfg.get('rotation', 1),
                'bgr': cfg.get('bgr', True),
                'splash': cfg.get('splash', True),
                'net': netmgr.status()})

        if path == '/api/wifi' and method == 'POST':
            try:
                data = json.loads(body) if body else {}
                settings.save(ssid=data.get('ssid', ''),
                              password=data.get('password', ''),
                              ip=data.get('ip', ''),
                              netmask=data.get('netmask', '255.255.255.0'),
                              gateway=data.get('gateway', ''),
                              dns=data.get('dns', ''))
                self._ok(conn, msg='kaydedildi, yeniden baslatiliyor')
                time.sleep_ms(400)
                machine.reset()
            except Exception as e:
                self._err(conn, e)
            return

        if path == '/api/scan':
            import netmgr
            return self._json(conn, {'ok': True, 'networks': netmgr.scan()})

        # ---- depolama: projeler flash'ta mi SD'de mi ------------------
        if path == '/api/depolama' and method == 'GET':
            return self._json(conn, {'ok': True, 'mod': store.mod(),
                                     'base': store.base(), 'on_sd': store.on_sd(),
                                     'sd_var': store.sd_var(), 'not': store.not_()})

        if path == '/api/depolama' and method == 'POST':
            mod = q.get('mod', '')
            if mod not in ('otomatik', 'flash', 'sd'):
                return self._err(conn, 'mod otomatik|flash|sd olmali')
            if m.running_jobs():
                return self._err(conn, 'once calisan projeleri durdur')
            settings.save(depolama=mod)
            store.init()                      # canli gecis, reset gerekmez
            m.system('depolama: %s -> %s' % (mod, store.not_()))
            return self._json(conn, {'ok': True, 'mod': mod, 'base': store.base(),
                                     'on_sd': store.on_sd(), 'not': store.not_()})

        if path == '/api/tasi' and method == 'POST':
            if m.running_jobs():
                return self._err(conn, 'once calisan projeleri durdur')
            adlar = q.get('names')
            adlar = [a for a in adlar.split(',') if a] if adlar else None
            try:
                tasinan, hatalar = store.tasi(q.get('hedef', ''), adlar)
            except Exception as e:
                return self._err(conn, e)
            m.system('tasindi -> %s: %d dosya%s' % (q.get('hedef'), len(tasinan),
                     (', %d hata' % len(hatalar)) if hatalar else ''))
            return self._json(conn, {'ok': True, 'tasinan': tasinan,
                                     'hatalar': hatalar, 'base': store.base()})

        # ---- ad-hoc code ---------------------------------------------
        if path == '/api/eval' and method == 'POST':
            try:
                g = {'print': lambda *a, **k: m.push(
                    'konsol', ' '.join(str(x) for x in a))}
                exec(body.decode('utf-8'), g)
                return self._ok(conn)
            except Exception as e:
                import io
                import sys as _s
                buf = io.StringIO()
                _s.print_exception(e, buf)
                m.push('konsol', buf.getvalue())
                return self._err(conn, e)

        if path == '/api/rotalar':
            import runtime
            return self._json(conn, {'ok': True, 'rotalar': runtime.rotalar()})

        # ---- proje rotalari ------------------------------------------
        # /api disinda kalan her sey once projelerin kaydettigi rotalara
        # bakar (cyd.rota). Ikinci bir sunucu acmadan proje kendi sayfasini
        # ayni portta sunar - ayri dinleyici soket DRAM'i tuketiyordu.
        import runtime
        h = runtime.rota_bul(path)
        if h:
            return self._rota_calistir(conn, h, method, path, q, body)

        self._send(conn, '404 Not Found', 'text/plain', 'bulunamadi: ' + path)
