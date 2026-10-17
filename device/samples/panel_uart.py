# PANELI UART UZERINDEN SERVIS ET - WiFi'ye hic dokunmadan.
#
# NEDEN: bu kartin beslemesi WiFi vericisinin anlik akimini kaldiramiyor;
# radyo acilir acilmaz brownout ile resetleniyor (olculdu). Ama panelin
# WiFi'ye ihtiyaci yok - HTTP'yi tasiyan sey ne olursa olsun calisir.
# Burada tasiyici UART: karsi uctaki CYD agda, istekleri bize aktariyor.
#
#   Tarayici --HTTP--> CYD :216 --UART--> BU KART (server.py)
#
# GUZEL TARAFI: server.py hic degismiyor. Sadece uc sey istiyor -
# sock.accept(), conn.read/readline/write/close. Bunlar soket olmak
# zorunda degil. Asagidaki iki sinif UART'i soket gibi gosteriyor,
# Server.listen() override edilince mevcut panel oldugu gibi kosuyor.
#
# NEDEN UART0 DEGIL: ESP32'de REPL ve print() cikisi cekirdege gomulu
# UART0 konsoluna bagli ve dupterm ile ayrilamiyor (denendi: slot 0 None,
# slot 1 "invalid dupterm index"). Ayni teli paylassaydik panel verisi ile
# konsol ciktisi birbirine karisirdi. Bu yuzden panel AYRI bir UART'ta;
# UART0 kurtarma ve esptool icin bos kaliyor.
#
# KABLOLAMA:
#     hedef GPIO25 (TX) ----> CYD GPIO19 (RX)
#     hedef GPIO26 (RX) <---- CYD GPIO23 (TX)
#     GND ortak  (zaten var)
#
# CERCEVE PROTOKOLU - UART akistir, istegin nerede bittigi bellidir degil:
#     CYD -> kart :  \x01<uzunluk>\n<istek baytlari>
#     kart -> CYD :  \x02<uzunluk>\n<parca>     (cevap parca parca gelir)
#                    \x03\n                     (cevap bitti, baglanti kapandi)
from machine import UART, Pin
import time
import store
import jobs
import server

TX = 25
RX = 26
BAUD = 115200
RXBUF = 2048
PARCA = 256          # UART'a tek seferde yazilan bayt - araya nefes payi


class UartConn:
    """Tek bir HTTP istegini temsil eden sahte soket."""

    def __init__(self, link, veri):
        self.link = link
        self.buf = veri
        self.pos = 0
        self.kapali = False

    def settimeout(self, t):
        pass

    def read(self, n=-1):
        if n is None or n < 0:
            n = len(self.buf) - self.pos
        d = self.buf[self.pos:self.pos + n]
        self.pos += len(d)
        return d

    def readline(self):
        i = self.buf.find(b'\n', self.pos)
        if i < 0:
            d = self.buf[self.pos:]
            self.pos = len(self.buf)
            return d
        d = self.buf[self.pos:i + 1]
        self.pos = i + 1
        return d

    def write(self, b):
        if isinstance(b, str):
            b = b.encode('utf-8')
        if b:
            self.link.cerceve(2, b)
        return len(b)

    def close(self):
        if not self.kapali:
            self.kapali = True
            self.link.bitir()


class UartDinleyici:
    """socket.accept() taklidi - istek gelene kadar BEKLER.

    Once EAGAIN atip server.py'nin "su an istek yok" dalina dusmesini
    denedim; hedefteki server.py surumu EAGAIN'i hata sayip dinleyiciyi
    yeniden kuruyordu ve yarim cerceveler kayboluyordu. Beklemek surumden
    bagimsiz calisiyor. Beklerken panel nabzini kendimiz atiyoruz ki
    jobs.Manager'in bekcisi paneli olu sanmasin.
    """

    def __init__(self, uart, srv):
        self.uart = uart
        self.srv = srv
        self.gelen = b''

    def settimeout(self, t):
        pass

    def close(self):
        pass

    def _cozumle(self):
        """Tamponda tam bir istek varsa cikar, yoksa None."""
        if not self.gelen:
            return None
        i = self.gelen.find(b'\x01')
        if i < 0:
            self.gelen = b''                   # cop - at
            return None
        if i:
            self.gelen = self.gelen[i:]
        j = self.gelen.find(b'\n')
        if j < 0:
            return None                        # basligin tamami gelmedi
        try:
            boy = int(self.gelen[1:j])
        except ValueError:
            self.gelen = self.gelen[j + 1:]
            return None
        if len(self.gelen) < j + 1 + boy:
            return None                        # govde tamamlanmadi
        veri = self.gelen[j + 1:j + 1 + boy]
        self.gelen = self.gelen[j + 1 + boy:]
        return veri

    def accept(self):
        while True:
            n = self.uart.any()
            if n:
                self.gelen += self.uart.read(n)
                veri = self._cozumle()
                if veri is not None:
                    return UartConn(self, veri), ('uart', 0)
            self.srv.kalp = time.ticks_ms()    # panel nabzi
            time.sleep_ms(5)

    # ---------------------------------------------------------- cerceve
    def cerceve(self, tip, veri):
        self._gonder(bytes([tip]) + str(len(veri)).encode() + b'\n')
        self._gonder(veri)

    def bitir(self):
        self._gonder(b'\x03\n')

    def _gonder(self, b):
        # uart.write bloke eder ve o sure boyunca GIL birakilmaz; parcalara
        # bolup araya 1 ms koyuyoruz ki calisan projeler ac kalmasin.
        # 256 bayt 115200 baud'da ~22 ms, 1 ms nefes payi %4.5.
        for i in range(0, len(b), PARCA):
            self.uart.write(b[i:i + PARCA])
            time.sleep_ms(1)


class UartServer(server.Server):
    """Ayni panel, sadece tasiyicisi farkli."""

    def __init__(self, mgr, uart):
        server.Server.__init__(self, mgr)
        self.uart = uart

    def listen(self):
        self.sock = UartDinleyici(self.uart, self)
        return self.sock


uart = UART(2, baudrate=BAUD, tx=Pin(TX), rx=Pin(RX), rxbuf=RXBUF, timeout=0)

print('panel UART uzerinden servis edilecek')
print('  UART2  TX=GPIO%d  RX=GPIO%d  %d baud' % (TX, RX, BAUD))
print('  karsi uc: CYD, http://<cyd-ip>:216/')

try:
    base = store.init()
    print('projeler:', base)
except Exception as e:
    print('depolama hatasi:', e)

mgr = jobs.Manager()
srv = UartServer(mgr, uart)
mgr.system('panel UART uzerinden servis ediliyor (WiFi kapali)')
srv.serve_forever()
