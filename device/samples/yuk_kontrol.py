# YUK KONTROL - kucuk web sayfasi ile ULN2803A yuku surer
#
#   Tarayici:  http://<cyd-ip>/yuk        <- ANA SUNUCUNUN portu, ayri port YOK
#
# OZELLIKLER
#   * AC / KAPAT dugmesi
#   * Yanip sonme: acik ve kapali sureleri saniye cinsinden ayarlanir
#   * Zamanli: her gun su saatte acil, su saatte kapan
#
# KABLOLAMA - uln2803_yuk.py ile ayni
#     CYD GPIO27 -> ULN 1B (pin 1)      CYD GND -> ULN GND (pin 9) + 12V (−)
#     12V (+)    -> ULN COM (pin 10) ve yukun (+) ucu
#     Yuk (−)    -> ULN 1C (pin 18)     <-- adaptorun eksisine DEGIL
#
#
# NEDEN cyd.rota - IKINCI SUNUCU YOK
#
# Bu projenin ilk surumu 8080'de kendi soketini aciyordu. CYD'de ikinci
# dinleyici soket lwIP tamponlariyla dahili DRAM'i tuketip paneli
# kilitliyordu (UART koprusunde olculdu). Simdi sayfa ve API ana sunucuya
# ROTA olarak kaydediliyor: tek soket, tek dongu, panel bozulmaz, proje
# durunca rotalar kendiliginden silinir. Panelde "Uygulamalar:" satirinda
# baglanti olarak gorunur.
#
#   cyd.rota('/yuk', sayfa)        isleyici istek sozlugu alir:
#                                  {'yontem','yol','sorgu','govde'}
#                                  str -> html, dict -> json
#
# Isleyici sunucunun is parcaciginda kosar; kisa tutuluyor, sadece
# degiskenleri okuyup yaziyor. Asil isi (pin surme, zamanlama) asagidaki
# ana dongu yapar.
import cyd
import time
from machine import Pin

PIN = 27
SAAT_FARKI = 3          # Turkiye UTC+3

# ------------------------------------------------------------- durum
mod = 'kapali'          # kapali | acik | yanip | zamanli
acik_sn = 1.0
kapali_sn = 1.0
bas_saat = (7, 0)       # zamanli mod: acilma saati
bit_saat = (23, 0)      # zamanli mod: kapanma saati

yuk = Pin(PIN, Pin.OUT, value=0)
_acik = False
_gecis = time.ticks_ms()
saat_var = False
ip = cyd.wifi().ifconfig()[0]


def cikis(deger):
    global _acik
    if deger != _acik:
        _acik = deger
        yuk.value(1 if deger else 0)
        ekran_ciz()


# --------------------------------------------------------------- saat
try:
    import ntptime
    ntptime.settime()
    saat_var = True
    print('saat NTP ile ayarlandi')
except Exception as e:
    print('NTP basarisiz (%s) - zamanli mod calismaz' % e)


def simdi_hm():
    if not saat_var:
        return None
    t = time.localtime(time.time() + SAAT_FARKI * 3600)
    return (t[3], t[4])


def zamanda_mi():
    hm = simdi_hm()
    if hm is None:
        return False
    su = hm[0] * 60 + hm[1]
    bas = bas_saat[0] * 60 + bas_saat[1]
    bit = bit_saat[0] * 60 + bit_saat[1]
    if bas == bit:
        return False
    if bas < bit:
        return bas <= su < bit
    return su >= bas or su < bit          # gece yarisini asan aralik


# -------------------------------------------------------------- ekran
d = None
try:
    d = cyd.display()
except Exception:
    pass
_son_ciz = None


def ekran_ciz():
    """Sadece durum degisince cizer."""
    global _son_ciz
    if d is None:
        return
    anahtar = (mod, _acik)
    if anahtar == _son_ciz:
        return
    _son_ciz = anahtar
    try:
        d.fill(cyd.BLACK)
        d.text('YUK KONTROL', 8, 8, cyd.CYAN, cyd.BLACK, 2)
        d.text('%s/yuk' % ip, 8, 34, cyd.WHITE, cyd.BLACK, 2)
        if _acik:
            d.text('ACIK', 12, 78, cyd.RED, cyd.BLACK, 5)
        else:
            d.text('kapali', 12, 78, cyd.GREEN, cyd.BLACK, 4)
        d.text('mod: %s' % mod, 12, 145, cyd.WHITE, cyd.BLACK, 2)
        hm = simdi_hm()
        if hm:
            d.text('%02d:%02d' % hm, 12, 178, cyd.GREY, cyd.BLACK, 2)
    except Exception:
        pass


