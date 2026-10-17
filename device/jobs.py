# jobs.py - run several user projects at once.
#
# Three ways to run a project (per file, saved in config.json "modlar"):
#
#   normal  Shared worker: every normal project is an asyncio task on ONE
#           thread. Costs ~2 KB of heap per project and NO internal DRAM,
#           so six or seven small projects fit next to each other. The
#           plain script is wrapped into an async function on the fly
#           (cyd.sleep -> await); if that does not compile the project is
#           started as a thread instead and the log says so. A project that
#           never sleeps blocks the other normal ones (single thread) -
#           that is what the thread mode is for.
#   thread  Own FreeRTOS thread: measured 10-15 KB of internal DRAM each,
#           which caps it at ~4 on the CYD. Pre-emptive via the GIL, so a
#           tight loop only hurts itself.
#   solo    Reboot without the panel, project gets all the RAM (main.py).
#
# Stopping is cooperative first: the project polls cyd.should_stop() (or
# uses cyd.sleep()). If it ignores that, the job is flagged "stuck". When
# it is the only thing running we hard-reset the board automatically,
# because the Stop button must never leave you with no way out. When other
# projects are still running we refuse to take them down behind your back
# and let you decide from the UI instead.
import io
import sys
import time
import gc
import machine
import logstore
from runtime import HAS_THREADS, kilit, yetenekler, _thread, _tid

# ESP8266'da yigin 35 KB: 250 satirlik halka tampon tek basina yigini yer.
# Kalici log zaten dosyada durdugu icin RAM'deki kopya kucuk olabilir.
# Canli log halkasi RAM'de durur ve her satir ayri kucuk bir string: 250
# satir CYD'de olculdu 20,7 KB tutuyor ve heap'i parcaliyordu (43 KB bos
# gorunurken 1,7 KB'lik JSON icin MemoryError). Tarayici saniyede bir
# since=N ile artimli okur, gecmis zaten /logs/<proje>.log'da; 100 yeter.
MAX_LOG = 100 if HAS_THREADS else 40
NORMAL_MAX = yetenekler()['max_jobs']   # normal mod (ayni anda proje) - kart yetenegi
MAX_THREAD = 4 if HAS_THREADS else 0    # thread modundaki proje siniri (DRAM)
GRACE_MS = 3000

# Panel bu kadar sure nabiz vermezse calisan projeler durdurulur.
# Kullanici karta fiziksel erisemeyebilir; panel her kosulda geri gelmeli.
PANEL_ACLIK_MS = 20000

# A project printing in a tight loop must not be able to starve the web
# panel. Beyond this many lines per second the rest are counted, not
# stored, and the count is reported once the second is over.
LOG_RATE = 12

# Thread stacks come out of the ESP32's internal DRAM, most of which the
# Wi-Fi stack has already claimed - so these are deliberately modest.
# Raise JOB_STACK if a project overflows; lower it to fit more projects.
JOB_STACK = 10 * 1024
NORMAL_STACK = 12 * 1024    # tek ortak calisan: asyncio + tum normal projeler
WATCH_STACK = 3 * 1024

MODLAR = ('normal', 'thread', 'solo')

# Normal mod donusumu: duz betikteki bekleme cagrilari await'e cevrilir.
# Sira onemli: 'sleep_ms(' once, yoksa 'cyd.sleep(' onu da yakalar.
_UYKU = (('cyd.sleep_ms(', 'await __uyu_ms('),
         ('cyd.sleep(', 'await __uyu('),
         ('time.sleep_ms(', 'await __uyu_ms('),
         ('time.sleep(', 'await __uyu('),
         ('cyd.should_stop(', 'should_stop('))


def _isim(s):
    """Satir basindaki tanimlayiciyi doner ('' ise yok)."""
    s = s.strip()
    i = 0
    while i < len(s) and (s[i].isalpha() or s[i] == '_' or (i and s[i].isdigit())):
        i += 1
    return s[:i]


