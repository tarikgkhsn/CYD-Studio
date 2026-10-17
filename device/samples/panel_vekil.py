# PANEL VEKILI - hedef kartin panelini agdan erisilebilir yapar.
#
#   Tarayici --HTTP--> BU KART :216 --UART--> hedef kartin server.py'si
#
# Hedefin WiFi'si acilamiyor (besleme brownout'a dusuyor, olculdu). Ama
# panelin WiFi'ye ihtiyaci yok: HTTP'yi tasiyan sey ne olursa olsun calisir.
# Bu kart agda oldugu icin tasiyicilik yapiyor.
#
# Tarayicida:  http://<bu kartin ip'si>:216/
#
# KABLOLAMA (kurtarma hatti olan GPIO27/22 AYRI DURUR, ona dokunma):
#     CYD GPIO27 (TX) ----> hedef GPIO26 (RX)
#     CYD GPIO22 (RX) <---- hedef GPIO25 (TX)
#     GND ortak
#
# Bunlar kurtarma koprusunun kullandigi TELLERIN AYNISI - degisen sadece
# hedef taraftaki uclar: GPIO3/GPIO1 yerine GPIO26/GPIO25. Yeni kablo
# gerekmiyor. Kurtarma (esptool / REPL) gerekince uclari hedefin TX/RX
# pinlerine geri tak.
#
# CYD'de 23/19 denedim, orasi SD kart hatti (VSPI 18/23/19/5) ve acilista
# store.init() oraya dokunuyor - 27/22 hem bos hem zaten kablolu.
#
# Hedefte calismasi gereken: projects/panel_uart.py
#
# SOLO MODDA CALISTIR: panel acikken WiFi sonrasi dahili DRAM 32 KB'ye
# duser ve ikinci bir TCP sunucusunun lwIP tamponlari o havuzu tuketip
# paneli kilitliyor (olculdu). Panelde bu projeyi sec -> "Solo".
#
# GERI DONUS: ekrandaki kirmizi tusa 1 sn basili tut.
from machine import UART, Pin
import machine
import socket
import time
import cyd

TX = 27              # cikis - hedefin GPIO26'sina
RX = 22              # giris - hedefin GPIO25'inden
BAUD = 115200
PORT = 216           # tarayici bu porta baglanir
RXBUF = 4096          # tarayiciya yazarken UART okunamiyor - genis tampon
PARCA = 256          # UART'a tek yazim - araya nefes payi

ISTEK_MS = 8000      # tarayicidan istegin tamami bu surede gelmeli
CEVAP_MS = 20000     # hedeften cevap bu surede gelmeli
YAZMA_MS = 10000     # tarayiciya yazma ust siniri
BOSTA_PANEL_MS = 20 * 60000
TUT_MS = 1000

uart = UART(1, baudrate=BAUD, tx=Pin(TX), rx=Pin(RX), rxbuf=RXBUF, timeout=0)

ip = cyd.wifi().ifconfig()[0]

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', PORT))
srv.listen(4)
srv.settimeout(0)                # bloke etmeyen - GIL'i tutmasin

print('panel vekili hazir')
print('  UART1  TX=GPIO%d  RX=GPIO%d  %d baud' % (TX, RX, BAUD))
print('  tarayicida:  http://%s:%d/' % (ip, PORT))
print('  hedefte projects/panel_uart.py calisiyor olmali')
print('  panele donmek icin ekrandaki tusa 1 sn basili tut')
print()

# ---------------------------------------------------------------- ekran
d = None
tp = None
BX = BY = BW = BH = 0
DURUM_Y = 0
try:
    d = cyd.display()
    BW = min(220, d.width - 40)
    BH = 46
    BX = (d.width - BW) // 2
    BY = d.height - BH - 12
    DURUM_Y = 100 if d.height >= 200 else 40
except Exception as e:
    print('ekran yok:', e)
try:
    if d is not None:
        tp = cyd.touch()
