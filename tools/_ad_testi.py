"""Check what __name__ actually is inside a project run by jobs.py.

The driver's `if __name__ == '__main__':` block never fired, so measure
the value rather than assume the runner sets it.
"""
import json
import time
import urllib.request

B = 'http://192.168.0.217'

SRC = (
    "print('__name__ degeri :', repr(__name__))\n"
    "print('main mi         :', __name__ == '__main__')\n"
    "print('__file__        :', repr(globals().get('__file__')))\n"
    "print('print enjekte mi:', 'print' in globals())\n"
)


def call(path, method='GET', body=None, timeout=25):
    if method == 'POST' and body is None:
        body = b''
    req = urllib.request.Request(B + path, data=body, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


print(call('/api/save?name=_ad_testi.py', 'POST', SRC.encode()))
print(call('/api/run?name=_ad_testi.py', 'POST'))
time.sleep(3)
d = call('/api/log?since=0')
for seq, src, txt in d['lines']:
    if src == '_ad_testi.py':
        print('  ', txt)
call('/api/delete?name=_ad_testi.py', 'POST')