def _ust_duzey_adlar(path):
    """Betigin en ust duzeyde tanimladigi adlar. Sarilan async fonksiyonun
    basina `global a, b, c` yazilir ki proje icindeki fonksiyonlar (ve
    `global x` diyenler) eskisi gibi modul globaline erissin.
    Dosyadan satir satir okur: kaynagin tam kopyasi RAM'e girmez."""
    adlar = []

    def ekle(n):
        if n and n not in adlar and n != '_':
            adlar.append(n)

    for l in open(path):
        if not l or l[0] in ' \t#\r\n':
            continue
        s = l.strip()
        if s.startswith('def ') or s.startswith('class '):
            ekle(_isim(s.split(None, 1)[1]))
        elif s.startswith('import '):
            for parca in s[7:].split(','):
                p = parca.strip().split()
                ekle(p[-1] if len(p) == 3 and p[1] == 'as' else p[0].split('.')[0])
        elif s.startswith('from ') and ' import ' in s:
            for parca in s.split(' import ', 1)[1].strip('() ').split(','):
                p = parca.strip().split()
                if p and p[0] != '*':
                    ekle(p[-1] if len(p) == 3 else p[0])
        elif s.startswith('for ') and ' in ' in s:
            for n in s[4:].split(' in ', 1)[0].strip('() ').split(','):
                ekle(_isim(n))
        elif s.startswith('with ') and ' as ' in s:
            ekle(_isim(s.rsplit(' as ', 1)[1]))
        elif s[0].isalpha() or s[0] == '_':
            # atama: '=' var, oncesi ad(lar); '==' ve cagri satirlari degil
            i = s.find('=')
            if i > 0 and s[i + 1:i + 2] != '=' and s[i - 1] not in '!<>':
                sol = s[:i].rstrip('+-*/%|&^')
                if '(' not in sol and '[' not in sol and '.' not in sol:
                    for n in sol.split(','):
                        ekle(_isim(n))
    return adlar


def donustur(path, hedef):
    """Duz projeyi normal mod govdesine cevirip `hedef` dosyasina yazar.
    Donus: 'normal' (yazildi), 'async' (kullanici async yazmis, kaynak
    oldugu gibi calisir, `main` koroutini aranir), 'thread' (donusum uymaz).

    Bellek: ilk surum kaynagi okuyup 5 kez .replace() ile kopyaliyordu -
    12 KB'lik yuk_kontrol.py icin ~60 KB gecici; 54 KB "bos" ama parcali
    heap'te bile MemoryError (olculdu). Simdi satir satir dosyadan dosyaya
    akar; derleme de execfile ile dosyadan - kaynagin tam kopyasi RAM'e
    hic girmez."""
    # On tarama: kullanici async yazmissa dokunma. Bir de: bekleme cagrisi
    # bir def/class GOVDESINDE ise donusum UYMAZ - MicroPython 'await'i duz
    # bir def icinde sessizce kabul edip fonksiyonu generator'a cevirir,
    # govde hic calismaz (uart_tani.py ile goruldu: 3 sn'lik dinleme 0 sn
    # surdu). Boyle projeler thread modunda acilir.
    def_girinti = None
    for l in open(path):
        if 'async def' in l:
            return 'async'
        s = l.strip()
        if not s or s[0] == '#':
            continue
        girinti = len(l) - len(l.lstrip())
        if s.startswith('def ') or s.startswith('class '):
            if def_girinti is None or girinti <= def_girinti:
                def_girinti = girinti
        elif def_girinti is not None and girinti <= def_girinti:
            def_girinti = None
        if def_girinti is not None and girinti > def_girinti:
            for a, b in _UYKU:
                if a in l and a != 'cyd.should_stop(':
                    return 'thread'
    adlar = _ust_duzey_adlar(path)
    with open(hedef, 'w') as out:
        out.write('async def __proje__():\n')
        if adlar:
            out.write('    global ' + ', '.join(adlar) + '\n')
        for l in open(path):
            l = l.rstrip('\r\n')
            if l.strip():
                for a, b in _UYKU:
                    if a in l:
                        l = l.replace(a, b)
                out.write('    ' + l + '\n')
            else:
                out.write('\n')
    return 'normal'


