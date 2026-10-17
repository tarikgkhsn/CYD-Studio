# UART HAT TANISI - GPIO27/22'nin ucunda ne var?
#
# Panel vekili 504 veriyor: istek gidiyor, cevap gelmiyor. Sebep uc taneden
# biri olabilir ve ayirt etmek icin tahmin degil olcum lazim:
#
#   a) Teller hala hedefin TX/RX'inde (GPIO1/3) -> karsida REPL var.
#      Gonderdigimiz \x01 orada Ctrl-A, yani ham REPL modu. Cevap gelir
#      ama cerceve degil, REPL baytlaridir.
#   b) Teller GPIO25/26'da ama hedef panel_uart.py'yi calistirmiyor
#      -> hicbir sey gelmez.
#   c) Teller dogru ve panel calisiyor -> \x02 ile baslayan cerceve gelir.
#
# Dort adimda hattin ne oldugunu soyluyor. Cikti USB konsolunda.
from machine import UART, Pin
import time
import cyd

TX = 27
RX = 22
BAUD = 115200

uart = UART(1, baudrate=BAUD, tx=Pin(TX), rx=Pin(RX), rxbuf=2048, timeout=0)


def topla(sure_ms):
    basla = time.ticks_ms()
    veri = b''
    while time.ticks_diff(time.ticks_ms(), basla) < sure_ms:
        n = uart.any()
        if n:
            veri += uart.read(n)
        cyd.sleep(0.01)
    return veri


def rapor(etiket, veri):
    print('  %-22s %4d bayt' % (etiket, len(veri)))
    if veri:
        g = veri[:160]
        print('       ham : %r' % g)


print()
print('=== UART HAT TANISI  TX=GPIO%d RX=GPIO%d @%d ===' % (TX, RX, BAUD))

uart.read()
print('1) sessiz dinleme (3 sn) - karsi uc kendiliginden konusuyor mu?')
a = topla(3000)
rapor('sessiz', a)

uart.read()
print('2) CR gonderildi - REPL varsa prompt doner')
uart.write(b'\r\n')
b = topla(1500)
rapor('CR sonrasi', b)

uart.read()
print('3) Ctrl-C + CR - REPL varsa >>> doner')
uart.write(b'\x03\r\n')
c = topla(2000)
rapor('Ctrl-C sonrasi', c)

uart.read()
print('4) panel cercevesi gonderildi - panel_uart.py varsa \\x02 doner')
istek = b'GET /api/caps HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n'
uart.write(b'\x01' + str(len(istek)).encode() + b'\n')
time.sleep_ms(5)
uart.write(istek)
e = topla(6000)
rapor('cerceve sonrasi', e)

hepsi = a + b + c + e
print()
print('--- SONUC ---')
if not hepsi:
    print('  HIC BAYT GELMEDI.')
    print('  -> Ya kablo takili degil / yanlis pinde,')
    print('     ya ortak GND yok, ya da hedef calismiyor.')
    print('  -> CYD GPIO22 hedefin CIKIS pinine bagli olmali.')
elif b'>>>' in hepsi or b'MicroPython' in hepsi or b'raw REPL' in hepsi:
    print('  KARSIDA REPL VAR - teller hala hedefin TX/RX (GPIO1/3)')
    print('     pinlerinde. Uclari GPIO26 (CYD 27 den) ve GPIO25')
    print('     (CYD 22 ye) pinlerine tasi.')
elif b'\x02' in e:
    print('  PANEL CEVAP VERDI - cerceve geldi, hat saglam.')
    print('  -> Sorun vekilin cozumleyicisinde, orayi kazacagiz.')
else:
    print('  Bayt geliyor ama tanidik bir sey degil.')
    print('  -> Baud uyusmuyor olabilir, ya da TX/RX ters.')
print('=== bitti ===')
