# Hangi ag yontemleri calisiyor? Tek tek dener, sonucu yazar.
import requests

def dene(ad, fn):
    try:
        print('%-22s -> %s' % (ad, fn()))
    except Exception as e:
        print('%-22s -> HATA %s: %s' % (ad, type(e).__name__, e))


def http_duz():
    r = requests.get('http://example.com', timeout=10)
    n = len(r.text)
    kod = r.status_code
    r.close()
    return 'HTTP %s, %d bayt' % (kod, n)


def https_test():
    r = requests.get('https://example.com', timeout=15)
    kod = r.status_code
    n = len(r.text)
    r.close()
    return 'HTTPS %s, %d bayt' % (kod, n)


def https_json():
    r = requests.get('https://api.github.com/zen', timeout=15)
    t = r.text[:60]
    r.close()
    return t


def ntp():
    import ntptime
    import time
    ntptime.settime()
    y, m, d, h, mi, s = time.localtime()[:6]
    return '%04d-%02d-%02d %02d:%02d:%02d UTC' % (y, m, d, h, mi, s)


def soket():
    import socket
    ai = socket.getaddrinfo('example.com', 80)[0][-1]
    s = socket.socket()
    s.settimeout(10)
    s.connect(ai)
    s.send(b'GET / HTTP/1.0\r\nHost: example.com\r\n\r\n')
    ilk = s.recv(40)
    s.close()
    return repr(ilk)


dene('duz HTTP', http_duz)
dene('HTTPS', https_test)
dene('HTTPS + json api', https_json)
dene('NTP saat', ntp)
dene('ham soket', soket)
print('deneme bitti')