except Exception as e:
    print('dokunmatik yok:', e)


def tus_ciz(oran=0.0):
    if d is None:
        return
    try:
        d.fill_rect(BX, BY, BW, BH, cyd.BLACK)
        d.rect(BX, BY, BW, BH, cyd.RED)
        if oran > 0:
            d.fill_rect(BX + 2, BY + 2, int((BW - 4) * min(1.0, oran)),
                        BH - 4, cyd.RED)
        d.text('PANELE DON', BX + 18, BY + 10, cyd.WHITE, cyd.BLACK, 2)
        if oran <= 0:
            d.text('1 sn basili tut', BX + 34, BY + 30, cyd.GREY, cyd.BLACK, 1)
    except Exception:
        pass


def durum_yaz(metin, renk):
    if d is None:
        return
    try:
        d.fill_rect(0, DURUM_Y, d.width, 22, cyd.BLACK)
        d.text(metin, 8, DURUM_Y, renk, cyd.BLACK, 2)
    except Exception:
        pass


if d is not None:
    try:
        d.fill(cyd.BLACK)
        d.text('PANEL VEKILI', 8, 10, cyd.CYAN, cyd.BLACK, 3)
        d.text('%s:%d' % (ip, PORT), 8, 48, cyd.WHITE, cyd.BLACK, 2)
        d.text('UART1 TX=%d RX=%d' % (TX, RX), 8, 76, cyd.GREY, cyd.BLACK, 1)
        durum_yaz('istek bekleniyor', cyd.YELLOW)
        tus_ciz()
    except Exception as e:
        print('cizim hatasi:', e)


def panele_don(sebep):
    print('panele donuluyor (%s)' % sebep)
    if d is not None:
        try:
            d.fill(cyd.BLACK)
            d.text('PANELE', 40, 70, cyd.GREEN, cyd.BLACK, 3)
            d.text('DONULUYOR', 40, 112, cyd.GREEN, cyd.BLACK, 3)
        except Exception:
            pass
    time.sleep_ms(600)
    machine.reset()


basili = None


def tusu_yokla():
    """Ekran tusu. Kazara dokunma resetlemesin diye basili tutma sarti."""
    global basili
    if tp is None:
        return
    try:
        if tp.pressed():
            nokta = tp.touch()
            if (nokta and BX <= nokta[0] <= BX + BW
                    and BY <= nokta[1] <= BY + BH):
                if basili is None:
                    basili = time.ticks_ms()
                gecen = time.ticks_diff(time.ticks_ms(), basili)
                tus_ciz(gecen / TUT_MS)
                if gecen >= TUT_MS:
                    panele_don('ekran tusu')
            elif basili is not None:
                basili = None
                tus_ciz()
        elif basili is not None:
            basili = None
            tus_ciz()
    except Exception:
        pass


# ---------------------------------------------------------------- yardim
def uart_yaz(b):
    for i in range(0, len(b), PARCA):
        uart.write(b[i:i + PARCA])
        time.sleep_ms(1)


def icerik_boyu(bas):
    for satir in bas.split(b'\r\n'):
        if satir[:15].lower() == b'content-length:':
            try:
                return int(satir[15:].strip())
            except ValueError:
                return 0
    return 0


def istek_oku(sock):
    """Tarayicidan HTTP istegin TAMAMINI al - govde dahil.

    Govdeyi beklemek sart: UART'a yarim istek gonderirsek hedef onu
    hicbir zaman tamamlayamaz ve baglanti asili kalir.
    """
    veri = b''
    son = time.ticks_ms()
    while True:
        try:
            p = sock.recv(512)
            if p:
                veri += p
                son = time.ticks_ms()
            elif p == b'':
                return veri or None
        except OSError:
            pass
        if b'\r\n\r\n' in veri:
            bas, govde = veri.split(b'\r\n\r\n', 1)
            gerek = icerik_boyu(bas)
            if len(govde) >= gerek:
                return bas + b'\r\n\r\n' + govde[:gerek]
        if time.ticks_diff(time.ticks_ms(), son) > ISTEK_MS:
            return None
        tusu_yokla()
        cyd.sleep(0.002)


