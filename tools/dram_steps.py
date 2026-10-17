"""Attribute the missing internal DRAM to a specific boot step.

Runs over the serial REPL (main.py is not started there), doing each part
of the boot by hand and measuring after every one.
"""
import subprocess
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM3'

SCRIPT = r'''
import gc, esp32, time

def d():
    gc.collect()
    return sum(x[1] for x in esp32.idf_heap_info(esp32.HEAP_DATA)) // 1024

son = d()
print('%-34s %4d KB' % ('bos DRAM (baslangic)', son))

def adim(ad, fn):
    global son
    try:
        fn()
    except Exception as e:
        print('   (%s hata: %s)' % (ad, e))
    su = d()
    print('%-34s %4d KB   fark %+d' % (ad, su, su - son))
    son = su

def _store():
    import store
    store.init(try_sd=False)
adim('store.init(try_sd=False)', _store)

def _sd():
    import cyd
    print('   mount_sd ->', cyd.mount_sd())
adim('cyd.mount_sd()  <-- SUPHELI', _sd)

def _disp():
    import cyd
    cyd.display()
adim('cyd.display()', _disp)

def _srv():
    import jobs, server
    global S
    S = server.Server(jobs.Manager(), port=8080)
    S.listen()
adim('sunucu soketi acildi', _srv)

def _close():
    S.sock.close()
adim('soket kapatildi', _close)
'''

r = subprocess.run(
    [sys.executable, '-m', 'mpremote', 'connect', PORT, 'exec', SCRIPT],
    capture_output=True, text=True, timeout=180)
print(r.stdout)
if r.stderr.strip():
    print('--- stderr ---')
    print(r.stderr)