class Job:
    def __init__(self, mgr, name, path, mod='thread'):
        self.mgr = mgr
        self.name = name
        self.path = path
        self.mod = mod
        self.running = False
        self.stop_flag = False
        self.stop_ms = 0           # durdurma istegi ne zaman geldi
        self.stuck = False
        self.error = None
        self.started_ms = time.ticks_ms()
        self.finished_ms = 0
        self.thread = None
        self.task = None           # normal mod: asyncio gorevi
        self.kaynak = None         # normal mod: calistirilacak dosya
        self.iptal = False         # normal mod: calisan dongusu iptal etsin
        self._win = time.ticks_ms()
        self._count = 0
        self._dropped = 0

    # -- the project's own print() lands here
    def log(self, *args, **kwargs):
        now = time.ticks_ms()
        if time.ticks_diff(now, self._win) >= 1000:
            dropped = self._dropped
            self._win = now
            self._count = 0
            self._dropped = 0
            if dropped:
                self.mgr.push(self.name,
                              '... %d satir atlandi (saniyede %d satirdan fazla '
                              'yaziyorsun)' % (dropped, LOG_RATE))
        self._count += 1
        if self._count > LOG_RATE:
            self._dropped += 1
            return
        sep = kwargs.get('sep', ' ')
        self.mgr.push(self.name, sep.join(str(a) for a in args))

    def seconds(self):
        end = self.finished_ms if (not self.running and self.finished_ms) \
            else time.ticks_ms()
        return time.ticks_diff(end, self.started_ms) // 1000

    def info(self):
        return {
            'name': self.name,
            'path': self.path,
            'mod': self.mod,
            'running': self.running,
            'stuck': self.stuck,
            'error': self.error,
            'seconds': self.seconds(),
        }

    def _globals(self):
        return {
            '__name__': '__main__',
            '__file__': self.path,
            'print': self.log,
            'should_stop': lambda: self.stop_flag,
        }

    def _bitis(self, onceki):
        """Her modun ortak temizligi: moduller, rotalar, kalici log."""
        import cyd
        self.running = False
        self.stuck = False
        self.finished_ms = time.ticks_ms()
        self.code = None
        try:
            cyd._unregister_stop()
        except Exception:
            pass
        for m in [m for m in sys.modules if m not in onceki]:
            sys.modules.pop(m, None)
        # Projenin ana sunucuya kaydettigi rotalar onunla birlikte gitsin
        try:
            import runtime
            runtime._rotalari_temizle(self.name)
            runtime._butonlari_temizle(self.name)   # kesmeler projeyle gitsin
        except Exception:
            pass
        # Tampondaki satirlar diske yazilmadan proje bitmesin: solo
        # modda log dosyasi ciktinin TEK kopyasi.
        try:
            logstore.bosalt()
        except Exception:
            pass
        gc.collect()

    def _hata(self, e):
        buf = io.StringIO()
        sys.print_exception(e, buf)
        self.error = buf.getvalue()
        self.mgr.push(self.name, '!!! HATA')
        self.mgr.push(self.name, self.error)

    # -- thread body
    def _run(self):
        import cyd
        self.thread = _tid()
        cyd._register_stop(lambda: self.stop_flag, self.name)
        # Projenin import ettigi moduller sys.modules'te KALIYORDU: olculdu,
        # bme280 import eden proje bitince 6 KB geri gelmiyor (ESP8266'da
        # 24 -> 18 KB). Ustelik moduldeki bir duzeltme yeniden calistirinca
        # gorunmuyordu - onbellekteki eski surum kosuyordu. Baslarken listeyi
        # alip bitince yeni gelenleri siliyoruz; sonraki calistirma taze
        # import eder.
        onceki = set(sys.modules)
        try:
            with open(self.path) as f:
                source = f.read()
            g = self._globals()
            # compile() kaynak boyunun birkac kati BITISIK blok ister. Olculdu
            # (CYD): baska bir proje 20 KB tutarken 12 KB'lik yuk_kontrol.py
            # 41 KB bos heap'e ragmen 'allocating 6144 bytes' ile dustu -
            # parcalanma. Once toplayip derliyor, kaynagi hemen birakiyoruz.
            gc.collect()
            try:
                code = compile(source, self.name, 'exec')
            except (NameError, AttributeError):
                code = source
            del source
            gc.collect()
            exec(code, g)
            self.mgr.push(self.name,
                          '<<< durduruldu' if self.stop_flag else '<<< bitti')
        except Exception as e:
            self._hata(e)
        finally:
            self._bitis(onceki)

    # -- normal mod: asyncio gorevi (ortak calisan is parcaciginda)
    async def _uyu(self, sn):
        """cyd.sleep karsiligi: durdurulunca False, bitince True."""
        import asyncio
        end = time.ticks_add(time.ticks_ms(), int(sn * 1000))
        while True:
            if self.stop_flag:
                return False
            kalan = time.ticks_diff(end, time.ticks_ms())
            if kalan <= 0:
                return True
            await asyncio.sleep_ms(kalan if kalan < 100 else 100)

    async def _run_async(self):
        import asyncio
        import runtime
        task = asyncio.current_task()
        runtime._gorev_kaydet(task, self.name, lambda: self.stop_flag)
        onceki = set(sys.modules)
        try:
            g = self._globals()
            g['__uyu'] = self._uyu
            g['__uyu_ms'] = lambda ms: self._uyu(ms / 1000)
            gc.collect()
            try:
                # execfile dosyadan lexer'la okur: kaynak stringi heap'e girmez
                execfile(self.kaynak, g)
            except SyntaxError as e:
                # Donusum bu betige uymadi (ornegin cyd.sleep bir def icinde).
                # Ayni proje thread modunda yeniden aciliyor; kullanici
                # degisiklik hissetmez, log neden oldugunu soyler.
                self.mgr.push(self.name, '... normal moda cevrilemedi (%s) - '
                                         'thread modunda aciliyor' % e)
                self.running = False
                self._kaynagi_sil()
                runtime._gorev_sil(task)
                self.mgr._thread_ac(self.name, self.path)
                return
            self._kaynagi_sil()
            proje = g.get('__proje__') or g.get('main')
            if proje is None:
                self.mgr.push(self.name, '(async def main() yok - sadece '
                                         'modul govdesi calisti)')
            else:
                await proje()
            self.mgr.push(self.name,
                          '<<< durduruldu' if self.stop_flag else '<<< bitti')
        except asyncio.CancelledError:
            self.mgr.push(self.name, '<<< durduruldu (durdurmayi yoksaydi, '
                                     'gorev iptal edildi)')
        except Exception as e:
            self._hata(e)
        finally:
            self._kaynagi_sil()
            runtime._gorev_sil(task)
            # Biten Task nesnesi koroutini, koroutin de projenin TUM global
            # sozlugunu (fonksiyonlar, HTML stringleri...) tutuyor. Job
            # mgr.jobs'ta gecmis olarak kaldigi icin her farkli proje ~4 KB
            # birakiyordu: ESP8266'da 3 projeden sonra heap 19 -> 5 KB,
            # panel 500 (olculdu, 10 Eyl gece). Referansi birakiyoruz.
            self.task = None
            self._bitis(onceki)

    def _kaynagi_sil(self):
        """Donusturulmus gecici kaynak dosyasini kaldir (varsa)."""
        k = self.kaynak
        if k and k != self.path:
            try:
                import os
                os.remove(k)
            except OSError:
                pass
        self.kaynak = None


