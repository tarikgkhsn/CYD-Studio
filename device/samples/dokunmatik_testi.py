# Dokunmatik izleyici. Bosta sessiz durur, sadece DOKUNULUNCA yazar.
# Hem loga basar hem ekrana daire cizer - ikisinden birini gorursen calisiyor.
import cyd

d = cyd.display()
t = cyd.touch()

d.fill(cyd.BLACK)
d.text('EKRANA DOKUN', 10, 10, cyd.WHITE, cyd.BLACK, 2)
d.text('log web arayuzunde', 10, 34, cyd.GREY, cyd.BLACK, 1)

print('hazir. IRQ bostayken:', t.irq.value(), '(dokununca 0 olmali)')
print('ekran:', d.width, 'x', d.height, ' yon:', d._rot)

renkler = (cyd.RED, cyd.GREEN, cyd.BLUE, cyd.YELLOW, cyd.CYAN, cyd.MAGENTA)
sayac = 0
onceki = False

while not cyd.should_stop():
    su_an = t.pressed()

    if su_an and not onceki:
        ham = t.raw()
        nokta = t.touch()
        if ham:
            print('DOKUNMA #%d  ham=(%d, %d) basinc=%d  ekran=%s'
                  % (sayac + 1, ham[0], ham[1], ham[2], nokta))
        else:
            print('IRQ dustu ama gecerli koordinat okunamadi (ham=None)')
        if nokta:
            d.circle(nokta[0], nokta[1], 12,
                     renkler[sayac % len(renkler)], fill=True)
        sayac += 1

    onceki = su_an
    cyd.sleep(0.03)

print('toplam %d dokunma algilandi' % sayac)
