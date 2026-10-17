# Ekran yonu + renk duzeni testi. 4 adim, her biri 8 saniye.
#
# BANA SU IKI SEYI SOYLE:
#   1) Hangi NO'da beyaz cerceve ekranin DORT kenarina da degdi
#      (altta/sagda cizilmemis beyaz serit kalmadi)?
#   2) O adimda buyuk kare NE RENK gorundu? (kirmizi mi, mavi mi?)
import cyd

d = cyd.display()

ADIMLAR = (
    (1, 0x48, 240, 320),
    (2, 0x28, 320, 240),
    (3, 0x88, 240, 320),
    (4, 0xE8, 320, 240),
)

for no, madctl, w, h in ADIMLAR:
    if cyd.should_stop():
        break

    d._cmd(0x36, bytes([madctl]))
    d.width = w
    d.height = h

    d.fill(cyd.BLACK)
    # cerceve - dogru adimda dort kenara da degmeli
    d.rect(0, 0, w, h, cyd.WHITE)
    d.rect(1, 1, w - 2, h - 2, cyd.WHITE)
    d.rect(2, 2, w - 4, h - 4, cyd.WHITE)

    # tek buyuk kare: KIRMIZI gonderiyoruz. Mavi gorunuyorsa kanallar ters.
    d.fill_rect(w - 74, h - 74, 60, 60, cyd.RED)

    d.text('NO %d' % no, 10, 14, cyd.WHITE, cyd.BLACK, 5)
    d.text('%dx%d' % (w, h), 10, 62, cyd.WHITE, cyd.BLACK, 2)
    d.text('kare ne renk?', 10, 88, cyd.WHITE, cyd.BLACK, 2)

    print('NO %d -> madctl=0x%02X %dx%d  (kare KIRMIZI gonderildi)'
          % (no, madctl, w, h))

    if not cyd.sleep(8):
        break

d.fill(cyd.BLACK)
d.text('bitti', 10, 100, cyd.WHITE, cyd.BLACK, 3)
print('bitti - cerceve 4 kenara degen NO ve karenin rengini soyle')