# -------------------------------------------------------------- sayfa
SAYFA = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yuk Kontrol</title><style>
*{box-sizing:border-box}
body{margin:0;padding:16px;background:#12171c;color:#e6ecf1;
font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
h1{font-size:19px;margin:0 0 14px}
.d{background:#1b232b;border:1px solid #2b3641;border-radius:6px;
padding:14px;margin-bottom:12px}
.d h2{font-size:13px;margin:0 0 10px;color:#8fa0af;font-weight:600;
letter-spacing:.06em;text-transform:uppercase}
.big{font-size:32px;font-weight:700;letter-spacing:-.02em}
.on{color:#ff6b5a}.off{color:#4fbf87}
button{font:inherit;font-weight:600;padding:11px 16px;border-radius:5px;
border:1px solid #35424e;background:#232d36;color:#e6ecf1;cursor:pointer}
button:active{transform:translateY(1px)}
.ac{background:#8c2f26;border-color:#b03a2e}
.kp{background:#1f5d45;border-color:#2a7d5c}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input{font:inherit;width:80px;padding:9px;border-radius:5px;
border:1px solid #35424e;background:#141b21;color:#e6ecf1}
label{color:#8fa0af;font-size:13px}
.mod{font-size:13px;color:#8fa0af;margin-top:8px}
</style></head><body>
<h1>Yuk Kontrol</h1>

<div class="d">
  <h2>Durum</h2>
  <div class="big" id="dr">-</div>
  <div class="mod">mod: <b id="md">-</b> &middot; saat: <b id="st">-</b></div>
  <div class="row" style="margin-top:12px">
    <button class="ac" onclick="g('mod=acik')">AC</button>
    <button class="kp" onclick="g('mod=kapali')">KAPAT</button>
  </div>
</div>

<div class="d">
  <h2>Yanip sonme</h2>
  <div class="row">
    <label>acik</label><input id="a" type="number" step="0.1" min="0.1" value="1">
    <label>sn &middot; kapali</label><input id="k" type="number" step="0.1" min="0.1" value="1">
    <label>sn</label>
  </div>
  <div class="row" style="margin-top:10px">
    <button onclick="g('mod=yanip&a='+a.value+'&k='+k.value)">Basla</button>
  </div>
</div>

<div class="d">
  <h2>Zamanli</h2>
  <div class="row">
    <label>acil</label><input id="b" type="time" value="07:00" style="width:120px">
    <label>kapan</label><input id="t" type="time" value="23:00" style="width:120px">
  </div>
  <div class="row" style="margin-top:10px">
    <button onclick="g('mod=zamanli&bas='+b.value+'&bit='+t.value)">Kur</button>
  </div>
  <div class="mod" id="zn"></div>
</div>

<script>
function g(q){fetch('/yuk/ayar?'+q).then(r=>r.json()).then(u)}
function u(s){
  dr.textContent = s.acik ? 'ACIK' : 'kapali';
  dr.className = 'big ' + (s.acik ? 'on' : 'off');
  md.textContent = s.mod;
  st.textContent = s.saat || 'yok';
  zn.textContent = s.saat ? '' : 'NTP kurulamadi - zamanli mod calismaz';
  if(document.activeElement.tagName!='INPUT'){
    a.value=s.a; k.value=s.k; b.value=s.bas; t.value=s.bit;
  }
}
function y(){fetch('/yuk/durum').then(r=>r.json()).then(u).catch(()=>{})}
y(); setInterval(y, 2000);
</script></body></html>"""


# ------------------------------------------------------------- rotalar
def _hm_coz(s, varsayilan):
    try:
        h, m = s.split(':')
        h = int(h)
        m = int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return (h, m)
    except Exception:
        pass
    return varsayilan


def _durum():
    hm = simdi_hm()
    return {'acik': _acik, 'mod': mod,
            'a': acik_sn, 'k': kapali_sn,
            'bas': '%02d:%02d' % bas_saat, 'bit': '%02d:%02d' % bit_saat,
            'saat': ('%02d:%02d' % hm) if hm else None}


def _uygula(q):
    global mod, acik_sn, kapali_sn, bas_saat, bit_saat, _gecis
    m = q.get('mod', '')
    if m in ('acik', 'kapali', 'yanip', 'zamanli'):
        mod = m
    try:
        if 'a' in q:
            acik_sn = max(0.1, float(q['a']))
        if 'k' in q:
            kapali_sn = max(0.1, float(q['k']))
    except ValueError:
        pass
    if 'bas' in q:
        bas_saat = _hm_coz(q['bas'], bas_saat)
    if 'bit' in q:
        bit_saat = _hm_coz(q['bit'], bit_saat)
    _gecis = time.ticks_ms()
    print('mod=%s acik=%.1f kapali=%.1f %02d:%02d-%02d:%02d'
          % (mod, acik_sn, kapali_sn,
             bas_saat[0], bas_saat[1], bit_saat[0], bit_saat[1]))


def r_sayfa(istek):
    return SAYFA


def r_durum(istek):
    return _durum()


def r_ayar(istek):
    _uygula(istek['sorgu'])
    return _durum()


cyd.rota('/yuk', r_sayfa)
cyd.rota('/yuk/durum', r_durum)
cyd.rota('/yuk/ayar', r_ayar)

print('yuk kontrol hazir')
print('  tarayicida:  http://%s/yuk' % ip)
print('  yuk pini  :  GPIO%d' % PIN)
print('  ayri sunucu yok - ana panelin portu, "Uygulamalar" satirinda')
print()


# ------------------------------------------------------------- dongu
def _cikis_guncelle():
    global _gecis
    if mod == 'acik':
        cikis(True)
    elif mod == 'kapali':
        cikis(False)
    elif mod == 'yanip':
        sure = (acik_sn if _acik else kapali_sn) * 1000
        if time.ticks_diff(time.ticks_ms(), _gecis) >= sure:
            _gecis = time.ticks_ms()
            cikis(not _acik)
    elif mod == 'zamanli':
        cikis(zamanda_mi())


ekran_ciz()

try:
    while not cyd.should_stop():
        _cikis_guncelle()
        cyd.sleep(0.02)
finally:
    yuk.value(0)
    cyd.rota_sil()
    print('yuk KAPATILDI, rotalar kaldirildi')
