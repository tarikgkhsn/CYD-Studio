# Bu firmware'de gercekten NE VAR? Tahmin degil, olcum.
import gc
import sys


def dene(ad, fn):
    gc.collect()
    once = gc.mem_free()
    try:
        sonuc = fn()
        print('%-20s VAR    %s' % (ad, sonuc))
    except Exception as e:
        print('%-20s YOK    %s: %s' % (ad, type(e).__name__, e))
    gc.collect()
    fark = once - gc.mem_free()
    if fark > 2000:
        print('%-20s        (~%d KB RAM tuketti)' % ('', fark // 1024))


def modul(ad):
    def f():
        m = __import__(ad)
        return getattr(m, '__name__', ad)
    return f


print('--- MicroPython:', sys.version)
print('--- platform   :', sys.platform)

print('\n=== ag / haberlesme ===')
dene('network', modul('network'))
dene('socket', modul('socket'))
dene('ssl', modul('ssl'))
dene('requests', modul('requests'))
dene('ntptime', modul('ntptime'))
dene('webrepl', modul('webrepl'))

print('\n=== bluetooth ===')


def ble_ac():
    import bluetooth
    ble = bluetooth.BLE()
    ble.active(True)
    mac = ble.config('mac')
    ble.active(False)
    return 'BLE acildi, mac=%s' % (mac,)


dene('bluetooth modulu', modul('bluetooth'))
dene('BLE acilis testi', ble_ac)

print('\n=== donanim / depolama ===')
dene('machine.SDCard', lambda: __import__('machine').SDCard)
dene('esp32', modul('esp32'))
dene('esp', modul('esp'))
dene('framebuf', modul('framebuf'))
dene('_thread', modul('_thread'))
dene('uasyncio', modul('asyncio'))
dene('hashlib', modul('hashlib'))
dene('cryptolib', modul('cryptolib'))
dene('binascii', modul('binascii'))
dene('json', modul('json'))
dene('re', modul('re'))
dene('deflate', modul('deflate'))

print('\n=== kamera ===')
dene('camera (OV2640)', modul('camera'))

print('\n--- tarama bitti')