def sokete_yaz(sock, veri):
    """Bloke etmeyen sokete tam yazim - EAGAIN'de bekleyip tekrar dener."""
    i = 0
    son = time.ticks_ms()
    while i < len(veri):
        try:
            n = sock.write(veri[i:i + 512])
            if n:
                i += n
                son = time.ticks_ms()
            else:
                cyd.sleep(0.002)
        except OSError:
            cyd.sleep(0.002)
        if time.ticks_diff(time.ticks_ms(), son) > YAZMA_MS:
            return False
    return True


def cevap_aktar(sock):
    """Hedeften gelen cerceveleri cozup tarayiciya akitir.

    \x02<n>\n<parca>  = cevap parcasi
    \x03\n            = cevap bitti
    """
    tampon = b''
    son = time.ticks_ms()
    bayt = 0
    while True:
        n = uart.any()
        if n:
            tampon += uart.read(n)
            son = time.ticks_ms()
        ilerledi = True
        while ilerledi and tampon:
            ilerledi = False
            tip = tampon[0]
            if tip == 3:
                if len(tampon) < 2:
                    break
                return bayt                      # bitti
            if tip == 2:
                j = tampon.find(b'\n')
                if j < 0:
                    break
                try:
                    boy = int(tampon[1:j])
                except ValueError:
                    tampon = tampon[j + 1:]
                    ilerledi = True
                    continue
                if len(tampon) < j + 1 + boy:
                    break
                parca = tampon[j + 1:j + 1 + boy]
                tampon = tampon[j + 1 + boy:]
                if not sokete_yaz(sock, parca):
                    return -1
                bayt += len(parca)
                ilerledi = True
                continue
            tampon = tampon[1:]                  # cop bayt - at
            ilerledi = True
        if time.ticks_diff(time.ticks_ms(), son) > CEVAP_MS:
            return -1
        tusu_yokla()
        cyd.sleep(0.002)


VEKIL_HATA = (b'HTTP/1.1 504 Gateway Timeout\r\n'
              b'Content-Type: text/plain; charset=utf-8\r\n'
              b'Content-Length: 46\r\nConnection: close\r\n\r\n'
              b'hedef kart cevap vermedi - UART baglantisini kontrol et')


# ---------------------------------------------------------------- dongu
istek = 0
son_is = time.ticks_ms()

while not cyd.should_stop():
    tusu_yokla()
    try:
        sock, adres = srv.accept()
    except OSError:
        if time.ticks_diff(time.ticks_ms(), son_is) > BOSTA_PANEL_MS:
            panele_don('%d dk bosta' % (BOSTA_PANEL_MS // 60000))
        cyd.sleep(0.02)
        continue

    son_is = time.ticks_ms()
    try:
        sock.settimeout(0)
    except Exception:
        pass
    try:
        ham = istek_oku(sock)
        if not ham:
            continue
        istek += 1
        uart.read()                     # onceki cevabin artiklarini at
        uart_yaz(b'\x01' + str(len(ham)).encode() + b'\n')
        uart_yaz(ham)
        durum_yaz('istek #%d' % istek, cyd.GREEN)
        n = cevap_aktar(sock)
        if n < 0:
            print('#%d: hedef cevap vermedi' % istek)
            sokete_yaz(sock, VEKIL_HATA)
            durum_yaz('hedef sessiz', cyd.RED)
        else:
            print('#%d %s -> %d bayt' % (istek, ham.split(b' ')[1][:40], n))
    except Exception as e:
        print('vekil hatasi:', e)
    finally:
        try:
            sock.close()
        except Exception:
            pass

try:
    srv.close()
except Exception:
    pass
print('panel vekili kapandi - %d istek' % istek)
