# HTTPS, TLS el sikismasi icin buyuk ve bitisik bir bellek blogu ister.
# Once cop toplayip en buyuk bloga bakalim, sonra deneyelim.
import gc
import requests

gc.collect()
print('bos RAM      :', gc.mem_free())
try:
    print('en buyuk blok:', gc.mem_maxfree())
except AttributeError:
    pass

for url in ('https://example.com', 'https://api.github.com/zen'):
    gc.collect()
    try:
        r = requests.get(url, timeout=20)
        govde = r.text[:70]
        kod = r.status_code
        r.close()
        print('%s -> %s | %s' % (url, kod, govde))
    except Exception as e:
        print('%s -> HATA %s: %s (bos RAM %d)'
              % (url, type(e).__name__, e, gc.mem_free()))
    gc.collect()

print('bitti')
