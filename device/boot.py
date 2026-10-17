# boot.py - keep this tiny. If it throws, you lose the REPL.
#
# CPU frequency lives here rather than in main.py because it has to be set
# before Wi-Fi comes up: on a weakly powered board 240 MHz plus the radio's
# current spike is what browns the chip out.
import machine
import gc

_freq = 240


def _oku_freq():
    try:
        import json
        with open('/config.json') as f:
            return int(json.load(f).get('cpu_freq') or 240)
    except Exception:
        return 240


def _ayar(anahtar, varsayilan=None):
    try:
        import json
        with open('/config.json') as f:
            return json.load(f).get(anahtar, varsayilan)
    except Exception:
        return varsayilan


# Zayif beslemeli kartlarda brownout dedektoru, cip aslinda calisabilecek
# gerilimdeyken bile resetleyebiliyor (ESP32'nin datasheet minimumu 2.3V).
# BU BIR TAKAS: koruma kapaninca gerilim gercekten cokerse temiz reset
# yerine flash bozulmasi riski var. Sadece besleme duzeltilemiyorsa ac.
if _ayar('disable_bod'):
    try:
        machine.mem32[0x3FF480D4] = 0      # RTC_CNTL_BROWN_OUT_REG
        print('[boot] brownout dedektoru KAPATILDI (config: disable_bod)')
    except Exception as e:
        print('[boot] brownout kapatilamadi:', e)

try:
    _freq = _oku_freq()
    machine.freq(_freq * 1000000)
except Exception:
    try:
        machine.freq(240000000)
    except Exception:
        pass

gc.collect()
