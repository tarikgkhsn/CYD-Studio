# UART KOPRUSU - bu karti baska bir ESP'yi programlamak icin kullanir.
#
# NEDEN: USB'si bozuk / erisilemeyen bir karta bu kart uzerinden ulasmak.
# PC <--WiFi--> CYD <--UART--> hedef kart
#
# PC tarafinda pyserial'in socket:// destegi sayesinde esptool ve mpremote
# bu koprüyu gercek bir seri port gibi gorur:
#
#   python -m esptool --port socket://192.168.0.217:2323 \
#          --before no-reset --after no-reset flash-id
#   python -m mpremote connect socket://192.168.0.217:2323
#
# DIKKAT: bu port HEDEF karta acilir, CYD'ye degil. Buraya gonderilen
# machine.reset() hedefi resetler. CYD'yi resetlemek icin ekrandaki tusu
# kullan, ya da USB konsolunu.
#
# SOLO MODDA CALISTIR. Panel acikken WiFi'den sonra dahili DRAM 32 KB'ye
# duser; kopru ikinci bir TCP sunucusu actigi icin lwIP tamponlari ayni
# havuzu tuketiyor ve panelin accept()'i cokuyor - olculdu, panel kilitlendi
# ve fiziksel reset gerekti. Solo modda kopru ~59 KB fazladan DRAM aliyor ve
# sorunsuz calisiyor. Panelde projeyi sec, sonra "Solo" butonu.
#
# GERI DONUS: ekranda "PANELE DON" tusu var, 1 saniye basili tut. Ayrica
# hic baglanti gelmezse belirli sure sonra kendi kendine panele doner.
#
# KABLOLAMA (uc kablo, TX-RX capraz) - hepsi EXTENDED IO konnektorunde:
#     CYD GPIO27 (TX) ----> hedefin RX pini (GPIO3)
#     CYD GPIO22 (RX) <---- hedefin TX pini (GPIO1)
#     CYD GND       ------- hedef GND        <- ortak toprak SART
#
# KARTIN "TX/RX" ETIKETLI KONNEKTORUNU KULLANMA: oradaki pinler GPIO1 ve
# GPIO3, yani CYD'nin kendi USB konsolunun hatti. Kart uzerindeki CH340
# ile hedefin TX'i ayni teli surmeye calisir, veri bozulur.
#
# Hedef tarafinda ise TX/RX pinleri ZORUNLU: ESP32'nin ROM bootloader'i
# sadece kendi UART0'ini (GPIO1/GPIO3) dinler.
#
#   Hedefi CYD'den beslemek istersen: CYD 3.3V -> hedef 3.3V.
#   Bu FLASH icin yeterlidir (~100 mA). Hedefte WiFi calistiracaksan
#   yetmez - o zaman hedefe kendi beslemesini ver, sadece GND ortak olsun.
#
# ONEMLI: DTR/RTS koprüden gecmez, yani otomatik download modu YOK.
# Hedef karti elle download moduna almalisin:
#     BOOT'a bas ve TUT -> RESET'e bas-birak -> BOOT'u BIRAKMA
# ve esptool'u mutlaka --before no-reset --after no-reset ile calistir.
from machine import UART, Pin
import machine
import socket
import time
import cyd

TX = 27       # cikis - hedefin RX ine  (DOGRULANDI)
RX = 22       # giris - hedefin TX inden (DOGRULANDI)
BAUD = 115200
PORT = 2323
TAMPON = 2048        # UART RX tamponu - varsayilan 256 flash sirasinda tasar

BOSTA_BIRAK_MS = 20000        # olu TCP baglantisini birak, yenisi gelebilsin
BOSTA_PANEL_MS = 15 * 60000   # hic is gelmezse kendi kendine panele don
TUT_MS = 1000                 # "PANELE DON" icin basili tutma suresi


# txbuf parametresi bu portta EPERM veriyor - sadece rxbuf veriliyor.
# Onemli olan zaten RX tamponu: flash sirasinda hedeften gelen veriyi
# kaybetmemek icin varsayilan 256 bayt yetmiyor.
uart = UART(1, baudrate=BAUD, tx=Pin(TX), rx=Pin(RX),
            rxbuf=TAMPON, timeout=0)

ip = cyd.wifi().ifconfig()[0]

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', PORT))
srv.listen(1)
# BLOKE ETMEYEN: zaman asimli accept() MicroPython'da beklerken GIL'i
# birakmiyor ve web panelini ac birakiyor (panel bekcisi bu yuzden
# koprüyu durdurmustu). Yoklayip cyd.sleep ile is parcacigini veriyoruz.
srv.settimeout(0)

print('UART koprusu hazir')
print('  UART1  TX=GPIO%d  RX=GPIO%d  %d baud' % (TX, RX, BAUD))
print('  TCP    %s:%d   -> HEDEF karta acilir' % (ip, PORT))
print()
print('PC tarafinda:')
print('  python -m esptool --port socket://%s:%d \\' % (ip, PORT))
print('         --before no-reset --after no-reset flash-id')
print('  python -m mpremote connect socket://%s:%d' % (ip, PORT))
print()
print('Hedefi ELLE download moduna al: BOOT bas-tut -> RESET -> BOOT birakma')
print('Panele donmek icin ekrandaki tusa 1 sn basili tut.')
print()

