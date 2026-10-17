# Dokunmatik ekran demosu.
# Ekrana dokun -> dokundugun yere renkli daire cizer.
import cyd

d = cyd.display()          # 320x240 yatay
t = cyd.touch()

renkler = [cyd.RED, cyd.GREEN, cyd.BLUE, cyd.YELLOW,
           cyd.CYAN, cyd.MAGENTA, cyd.ORANGE]
i = 0

d.fill(cyd.BLACK)
d.text('Ekrana dokun', 60, 10, cyd.WHITE, cyd.BLACK, 2)
d.text('durdurmak icin web arayuzu', 40, 220, cyd.GREY, cyd.BLACK, 1)

print('hazir - ekrana dokun')

while not cyd.should_stop():
    p = t.touch()
    if p:
        x, y = p
        d.circle(x, y, 14, renkler[i % len(renkler)], fill=True)
        print('dokunma:', x, y)
        i += 1
        cyd.sleep(0.08)
    else:
        cyd.sleep(0.02)

d.fill(cyd.BLACK)
d.text('Durduruldu', 80, 110, cyd.RED, cyd.BLACK, 2)
print('cikiliyor')
