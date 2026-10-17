# runtime.py - projelerin calisma ortami. Karttan BAGIMSIZ.
#
# Durdurma bayraklari, ekran sahipligi, bellek ve ag yardimcilari burada
# durur; her kartin kendi `cyd.py` dosyasi bunlari disari acar. Boylece
# CYD ile OLED kartinda ayni proje kodu calisir.
import time

# ---------------------------------------------------------- kart yetenekleri
# Ayni cekirdek ESP32'de de ESP8266'da da calissin diye, ne oldugunu
# varsaymak yerine OLCUYORUZ. ESP8266'da _thread yoktur: orada projeler
# ayri thread'de kosamaz, sistem kendiliginden solo moda duser.
try:
    import _thread
    HAS_THREADS = True
except ImportError:
    _thread = None
    HAS_THREADS = False


class _SahteKilit:
    """_thread yoksa kilit de yok - tek is parcacigi var, gerek de yok."""

    def acquire(self, *a):
        return True

    def release(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def kilit():
    return _thread.allocate_lock() if HAS_THREADS else _SahteKilit()


def _tid():
    return _thread.get_ident() if HAS_THREADS else 0


# ---------------------------------------------------------------- ozellikler
# Sistem her kartta AYNI sistem; farklar veri olarak burada duruyor.
# Kartin `cyd.py` dosyasi OZELLIKLER sozlugu tanimlayip bunlari ezer.
# Panel de bu haritaya bakip desteklenmeyen dugmeleri gizler.
_VARSAYILAN = {
    'display': False,        # ekran var mi
    'touch': False,          # dokunmatik
    'sd': False,             # SD kart yuvasi
    'rgb_led': False,        # kart uzerinde RGB LED
    'light': False,          # isik sensoru (LDR)
    'speaker': False,        # hoparlor / buzzer
    'ble': False,            # Bluetooth LE (solo modda)
    'tls': False,            # HTTPS (solo modda)
    'wifi_config': True,     # panelden ag ayari
    'docs': True,            # panelde dokuman sekmesi
    'persistent_log': True,  # proje basina kalici log
    'lite_ui': False,        # sade panel kullaniliyor mu
}


def yetenekler():
    """Cekirdek yetenekleri - donanim modulunu import ETMEDEN.
    jobs.py bunu modul yuklenirken cagiriyor, o yuzden hafif olmali."""
    import sys
    return {
        'threads': HAS_THREADS,
        'platform': sys.platform,
        # Ayni anda kac proje (normal mod, olculdu 10 Eyl 2026): CYD'de 7 kostu,
        # 8 tavan; ESP8266'da 24 KB heap ile 3 (19 -> 9 KB). Thread tavani
        # ayri: jobs.MAX_THREAD.
        'max_jobs': 8 if HAS_THREADS else 3,
        # Thread'siz kartta proje sunucuyla AYNI is parcaciginda kosar ve
        # cyd.sleep() icindeki pompa sunucuya tur verir (bkz. pompala).
        # Solo hala bir secenek, artik zorunluluk degil.
        'solo_only': False,
        'inline': not HAS_THREADS,
    }


def ozellikler():
    """Cekirdek yetenekleri + kartin kendi bildirdigi ozellikler."""
    o = dict(_VARSAYILAN)
    o.update(yetenekler())
    try:
        import cyd
        o.update(getattr(cyd, 'OZELLIKLER', {}))
    except Exception:
        pass
    return o

# Ayni anda birden fazla proje calisabildigi icin durdurma bayragi
# thread basina tutulmali, tek bir modul degiskeni olamaz.
_stop_checks = {}
_job_names = {}
_display_owner = None

# "Normal mod" (jobs.py): birden cok proje TEK is parcaciginda asyncio
# gorevi olarak kosar. Thread kimligi hepsinde ayni oldugu icin proje
# adi/durdurma bayragi gorev nesnesine gore tutulur. _normal_aktif False
# iken asyncio hic import edilmez - thread modundaki projeler bedel odemez.
_normal_aktif = False
_gorev_adi = {}          # id(task) -> proje adi
_gorev_bayrak = {}       # id(task) -> durdurma bayragi fonksiyonu


def _gorev():
    if not _normal_aktif:
        return None
    try:
        import asyncio
        return asyncio.current_task()
    except Exception:
        return None


def _gorev_kaydet(task, name, fn):
    _gorev_adi[id(task)] = name
    _gorev_bayrak[id(task)] = fn


def _gorev_sil(task):
    global _display_owner
    name = _gorev_adi.pop(id(task), None)
    _gorev_bayrak.pop(id(task), None)
    if name and _display_owner == name:
        _display_owner = None
_warned = set()


def _register_stop(fn, name=None):
    tid = _tid()
    _stop_checks[tid] = fn
    if name:
        _job_names[tid] = name


def _unregister_stop():
    global _display_owner
    tid = _tid()
    _stop_checks.pop(tid, None)
    name = _job_names.pop(tid, None)
    if name and _display_owner == name:
        _display_owner = None          # biten is ekrani elinde tutmasin


def job_name():
    """Bu thread'de calisan projenin adi ('' ise web sunucusu)."""
    t = _gorev()
    if t is not None and id(t) in _gorev_adi:
        return _gorev_adi[id(t)]
    return _job_names.get(_tid(), '')


def should_stop():
    """Bu proje icin Durdur'a basildi mi? Donguleerde bunu yokla."""
    t = _gorev()
    if t is not None and id(t) in _gorev_bayrak:
        return bool(_gorev_bayrak[id(t)]())
    fn = _stop_checks.get(_tid())
    return bool(fn and fn())


# ---------------------------------------------------------- isbirlikci pompa
# Thread'i olmayan kartta (ESP8266) proje ile web sunucusu AYNI is
# parcaciginda kosar. Proje cyd.sleep() dedigi her turda pompa sunucuya bir
# tur verir: istek varsa islenir, panel ayakta kalir. Eski PC'lerdeki tek
# cekirdekli cok gorevlilik gibi - gercekten ayni anda degil, ama insan
# fark etmeyecek kadar sik sirayla.
#
# Bedeli: cyd.sleep() cagirmayan bir proje sunucuya hic sira vermez ve
# panel duser. Thread'li kartta (ESP32) pompa kayitli degildir, sleep
# eskisi gibi calisir.
_pompa = None
_pompada = False
_bekci = None
_son_pompa = 0
_son_bekci = 0
_timer = None


def pompa_kaydet(fn):
    """Sunucunun bloke etmeyen tek tur fonksiyonunu kaydeder."""
    global _pompa
    _pompa = fn


def pompala():
    """Sunucuya bir tur ver. Yeniden girise kapali: bir istek islenirken
    icerden tekrar cagrilirsa hicbir sey yapmaz."""
    global _pompada, _son_pompa, _son_bekci
    if _pompa is None or _pompada:
        return
    _pompada = True
    try:
        _pompa()
    except Exception as e:
        print('pompa hatasi:', e)
    finally:
        _pompada = False
        _son_pompa = time.ticks_ms()
    # Durdurulamayan projeyi yakalayan bekci - saniyede bir yeter.
    if _bekci and time.ticks_diff(_son_pompa, _son_bekci) > 1000:
        _son_bekci = _son_pompa
        try:
            _bekci()
        except Exception as e:
            print('bekci hatasi:', e)


def kesici_baslat(pompa_fn, bekci_fn=None, aralik_ms=100, esik_ms=400):
    """Thread'siz kartta ZAMANLAYICI KESICISI - acemi kodun sigortasi.

    Proje cyd.sleep() cagirmadan sıkı dongude donerse pompa hic calismaz,
    panel duser. Bu zamanlayici her aralik_ms'de bakar: son pompadan beri
    esik_ms gectiyse micropython.schedule ile pompayi ARAYA SOKAR - iki
    bytecode arasinda, projenin haberi olmadan. Eski tek cekirdekli PC'lerin
    zaman dilimlemesi gibi: gercekten ayni anda degil, ama insan fark etmez.

    Sinir: bloke eden bir C cagrisinin (uart.write, buyuk SPI transferi)
    icine giremez; o milisaniyelik bir aralik. Saf Python dongusunu keser.
    bekci_fn: durdurma istegini yoksayan projeyi resetleyen kontrol
    (jobs.Manager.bekci_tik) - CYD'deki bekci thread'inin karsiligi.
    """
    global _bekci, _timer, _son_pompa
    pompa_kaydet(pompa_fn)
    _bekci = bekci_fn
    _son_pompa = time.ticks_ms()
    import machine
    import micropython

    def _zorla(_):
        pompala()

    def _tik(t):
        if time.ticks_diff(time.ticks_ms(), _son_pompa) > esik_ms:
            try:
                micropython.schedule(_zorla, 0)
            except RuntimeError:
                pass                       # kuyruk dolu - bir sonraki tikte
    _timer = machine.Timer(-1)
    _timer.init(period=aralik_ms, mode=machine.Timer.PERIODIC, callback=_tik)
    return _timer


# ---------------------------------------------------------- proje rotalari
# Bir projenin kendi web sayfasi / API'si icin IKINCI BIR SUNUCU ACMASINA
# GEREK YOK. CYD'de ikinci dinleyici soket lwIP tamponlariyla dahili DRAM'i
# tuketip paneli kilitliyordu (olculdu, kopru ve yuk_kontrol). Proje
# rotasini buraya kaydeder; ana sunucu /api disindaki istekleri once buraya
# bakar. Tek soket, tek dongu. Proje bitince rotalari kendiliginden silinir.
#
#   def sayfa(istek):                 # istek: {'yontem','yol','sorgu','govde'}
#       return '<h1>merhaba</h1>'     # str -> html/text, dict/list -> json,
#   cyd.rota('/selam', sayfa)         # bytes -> ham, (durum, tip, govde) -> ozel
#
# Isleyici ana sunucunun is parcaciginda kosar (CYD'de projeninkinde DEGIL):
# kisa tut, icinde cyd.sleep bekleme, paylasilan durumu basit degiskenlerde
# tut. print() projenin loguna gider (fonksiyonun globalleri projenin).
_rotalar = {}          # yol -> (fn, proje adi)


def rota(yol, fn):
    if not yol.startswith('/') or yol == '/' or yol.startswith('/api'):
        raise ValueError("rota '/' ya da '/api/...' olamaz: %s" % yol)
    _rotalar[yol] = (fn, job_name() or 'sistem')


def rota_sil(yol=None):
    """Tek rotayi ya da (yol verilmezse) bu projenin tum rotalarini kaldirir."""
    if yol is None:
        _rotalari_temizle(job_name() or 'sistem')
    else:
        _rotalar.pop(yol, None)


def _rotalari_temizle(proje):
    for y in [y for y, v in _rotalar.items() if v[1] == proje]:
        _rotalar.pop(y, None)


def rota_bul(yol):
    v = _rotalar.get(yol)
    return v[0] if v else None


def rotalar():
    return [{'yol': y, 'proje': v[1]} for y, v in _rotalar.items()]


def sleep(seconds):
    """Durdurulabilir bekleme. Erken kesilirse False doner.

    Thread'siz kartta her turda sunucuya da sira verir (pompala)."""
    end = time.ticks_add(time.ticks_ms(), int(seconds * 1000))
    while True:
        if should_stop():
            return False
        pompala()
        kalan = time.ticks_diff(end, time.ticks_ms())
        if kalan <= 0:
            break
        time.sleep_ms(min(50, max(1, kalan)))
    return not should_stop()


# ---------------------------------------------------------- ekran sahipligi
# Tek panel var ve ikinci bir framebuffer'a yer yok. Iki proje ayni anda
# cizerse veri bozulmaz (surucude kilit var) ama ust uste yazarlar.
def claim_display():
    """(True, None) ya da (False, 'sahip projenin adi')."""
    global _display_owner
    me = job_name() or 'sistem'
    if _display_owner and _display_owner != me:
        return False, _display_owner
    _display_owner = me
    return True, None


def release_display():
    global _display_owner
    if _display_owner == (job_name() or 'sistem'):
        _display_owner = None


def display_owner():
    return _display_owner


def warn_shared_display():
    """Baska bir proje ekrani kullaniyorsa bir kez uyarir."""
    me = job_name()
    if me and _display_owner and _display_owner != me and me not in _warned:
        _warned.add(me)
        print('[uyari] ekrani "%s" kullaniyor - ikiniz de ayni panele '
              'cizeceksiniz' % _display_owner)


# ------------------------------------------------------------------ bellek
def dram():
    """Bos dahili DRAM (bayt). BLE ve TLS'in sinirlandigi yer burasi -
    gc.mem_free() degil."""
    try:
        import esp32
        return sum(r[1] for r in esp32.idf_heap_info(esp32.HEAP_DATA))
    except Exception:
        return 0


# --------------------------------------------------------------------- ag
def wifi():
    """Zaten bagli olan istemci arayuzu.

    Kullan, ama active(False) ya da disconnect() CAGIRMA - web panelini de
    dusurursun. Ag ayarlarini degistirmek icin arayuzu kullan.
    """
    import network
    return network.WLAN(network.STA_IF)


# ---------------------------------------------------------------- buton
# Giris yakalama ZAMANLAMADAN BAGIMSIZ olmali. Olculdu (10 Eyl 2026): normal
# modda 10 ms'lik yoklayici, ekrana cizen komsuyla 973 ms, CPU birakmayan
# thread'le 3,4 sn bosluk gordu - insan basisi (50-100 ms) kacar. Kesme
# (Pin.irq) donanimdan gelir: hangi proje kosarsa kossun basis ANINDA
# sayilir; proje sirasi gelince okur. Basis kaybolmaz, gec fark edilir.
#
#   b = cyd.buton(22)                 # GPIO22 <-> GND arasi buton, dahili pull-up
#   b = cyd.buton(22, fn=lambda b: print('basildi', b.sayac))
#   while not cyd.should_stop():
#       if b.basildi():               # son sorudan beri basis var mi (tuketir)
#           ...
#       cyd.sleep(0.05)
#
# fn kisa tutulmali: micropython.schedule ile kesme disinda, ama o an hangi
# thread kosuyorsa onun icinde calisir. Proje bitince kesme kendiliginden
# kapanir (_butonlari_temizle).
_butonlar = []       # (proje adi, Buton)


class Buton:
    def __init__(self, pin, fn=None, pull=None, aktif=0, sekme_ms=40):
        from machine import Pin
        import micropython
        self._sched = micropython.schedule
        if pull is None:
            pull = Pin.PULL_UP if aktif == 0 else Pin.PULL_DOWN
        self.pin = Pin(pin, Pin.IN, pull) if isinstance(pin, int) else pin
        self.fn = fn
        self.sekme = sekme_ms
        self._aktif = aktif
        self._say = 0           # toplam basis (kesme sayar)
        self._okunan = 0        # basildi() ile tuketilen
        self._son = 0
        self._bekleyen = False
        self._cagir_ref = self._cagir
        self.pin.irq(handler=self._isr,
                     trigger=Pin.IRQ_FALLING if aktif == 0 else Pin.IRQ_RISING)
        _butonlar.append((job_name(), self))

    def _isr(self, p):
        # Kesme baglami: bellek ayirma yok, sadece sayac ve zaman.
        now = time.ticks_ms()
        if time.ticks_diff(now, self._son) < self.sekme:
            return
        self._son = now
        self._say += 1
        if self.fn and not self._bekleyen:
            self._bekleyen = True
            try:
                self._sched(self._cagir_ref, 0)
            except RuntimeError:
                self._bekleyen = False      # kuyruk dolu; sayac yine artti

    def _cagir(self, _):
        self._bekleyen = False
        try:
            self.fn(self)
        except Exception as e:
            print('buton hatasi:', e)

    @property
    def sayac(self):
        return self._say

    def basildi(self):
        """Son sorudan beri kac basis oldu (tuketir)."""
        n = self._say - self._okunan
        self._okunan = self._say
        return n

    def basili(self):
        return self.pin.value() == self._aktif

    def kapat(self):
        try:
            self.pin.irq(handler=None)
        except Exception:
            pass


def buton(pin, fn=None, **k):
    return Buton(pin, fn, **k)


def _butonlari_temizle(proje):
    global _butonlar
    kalan = []
    for ad, b in _butonlar:
        if ad == proje:
            b.kapat()
        else:
            kalan.append((ad, b))
    _butonlar = kalan
