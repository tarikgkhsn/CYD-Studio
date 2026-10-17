# BUTON - kesme ile, kacirmadan.
#
# KABLOLAMA: buton bir ucu GPIO22, obur ucu GND. Direnc gerekmez, dahili
# pull-up acik. (NodeMCU'da D1=GPIO5 gibi bos bir pin sec.)
#
# NEDEN cyd.buton, neden pin.value() yoklamasi degil?
#   Olculdu (CYD, 10 Eyl 2026): 50 taklit basis, yanda ekrana cizen proje +
#   CPU birakmayan bir thread varken 10 ms yoklama 5 basis yakaladi;
#   kesme 50/50. Kesme donanimdan gelir, hangi proje kosarsa kossun sayar;
#   proje sirasi gelince basildi() ile okur. Basis kaybolmaz.
#
#   b = cyd.buton(pin)                    # pin <-> GND, pull-up (varsayilan)
#   b = cyd.buton(pin, aktif=1)           # pin <-> 3.3V, pull-down
#   b = cyd.buton(pin, fn=islev)          # her basista islev(b) (kisa tut)
#   b.basildi()  -> son sorudan beri kac basis (tuketir)
#   b.sayac      -> toplam basis      b.basili() -> su an basili mi
#   sekme_ms=40  -> titresim suzme (varsayilan 40 ms)
import cyd

PIN = 22
led_acik = False


def basinca(b):
    # Kesme disinda, ama o an hangi proje kosuyorsa onun icinde calisir:
    # kisa tut, agir isi asagidaki donguye birak.
    print('basis #%d' % b.sayac)


b = cyd.buton(PIN, fn=basinca)
print('buton hazir: GPIO%d <-> GND. Basinca LED renk degistirir.' % PIN)

try:
    while not cyd.should_stop():
        if b.basildi():
            led_acik = not led_acik
            try:
                if led_acik:
                    cyd.led(False, True, False)     # yesil
                else:
                    cyd.led_off()
            except Exception:
                pass                                # LED'i olmayan kart
        cyd.sleep(0.05)
finally:
    try:
        cyd.led_off()
    except Exception:
        pass
    print('bitti - toplam %d basis' % b.sayac)
