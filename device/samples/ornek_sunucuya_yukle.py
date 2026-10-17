# SD karttaki bir dosyayi kendi sunucuna yukler.
#
# Onemli: dosya RAM'e ALINMAZ, parca parca gonderilir. Bir fotograf 200 KB
# olabilir ve bu kartta o kadar bos RAM yok. Ham soket kullaniyoruz cunku
# requests tum govdeyi bellekte ister.
#
# Sunucu tarafinda beklenen: POST /yukle?ad=<dosya>  govde = ham baytlar
# (PHP: file_put_contents($_GET['ad'], file_get_contents('php://input')))
import socket
import os
import cyd

SUNUCU = '192.168.1.26'      # <-- kendi sunucunun IP'si
PORT = 8000
YOL = '/yukle'
PARCA = 1024                  # bir seferde gonderilecek bayt


def yukle(dosya_yolu, ad=None):
    ad = ad or dosya_yolu.rsplit('/', 1)[-1]
    boyut = os.stat(dosya_yolu)[6]
    print('yukleniyor: %s (%d bayt) -> %s:%d' % (ad, boyut, SUNUCU, PORT))

    ai = socket.getaddrinfo(SUNUCU, PORT)[0][-1]
    s = socket.socket()
    s.settimeout(20)
    s.connect(ai)

    basliklar = (
        'POST %s?ad=%s HTTP/1.0\r\n'
        'Host: %s\r\n'
        'Content-Type: application/octet-stream\r\n'
        'Content-Length: %d\r\n'
        '\r\n' % (YOL, ad, SUNUCU, boyut)
    )
    s.send(basliklar.encode())

    gonderilen = 0
    with open(dosya_yolu, 'rb') as f:
        while True:
            if cyd.should_stop():
                s.close()
                print('yukleme yarida kesildi')
                return None
            parca = f.read(PARCA)
            if not parca:
                break
            s.send(parca)
            gonderilen += len(parca)
            if gonderilen % (PARCA * 20) == 0:
                print('  %d / %d bayt (%%%d)'
                      % (gonderilen, boyut, gonderilen * 100 // boyut))

    cevap = s.recv(120)
    s.close()
    ilk = cevap.split(b'\r\n')[0].decode() if cevap else '(cevap yok)'
    print('bitti: %d bayt gonderildi | sunucu: %s' % (gonderilen, ilk))
    return ilk


# --- ornek kullanim ---------------------------------------------------
# Once yuklenecek bir dosya hazirlayalim (kamera yerine gecici ornek)
import store

test = store.base() + '/ornek_veri.txt'
with open(test, 'w') as f:
    for i in range(200):
        f.write('satir %d - karttan sunucuya yuklenen ornek veri\n' % i)

print('bos DRAM: %d KB' % (cyd.dram() // 1024))
try:
    yukle(test)
except OSError as e:
    print('BAGLANTI HATASI:', e)
    print('SUNUCU degiskenini kendi makinenin IP adresiyle degistir.')
    print('Hizli test sunucusu icin PC de:')
    print('  python tools/upload_server.py')

os.remove(test)
print('ornek bitti')
