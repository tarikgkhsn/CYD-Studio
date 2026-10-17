# Panelin kendisine soralim: hangi denetleyici, MADCTL su an ne?
# Okuma icin SPI'yi yavaslatmak sart - ILI9341 yazma 40 MHz kabul eder
# ama okumada ~6 MHz ustunde cop dondurur.
import cyd

d = cyd.display()
spi = d.spi


def oku(cmd, n):
    spi.init(baudrate=1000000)
    d.dc(0)
    d.cs(0)
    spi.write(bytes([cmd]))
    d.dc(1)
    buf = spi.read(n + 1, 0x00)      # ilk bayt dummy
    d.cs(1)
    spi.init(baudrate=40000000)
    return buf[1:]


def hx(b):
    return ' '.join('%02X' % x for x in b)


print('RDDID   (0x04):', hx(oku(0x04, 3)))
print('RDID4   (0xD3):', hx(oku(0xD3, 4)), '  <- ILI9341 ise 00 93 41 bekleriz')
print('MADCTL  (0x0B):', hx(oku(0x0B, 1)))
print('PIXFMT  (0x0C):', hx(oku(0x0C, 1)))
print('DISPCTL (0x09):', hx(oku(0x09, 4)))
print('surucu genislik/yukseklik:', d.width, 'x', d.height)
print('kimlik okumasi bitti')
