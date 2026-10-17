# Kart uzerindeki LDR ile ortam isigini olcup ekranda bar grafik cizer.
import cyd

d = cyd.display()
d.fill(cyd.BLACK)
d.text('Isik Sensoru', 70, 8, cyd.CYAN, cyd.BLACK, 2)

BAR_X, BAR_Y, BAR_W, BAR_H = 20, 60, 280, 40
d.rect(BAR_X - 2, BAR_Y - 2, BAR_W + 4, BAR_H + 4, cyd.GREY)

while not cyd.should_stop():
    ham = cyd.light()                  # 0..4095, buyudukce karanlik
    oran = 1.0 - (ham / 4095.0)
    dolu = int(BAR_W * oran)

    renk = cyd.GREEN if oran > 0.6 else (cyd.YELLOW if oran > 0.25 else cyd.RED)
    d.fill_rect(BAR_X, BAR_Y, dolu, BAR_H, renk)
    d.fill_rect(BAR_X + dolu, BAR_Y, BAR_W - dolu, BAR_H, cyd.BLACK)

    yazi = 'ham: %4d  parlaklik: %3d%%   ' % (ham, int(oran * 100))
    d.text(yazi, 20, 130, cyd.WHITE, cyd.BLACK, 1)
    print(yazi)

    cyd.sleep(0.3)

print('olcum durdu')