class Manager:
    def __init__(self):
        self.jobs = {}
        self._log = []
        self._seq = 0
        self._lock = kilit()
        self.panel = None          # Server kendini buraya kaydeder
        self._bekci = False
        # Thread'siz kartta start() projeyi hemen calistirmaz; buraya koyar.
        # Sunucu dongusu istek olmadigi bir anda alip satir ici calistirir.
        self.bekleyen = None
        # Normal mod: ortak calisan is parcacigi ve ona verilecek projeler
        self._normal = False
        self.normal_bekleyen = []
        self.normal_kalp = 0

    # ------------------------------------------------------- panel bekcisi
    # MicroPython'da thread'ler GIL yuzunden CPU'yu gercekten paylasmiyor:
    # is parcaciklari sirayla calisiyor. CPU'yu birakmayan bir proje web
    # panelini ac birakabiliyor - kullanici acisindan panel "kilitleniyor".
    # Cozum: panelin nabzini izleyip, durursa projeleri durdurmak. Panel
    # her kosulda geri gelsin, kullanici karta fiziksel erisemeyebilir.
    def _bekci_calis(self):
        self._bekci = True
        try:
            while True:
                time.sleep(2)
                calisan = self.running_jobs()
                if not calisan:
                    break                      # is kalmadi, bekciye gerek yok
                p = self.panel
                if p is None:
                    continue
                gecen = time.ticks_diff(time.ticks_ms(), p.kalp)
                if gecen > PANEL_ACLIK_MS:
                    self.system('!!! panel %d saniyedir cevap veremiyor - '
                                'projeler durduruluyor' % (gecen // 1000))
                    for j in calisan:
                        self.system('    durduruluyor: %s' % j.name)
                        j.stop_flag = True
                        j.iptal = True
                    time.sleep(4)
                    if self.running_jobs():
                        self.system('!!! proje durmadi - cihaz yeniden '
                                    'baslatiliyor (panel kurtarilamadi)')
                        self._resetten_once()
                        machine.reset()
                    break
        finally:
            self._bekci = False

    def _resetten_once(self):
        """machine.reset() oncesi kalici logu diske indir. logstore satirlari
        tamponluyor; bosaltilmazsa 'yanit vermiyor - resetleniyor' gibi tam
        da o an en onemli satir kaybolur (CYD'de olculdu, test_kesici)."""
        try:
            logstore.bosalt()
        except Exception:
            pass
        time.sleep_ms(400)

    def _bekci_baslat(self):
        if self._bekci or not HAS_THREADS or self.panel is None:
            return
        try:
            _thread.stack_size(WATCH_STACK)
            _thread.start_new_thread(self._bekci_calis, ())
        except Exception:
            pass

    # ------------------------------------------------- normal mod calisani
    # Tek is parcacigi, icinde asyncio dongusu; her normal proje bir gorev.
    # Bos kalinca (30 sn proje yok) kendini kapatir ki 12 KB DRAM geri gelsin;
    # ilk normal proje yeniden acar.
    def _normal_dongu(self):
        import asyncio
        import runtime
        runtime._normal_aktif = True
        bos_sayac = 0

        async def ana():
            nonlocal bos_sayac
            while True:
                aktif = self.normal_tik()
                bos_sayac = 0 if (aktif or self.normal_bekleyen) else bos_sayac + 1
                if bos_sayac > 600:            # 600 x 50 ms = 30 sn bos
                    return
                await asyncio.sleep_ms(50)

        try:
            asyncio.run(ana())
        except Exception as e:
            self.system('!!! normal mod calisani dustu: %s' % e)
        finally:
            runtime._normal_aktif = False
            self._normal = False
            try:
                asyncio.new_event_loop()       # eski dongu nesnesi birakilsin
            except Exception:
                pass
            gc.collect()

    def normal_tik(self):
        """Asyncio dongusunun bir adimi: bekleyen normal projeleri gorev
        yapar, iptal istenenleri iptal eder. Kosan normal proje varsa True.
        ESP32'de _normal_dongu, ESP8266'da sunucunun asyncio dongusu cagirir
        (orada thread yok; dongu ana is parcaciginda, sunucu turu da icinde)."""
        import asyncio
        self.normal_kalp = time.ticks_ms()
        while self.normal_bekleyen:
            job = self.normal_bekleyen.pop(0)
            job.task = asyncio.create_task(job._run_async())
        aktif = False
        for j in self.jobs.values():
            if j.mod == 'normal' and j.running:
                aktif = True
                if j.iptal and j.task:
                    j.iptal = False
                    j.task.cancel()
        return aktif

    def _normal_baslat(self):
        if not HAS_THREADS:
            return True                # dongu sunucunun icinde zaten kosuyor
        if self._normal:
            return True
        gc.collect()
        try:
            _thread.stack_size(NORMAL_STACK)
            _thread.start_new_thread(self._normal_dongu, ())
            self._normal = True
            self.normal_kalp = time.ticks_ms()
            return True
        except Exception as e:
            self.system('!!! normal mod calisani baslatilamadi: %s' % e)
            return False

    def _normal_hazirla(self, job):
        """Sunucu is parcaciginda: kaynagi sarip gecici dosyaya akit.
        Derleme calisanda execfile ile dosyadan olur. Basarisizsa False."""
        hedef = '/.n_' + job.name
        try:
            gc.collect()
            sonuc = donustur(job.path, hedef)
            if sonuc == 'thread':
                self.push(job.name, '... bekleme cagrisi bir def icinde: normal '
                                    'moda cevrilemez, thread modunda aciliyor')
                return False
            job.kaynak = hedef if sonuc == 'normal' else job.path
            return True
        except Exception as e:
            self.push(job.name, '... normal mod hazirlanamadi (%s) - thread '
                                'modunda aciliyor' % e)
            job.kaynak = None
            return False

    # ---------------------------------------------------------- logging
    def push(self, source, msg):
        for line in str(msg).split('\n'):
            with self._lock:
                self._seq += 1
                self._log.append((self._seq, source, line))
                if len(self._log) > MAX_LOG:
                    del self._log[:len(self._log) - MAX_LOG]
            # Kalici kopya: RAM'deki log reset'te ucuyor, solo modda ise
            # panel hic acilmadigi icin kimse gormeden kayboluyordu.
            try:
                logstore.ekle(source, line)
            except Exception:
                pass
        try:
            print('[%s] %s' % (source, msg))
        except Exception:
            pass

    def system(self, msg):
        self.push('sistem', msg)

    def log_since(self, seq, source=None):
        with self._lock:
            rows = [r for r in self._log if r[0] > seq]
            top = self._seq
        if source:
            rows = [r for r in rows if r[1] == source]
        return rows, top

    def clear_log(self):
        with self._lock:
            self._log = []

    # ---------------------------------------------------------- control
    def running_jobs(self):
        return [j for j in self.jobs.values() if j.running]

    def running_mod(self, mod):
        return [j for j in self.jobs.values() if j.running and j.mod == mod]

    @staticmethod
    def mod_bul(name, mod=None):
        """Dosyaya kayitli mod (config.json 'modlar'), yoksa varsayilan."""
        if mod in MODLAR:
            return mod
        try:
            import settings
            m = settings.get('modlar', {}).get(name)
            if m in MODLAR:
                return m
            v = settings.get('varsayilan_mod')
            if v in MODLAR:
                return v
        except Exception:
            pass
        return 'normal'

    def start(self, name, path, mod=None):
        mod = self.mod_bul(name, mod)
        # ESP8266 gibi thread'i olmayan kartlarda proje sunucuyla AYNI is
        # parcaciginda kosar: burada sadece "bekleyen" olarak isaretlenir,
        # sunucu dongusu bir sonraki bos turda bekleyeni_calistir() ile alir.
        # Istek isleyicisinin icinden dogrudan calistiramayiz - once cevap
        # gitmeli, ve pompa bir isteğin icinden yeniden girmemeli.
        old = self.jobs.get(name)
        if old and old.running:
            return False, '%s zaten calisiyor' % name

        if not HAS_THREADS:
            # Normal = asyncio gorevi, sunucunun dongusunde; birden cok olur.
            # Donusum uymayan proje (bekleme bir def icinde) eski satir ici
            # yoldan tek basina kosar - o sirada baska proje calisamaz.
            if mod != 'solo' and len(self.running_mod('normal')) < NORMAL_MAX:
                job = Job(self, name, path, 'normal')
                if self._normal_hazirla(job):
                    self.jobs[name] = job
                    job.running = True
                    self.push(name, '>>> baslatildi (normal)')
                    self.normal_bekleyen.append(job)
                    return True, 'ok'
            if self.running_jobs():
                return False, ('bu proje satir ici kosmali (bekleme bir def '
                               'icinde) ve baska projeler calisiyor - once '
                               'onlari durdur ya da Solo sec')
            if self.bekleyen:
                return False, 'zaten bir proje baslatiliyor'
            self.bekleyen = (name, path)
            return True, 'BERABER'

        if mod == 'normal':
            if len(self.running_mod('normal')) >= NORMAL_MAX:
                return False, 'normal modda en fazla %d proje' % NORMAL_MAX
            job = Job(self, name, path, 'normal')
            if not self._normal_hazirla(job) or not self._normal_baslat():
                return self._thread_ac(name, path)     # asagiya dus
            self.jobs[name] = job
            job.running = True
            self.push(name, '>>> baslatildi (normal)')
            self.normal_bekleyen.append(job)
            self._bekci_baslat()
            return True, 'ok'
        return self._thread_ac(name, path)

    def _thread_ac(self, name, path):
        if len(self.running_mod('thread')) >= MAX_THREAD:
            return False, 'thread modunda en fazla %d proje calisabilir' % MAX_THREAD

        # A thread stack is carved out of the heap, so check before we try:
        # a clear "not enough RAM" beats a bare "can't create thread".
        gc.collect()
        free = gc.mem_free()
        if free < JOB_STACK + 14000:
            return False, ('yetersiz RAM: %d KB bos, en az %d KB gerekli. '
                           'once calisan bir projeyi durdur'
                           % (free // 1024, (JOB_STACK + 14000) // 1024))

        job = Job(self, name, path, 'thread')
        self.jobs[name] = job
        job.running = True
        self.push(name, '>>> baslatildi (thread)')
        gc.collect()
        try:
            _thread.stack_size(JOB_STACK)
            _thread.start_new_thread(job._run, ())
        except Exception as e:
            job.running = False
            job.error = 'thread baslatilamadi: %s' % e
            self.push(name, '!!! ' + job.error)
            self.push(name, 'ipucu: dahili RAM doldu. bir projeyi durdur, ya da '
                            'bu projeyi normal modda ac (thread yigini yok).')
            return False, job.error
        self._bekci_baslat()
        return True, 'ok'

    def start_blocking(self, name, path):
        """Projeyi AYNI is parcaciginda calistirir ve bitmesini bekler.

        Solo modun calisma bicimi budur: sunucu zaten acilmadigi icin
        paralellige gerek yok. ESP8266'da tek yol da bu - orada thread yok.
        """
        job = Job(self, name, path, 'solo')
        self.jobs[name] = job
        job.running = True
        self.push(name, '>>> baslatildi (solo)')
        gc.collect()
        try:
            job._run()
        finally:
            try:
                logstore.bosalt()      # tampondaki son satirlar diske
            except Exception:
                pass
        return True, 'ok'

    def bekleyeni_calistir(self):
        """Thread'siz kart: sunucu, istek olmayan bir turda bunu cagirir.

        Bekleyen proje AYNI is parcaciginda calisir ve bitene kadar donmez.
        Bu sirada proje her cyd.sleep() dediginde runtime.pompala() sunucuya
        bir tur verir - panel ayakta kalir, /api/stop bayragi gorulur.
        Calistirdiysa True, bekleyen yoksa False.
        """
        b = self.bekleyen
        if not b:
            return False
        self.bekleyen = None
        name, path = b
        job = Job(self, name, path, 'normal')
        self.jobs[name] = job
        job.running = True
        self.push(name, '>>> baslatildi (panel acik)')
        gc.collect()
        try:
            job._run()
        finally:
            try:
                logstore.bosalt()
            except Exception:
                pass
        return True

    def bekci_tik(self):
        """Thread'siz kart: durdurma istegi GRACE'i asmis ama proje hala
        kosuyorsa karti resetle - CYD'deki _watch'in karsiligi. Zamanlayici
        kesicisi (runtime.pompala) saniyede bir cagirir."""
        now = time.ticks_ms()
        for j in self.running_jobs():
            if not (j.stop_flag and j.stop_ms):
                continue
            gecen = time.ticks_diff(now, j.stop_ms)
            if j.mod == 'normal' and gecen > GRACE_MS and not j.iptal:
                j.iptal = True             # await eden gorevi dongu iptal eder
            if gecen > GRACE_MS + 1500:
                self.push(j.name, '!!! yanit vermiyor - cihaz yeniden baslatiliyor')
                self._resetten_once()
                machine.reset()

    def stop(self, name):
        job = self.jobs.get(name)
        if not job or not job.running:
            return False, '%s calismiyor' % name
        job.stop_flag = True
        job.stop_ms = time.ticks_ms()
        self.push(name, '... durdurma istegi gonderildi')
        try:
            _thread.stack_size(WATCH_STACK)
            _thread.start_new_thread(self._watch, (job,))
        except Exception:
            pass
        return True, 'ok'

    def stop_all(self):
        n = 0
        for job in self.running_jobs():
            self.stop(job.name)
            n += 1
        return n

    def _watch(self, job):
        deadline = time.ticks_add(time.ticks_ms(), GRACE_MS)
        while job.running and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            time.sleep_ms(50)
        if not job.running:
            return
        if job.mod == 'normal':
            # Bayragi yoksaydi ama await ediyorsa gorev iptali onu keser.
            # Calisan is parcacigi hic donmuyorsa (sleep'siz siki dongu)
            # iptal de islenmez - asagida thread gibi ele alinir.
            job.iptal = True
            deadline = time.ticks_add(time.ticks_ms(), 2000)
            while job.running and time.ticks_diff(deadline, time.ticks_ms()) > 0:
                time.sleep_ms(50)
            if not job.running:
                return
        job.stuck = True
        others = [j for j in self.running_jobs() if j is not job]
        if job.mod == 'normal' and \
                time.ticks_diff(time.ticks_ms(), self.normal_kalp) > 2000:
            # Ortak calisan takili: diger normal projeler de zaten donmuyor.
            others = [j for j in others if j.mod != 'normal']
        if others:
            self.push(job.name,
                      '!!! yanit vermiyor. diger projeler calistigi icin '
                      'otomatik reset atilmadi - arayuzden "zorla" secebilirsin')
            return
        self.push(job.name, '!!! yanit vermiyor - cihaz yeniden baslatiliyor')
        self._resetten_once()
        machine.reset()

    def force_reset(self):
        self.system('!!! zorla yeniden baslatiliyor')
        self._resetten_once()
        machine.reset()

    # ----------------------------------------------------------- status
    def status(self):
        return {
            'jobs': [j.info() for j in self.jobs.values()],
            'running': len(self.running_jobs()),
            'max_jobs': NORMAL_MAX,
            'max_thread': MAX_THREAD,
            'normal_calisan': self._normal,
            'seq': self._seq,
        }
