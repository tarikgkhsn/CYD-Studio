# OLED'de surekli bir seyler cizer - ag yok, sunucu yok, sadece ekran.
#
# Bu kartin WiFi'si acilirken besleme cokuyor (brownout), o yuzden panelsiz
# calisan bir sey lazimdi. Bu script radyoya hic dokunmuyor: kart bu haliyle
# gayet kararli.
#
# Pinleri cyd katmani buluyor - hangi GPIO'ya bagli oldugunu bilmemize
# gerek yok, I2C aday ciftlerini tarayip 0x3C/0x3D'yi ariyor.
import time
import cyd

# 0 = sonsuz. Panelden calistirilirsa durdur butonu zaten keser.
SURE = 0

d = cyd.display()
W, H = d.width, d.height
BEYAZ, SIYAH = cyd.WHITE, cyd.BLACK


def yaz_ortali(metin, y, olcek=1):
    # 8 px genislik * olcek, kabaca ortalamak icin yeterli
    x = (W - len(metin) * 8 * olcek) // 2
    d.text(metin, max(0, x), y, BEYAZ, SIYAH, olcek)


# --- acilis
d.fill(SIYAH)
yaz_ortali('CYD', 14, 3)
yaz_ortali('Studio', 42, 2)
d.show()
time.sleep(1.6)

d.fill(SIYAH)
yaz_ortali('OLED hazir', 28, 1)
d.show()
time.sleep(0.9)

# --- iki top, farkli hizlarda
TABAN = 50               # bu satirin altinda yazi bandi var
toplar = [
    {'x': 20.0, 'y': 20.0, 'dx': 1.7, 'dy': 1.1, 'r': 5},
    {'x': 90.0, 'y': 32.0, 'dx': -1.1, 'dy': 1.9, 'r': 3},
]

bar = 0
yon = 3
kare = 0
basla = time.ticks_ms()

# should_stop panelden calistirilinca var, mpremote ile calistirinca yok
dur = getattr(cyd, 'should_stop', None) or (lambda: False)

print('ciziyor... (Ctrl-C ile kes)')

while not dur():
    d.fill(SIYAH)
    d.rect(0, 0, W, TABAN, BEYAZ)

    for t in toplar:
        t['x'] += t['dx']
        t['y'] += t['dy']
        r = t['r']
        if t['x'] - r <= 1 or t['x'] + r >= W - 2:
            t['dx'] = -t['dx']
            t['x'] += t['dx']
        if t['y'] - r <= 1 or t['y'] + r >= TABAN - 2:
            t['dy'] = -t['dy']
            t['y'] += t['dy']
        d.circle(int(t['x']), int(t['y']), r, BEYAZ, fill=True)

    # alt bant: isim + saga sola gezen cizgi
    d.text('CYD Studio', 24, TABAN + 3, BEYAZ, SIYAH, 1)
    bar += yon
    if bar <= 0 or bar >= W - 24:
        yon = -yon
    d.hline(bar, H - 2, 24, BEYAZ)

    d.show()
    kare += 1
    time.sleep_ms(20)

    if SURE and time.ticks_diff(time.ticks_ms(), basla) > SURE * 1000:
        break

sn = time.ticks_diff(time.ticks_ms(), basla) / 1000
print('bitti - %d kare / %.1f sn (%.1f fps)' % (kare, sn, kare / max(sn, 0.1)))