# ---------------------------------------------------------------- ekran
d = None
tp = None
# Tus koordinatlari ekran olcusune gore kuruluyor ki kucuk panellerde
# de tasmasin.
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
    """PANELE DON tusu. `oran` basili tutma ilerlemesi (0..1)."""
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
        d.text('UART KOPRUSU', 8, 10, cyd.CYAN, cyd.BLACK, 3)
        d.text('%s:%d' % (ip, PORT), 8, 48, cyd.WHITE, cyd.BLACK, 2)
        d.text('TX=%d RX=%d %d baud' % (TX, RX, BAUD), 8, 76,
               cyd.GREY, cyd.BLACK, 1)
        durum_yaz('baglanti bekleniyor', cyd.YELLOW)
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


# ---------------------------------------------------------------- dongu
conn = None
giden = 0        # PC -> hedef
gelen = 0        # hedef -> PC
son_rapor = time.ticks_ms()
son_veri = time.ticks_ms()
son_is = time.ticks_ms()          # en son ne zaman is vardi
basili = None                     # tusa basmaya baslanan an

while not cyd.should_stop():
    # --- ekran tusu: kazara dokunma resetlemesin diye BASILI TUTMA.
    # pressed() sadece PENIRQ pinini okur, bedeli yok; koordinat icin
    # SPI'ye ancak dokunulmussa gidiyoruz.
    if tp is not None:
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

    # --- baglanti kabul: YENI GELEN KAZANIR
    # Eskiden sadece conn None iken kabul ediyorduk; esptool/mpremote
    # baglantiyi duzgun kapatmadan cikinca kopru onu hala acik saniyor ve
    # sonraki istegi reddediyordu ("port is in use"). deploy arka arkaya
    # dosya kopyaladigi icin hepsi patliyordu. Artik her turda yeni
    # baglantiya bakiyoruz ve gelirse eskisini birakiyoruz.
    try:
        yeni, adres = srv.accept()
        yeni.settimeout(0)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            print('yeni baglanti geldi, eskisi birakildi')
        conn = yeni
        uart.read()                     # eski baytlari at
        giden = gelen = 0
        son_veri = son_is = time.ticks_ms()
        print('baglandi: %s' % (adres,))
        durum_yaz('BAGLI', cyd.GREEN)
    except OSError:
        pass                            # yeni baglanti yok - normal

    if conn is None:
        # Kimse gelmiyorsa sonsuza kadar kopru olarak beklemenin anlami yok;
        # kart panele donsun ki kullanici erisebilsin.
        if time.ticks_diff(time.ticks_ms(), son_is) > BOSTA_PANEL_MS:
            panele_don('%d dk bosta' % (BOSTA_PANEL_MS // 60000))
        cyd.sleep(0.05)
        continue

    calisti = False

    # --- PC -> hedef
    try:
        veri = conn.recv(256)
        if veri:
            # uart.write BLOKE EDER: 512 bayt 115200 baud'da 44 ms surer ve
            # o sure boyunca GIL birakilmaz - panel ac kalir, bekci kopruyu
            # keserdi. 64 baytlik parcalara bolup aralarda yer birakiyoruz.
            for i in range(0, len(veri), 64):
                uart.write(veri[i:i + 64])
                time.sleep_ms(1)
            giden += len(veri)
            calisti = True
        elif veri == b'':
            raise OSError('kapandi')
    except OSError as e:
        if 'kapandi' in str(e):
            print('baglanti kapandi (%d/%d bayt)' % (giden, gelen))
            try:
                conn.close()
            except Exception:
                pass
            conn = None
            son_is = time.ticks_ms()
            durum_yaz('baglanti bekleniyor', cyd.YELLOW)
            continue
        # EAGAIN - veri yok, normal

    # --- hedef -> PC
    n = uart.any()
    if n:
        veri = uart.read(min(n, 512))
        if veri:
            try:
                conn.write(veri)
                gelen += len(veri)
                calisti = True
            except OSError:
                pass

    # Veri akarken bile is parcacigini birakiyoruz. Onceden birakmiyordum
    # ("flash yavaslamasin" diye) ve panel bekcisi kopruyu durduruyordu.
    # Maliyeti onemsiz: 512 baytlik parca 115200 baud'da zaten ~44 ms
    # suruyor, 1 ms'lik nefes payi %2 bile degil.
    if calisti:
        son_veri = son_is = time.ticks_ms()
        time.sleep_ms(1)
    else:
        cyd.sleep(0.005)
        # Olu baglantiyi birak, yenisi gelebilsin
        if time.ticks_diff(time.ticks_ms(), son_veri) > BOSTA_BIRAK_MS:
            print('baglanti %d sn bosta kaldi - birakiliyor (%d/%d bayt)'
                  % (BOSTA_BIRAK_MS // 1000, giden, gelen))
            try:
                conn.close()
            except Exception:
                pass
            conn = None
            son_veri = time.ticks_ms()
            durum_yaz('baglanti bekleniyor', cyd.YELLOW)
            continue

    if time.ticks_diff(time.ticks_ms(), son_rapor) > 5000 and (giden or gelen):
        son_rapor = time.ticks_ms()
        print('koprü: PC->hedef %d bayt | hedef->PC %d bayt' % (giden, gelen))
        if d is not None:
            try:
                d.fill_rect(0, DURUM_Y + 26, d.width, 18, cyd.BLACK)
                d.text('%d / %d bayt' % (giden, gelen), 8, DURUM_Y + 28,
                       cyd.GREY, cyd.BLACK, 1)
            except Exception:
                pass

try:
    if conn:
        conn.close()
    srv.close()
except Exception:
    pass
print('koprü kapandi - toplam PC->hedef %d, hedef->PC %d bayt' % (giden, gelen))
